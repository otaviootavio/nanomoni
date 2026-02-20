"""Use cases for the vendor PayTree Second Opt flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.paytree_second_opt_dtos import (
    PaytreeSecondOptSettlementRequestDTO,
)
from ....application.shared.paytree_second_opt_payloads import (
    PaytreeSecondOptSettlementPayload,
)
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ....crypto.paytree import compute_cumulative_owed_amount
from ....crypto.paytree_first_opt import compute_tree_depth
from ....crypto.paytree_second_opt import verify_pruned_paytree_proof
from ....domain.shared import IssuerClientFactory
from ....domain.vendor.entities import (
    PaytreeSecondOptPaymentChannel,
    PaytreeSecondOptState,
)
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..paytree_second_opt_dtos import (
    PaytreeSecondOptPaymentResponseDTO,
    ReceivePaytreeSecondOptPaymentDTO,
)
from .paytree_second_opt_validators import (
    check_duplicate_paytree_second_opt_payment,
    validate_paytree_second_opt_amount,
    validate_paytree_second_opt_i,
)


class PaytreeSecondOptPaymentService:
    """Service for handling PayTree Second Opt payments and settlement."""

    def __init__(
        self,
        payment_channel_repository: PaymentChannelRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_channel_repository = payment_channel_repository
        self.issuer_client_factory = issuer_client_factory
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_channel(self, channel_id: str) -> PaytreeSecondOptPaymentChannel:
        try:
            async with self.issuer_client_factory() as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = (
                    await issuer_client.get_paytree_second_opt_payment_channel(dto)
                )
                payment_channel = PaytreeSecondOptPaymentChannel.model_validate(
                    issuer_channel.model_dump()
                )
                if payment_channel.is_closed:
                    raise ValueError("Payment channel is closed")
                if (
                    payment_channel.vendor_public_key_der_b64
                    != self.vendor_public_key_der_b64
                ):
                    raise ValueError("Payment channel is not for this vendor")
                return payment_channel
        except HttpResponseError as e:
            if e.response.status_code == 404:
                raise ValueError("Payment channel not found on issuer")
            raise ValueError(f"Failed to verify payment channel: {e}")
        except HttpRequestError as e:
            raise ValueError(f"Could not connect to issuer: {e}")
        except ValidationError as e:
            raise ValueError(f"Invalid payment channel data from issuer: {e}")

    async def _save_payment_with_retry(
        self,
        *,
        channel_id: str,
        payment_channel: PaytreeSecondOptPaymentChannel,
        new_state: PaytreeSecondOptState,
        is_first_payment: bool,
    ) -> tuple[int, Optional[PaytreeSecondOptState], PaytreeSecondOptPaymentChannel]:
        for attempt in range(2):
            if is_first_payment:
                (
                    status,
                    stored_state,
                ) = await self.payment_channel_repository.save_channel_and_initial_paytree_second_opt_state(
                    payment_channel, new_state
                )
                if status == 1:
                    return status, stored_state, payment_channel

                is_first_payment = False
                cached = await self.payment_channel_repository.get_by_channel_id(
                    channel_id
                )
                if not cached:
                    raise RuntimeError(
                        "Race condition handling failed: channel missing after collision"
                    )
                if not isinstance(cached, PaytreeSecondOptPaymentChannel):
                    raise TypeError("Cached channel is not PayTree Second Opt-enabled")
                payment_channel = cached

            (
                status,
                stored_state,
            ) = await self.payment_channel_repository.save_paytree_second_opt_payment(
                payment_channel, new_state
            )
            if status != 2:
                return status, stored_state, payment_channel
            if attempt == 0:
                payment_channel = await self._verify_channel(channel_id)
                is_first_payment = True
                continue
        return status, stored_state, payment_channel

    async def receive_payment(
        self, channel_id: str, dto: ReceivePaytreeSecondOptPaymentDTO
    ) -> PaytreeSecondOptPaymentResponseDTO:
        (
            payment_channel,
            latest_state,
        ) = await self.payment_channel_repository.get_paytree_second_opt_channel_and_latest_state(
            channel_id
        )

        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_channel(channel_id)
            is_first_payment = True
            latest_state = None

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")

        prev_i = latest_state.i if latest_state else 0
        prev_leaf = latest_state.leaf_b64 if latest_state else None
        prev_siblings = latest_state.siblings_b64 if latest_state else None
        is_duplicate = check_duplicate_paytree_second_opt_payment(
            i=dto.i,
            leaf=dto.leaf_b64,
            siblings=dto.siblings_b64,
            prev_i=prev_i,
            prev_leaf=prev_leaf,
            prev_siblings=prev_siblings,
        )
        if is_duplicate:
            assert latest_state is not None
            cumulative_owed_amount = compute_cumulative_owed_amount(
                i=latest_state.i,
                unit_value=payment_channel.paytree_second_opt_unit_value,
            )
            return PaytreeSecondOptPaymentResponseDTO(
                channel_id=latest_state.channel_id,
                i=latest_state.i,
                cumulative_owed_amount=cumulative_owed_amount,
                created_at=latest_state.created_at,
            )

        validate_paytree_second_opt_i(
            i=dto.i,
            prev_i=prev_i,
            max_i=payment_channel.paytree_second_opt_max_i,
        )
        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=payment_channel.paytree_second_opt_unit_value
        )
        validate_paytree_second_opt_amount(
            cumulative_owed=cumulative_owed_amount,
            channel_amount=payment_channel.amount,
        )

        node_cache_b64 = latest_state.node_cache_b64 if latest_state else {}
        ok, _, updated_cache = verify_pruned_paytree_proof(
            i=dto.i,
            root_b64=payment_channel.paytree_second_opt_root_b64,
            leaf_b64=dto.leaf_b64,
            pruned_siblings_b64=dto.siblings_b64,
            max_i=payment_channel.paytree_second_opt_max_i,
            node_cache_b64=node_cache_b64,
        )
        if not ok:
            raise ValueError("Invalid PayTree Second Opt proof")

        new_state = PaytreeSecondOptState(
            channel_id=channel_id,
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            node_cache_b64=updated_cache,
            created_at=datetime.now(timezone.utc),
        )

        status, stored_state, _ = await self._save_payment_with_retry(
            channel_id=channel_id,
            payment_channel=payment_channel,
            new_state=new_state,
            is_first_payment=is_first_payment,
        )
        if status == 1:
            if stored_state is None:
                raise RuntimeError("Unexpected: save returned success but no state")
            return PaytreeSecondOptPaymentResponseDTO(
                channel_id=stored_state.channel_id,
                i=stored_state.i,
                cumulative_owed_amount=cumulative_owed_amount,
                created_at=stored_state.created_at,
            )
        if status == 0:
            current_i = stored_state.i if stored_state else "unknown"
            raise ValueError(
                f"PayTree Second Opt i must be increasing (race detected). Got {dto.i}, DB has {current_i}"
            )
        if status == 3:
            raise ValueError("PayTree Second Opt i exceeds max_i for this channel")
        raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    def _full_siblings_from_cache(
        self, *, i: int, max_i: int, node_cache_b64: dict[str, str]
    ) -> list[str]:
        depth = compute_tree_depth(max_i)
        siblings: list[str] = []
        for level in range(depth):
            sibling_position = (i >> level) ^ 1
            key = f"{level}:{sibling_position}"
            value = node_cache_b64.get(key)
            if value is None:
                raise ValueError(
                    "Missing required sibling in node cache for settlement"
                )
            siblings.append(value)
        return siblings

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        channel = await self.payment_channel_repository.get_by_channel_id(
            dto.channel_id
        )
        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise TypeError("Payment channel is not PayTree Second Opt-enabled")
        if channel.is_closed:
            return None

        latest_state = (
            await self.payment_channel_repository.get_paytree_second_opt_state(
                dto.channel_id
            )
        )
        if not latest_state:
            raise ValueError("No PayTree Second Opt payments received for this channel")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=latest_state.i, unit_value=channel.paytree_second_opt_unit_value
        )
        if cumulative_owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        full_siblings_b64 = self._full_siblings_from_cache(
            i=latest_state.i,
            max_i=channel.paytree_second_opt_max_i,
            node_cache_b64=latest_state.node_cache_b64,
        )
        settlement_payload = PaytreeSecondOptSettlementPayload(
            channel_id=dto.channel_id,
            i=latest_state.i,
            leaf_b64=latest_state.leaf_b64,
            siblings_b64=full_siblings_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaytreeSecondOptSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            i=latest_state.i,
            leaf_b64=latest_state.leaf_b64,
            siblings_b64=full_siblings_b64,
            vendor_signature_b64=vendor_signature_b64,
        )
        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_paytree_second_opt_payment_channel(
                dto.channel_id, request_dto
            )

        await self.payment_channel_repository.mark_closed(
            channel_id=dto.channel_id,
            amount=channel.amount,
            balance=cumulative_owed_amount,
        )
        return None
