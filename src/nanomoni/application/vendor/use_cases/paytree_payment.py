"""Use cases for the vendor PayTree (Merkle tree) flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.paytree_dtos import PaytreeSettlementRequestDTO
from ....application.shared.paytree_payloads import PaytreeSettlementPayload
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ....crypto.paytree import (
    compute_cumulative_owed_amount,
    verify_paytree_proof,
)
from ....domain.vendor.entities import PaymentChannel, PaytreeState
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ....infrastructure.issuer.issuer_client import AsyncIssuerClient
from ..dtos import CloseChannelDTO
from ..paytree_dtos import PaytreePaymentResponseDTO, ReceivePaytreePaymentDTO


class PaytreePaymentService:
    """Service for handling PayTree payments and PayTree settlement."""

    def __init__(
        self,
        payment_channel_repository: PaymentChannelRepository,
        issuer_base_url: str,
        vendor_public_key_der_b64: str,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_channel_repository = payment_channel_repository
        self.issuer_base_url = issuer_base_url
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_paytree_channel(self, channel_id: str) -> PaymentChannel:
        """
        Verify that the PayTree channel exists on the issuer side and return it.

        This uses the issuer PayTree channel endpoint so PayTree commitment
        fields are present and validated.
        """
        try:
            async with AsyncIssuerClient(self.issuer_base_url) as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_paytree_payment_channel(dto)
                channel_data = issuer_channel.model_dump()

                payment_channel = PaymentChannel.model_validate(channel_data)

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

    async def _save_paytree_payment_with_retry(
        self,
        *,
        channel_id: str,
        payment_channel: PaymentChannel,
        new_state: PaytreeState,
        is_first_payment: bool,
    ) -> tuple[int, Optional[PaytreeState], PaymentChannel]:
        """
        Save a PayTree payment state, reconciling vendor cache races.

        Repository status codes:
          - 1: stored successfully (returns stored_state)
          - 0: rejected (race / not increasing; returns current state or None)
          - 2: channel missing in vendor cache (needs issuer verification)
          - 3: i exceeds max_i

        This helper centralizes the "first payment vs subsequent payment" flow
        and the status==2 reconciliation logic so callers don't need deeply
        nested conditionals.
        """

        # We may need up to two passes:
        # - First attempt using current local knowledge.
        # - If status==2, fetch from issuer, then retry initial-cache + save.
        for attempt in range(2):
            if is_first_payment:
                (
                    status,
                    stored_state,
                ) = await self.payment_channel_repository.save_channel_and_initial_paytree_state(
                    payment_channel, new_state
                )
                if status == 1:
                    return status, stored_state, payment_channel

                # status == 0: cache collision; switch to subsequent-save flow
                is_first_payment = False
                cached = await self.payment_channel_repository.get_by_channel_id(
                    channel_id
                )
                if not cached:
                    raise RuntimeError(
                        "Race condition handling failed: channel missing after collision"
                    )
                payment_channel = cached

            (
                status,
                stored_state,
            ) = await self.payment_channel_repository.save_paytree_payment(
                payment_channel, new_state
            )

            if status != 2:
                return status, stored_state, payment_channel

            # status == 2: vendor cache is missing the channel; fetch from issuer,
            # then cache it and retry the save flow once.
            if attempt == 0:
                payment_channel = await self._verify_paytree_channel(channel_id)
                is_first_payment = True
                continue

        # If we get here, something is inconsistent (e.g., channel was verified
        # but still appears missing in storage).
        return status, stored_state, payment_channel

    async def receive_paytree_payment(
        self, channel_id: str, dto: ReceivePaytreePaymentDTO
    ) -> PaytreePaymentResponseDTO:
        """Receive and validate a PayTree (Merkle proof) payment from a client."""
        payment_channel = await self.payment_channel_repository.get_by_channel_id(
            channel_id
        )

        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_paytree_channel(channel_id)
            is_first_payment = True

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")

        if payment_channel.paytree_root_b64 is None:
            raise ValueError("Payment channel is not PayTree-enabled")
        if payment_channel.paytree_unit_value is None:
            raise ValueError("Payment channel is missing paytree_unit_value")
        if payment_channel.paytree_max_i is None:
            raise ValueError("Payment channel is missing paytree_max_i")

        paytree_hash_alg = payment_channel.paytree_hash_alg or "sha256"
        if paytree_hash_alg != "sha256":
            raise ValueError("Unsupported PayTree hash algorithm")

        latest_state = await self.payment_channel_repository.get_paytree_state(
            channel_id
        )
        prev_i = latest_state.i if latest_state else -1

        # Idempotency + replay protection:
        # - If the client retries the *exact same* payment (same i + same proof),
        #   accept it and return the stored state (handles transient disconnects).
        # - If i is the same but proof differs, reject as a replay/double-spend attempt.
        # - Otherwise, enforce strictly increasing i.
        if dto.i <= prev_i:
            if latest_state is not None and dto.i == prev_i:
                if (
                    dto.leaf_b64 != latest_state.leaf_b64
                    or dto.siblings_b64 != latest_state.siblings_b64
                ):
                    raise ValueError(
                        "Duplicate PayTree i with mismatched proof (possible replay attack)"
                    )
                cumulative_owed_amount = compute_cumulative_owed_amount(
                    i=latest_state.i, unit_value=payment_channel.paytree_unit_value
                )
                return PaytreePaymentResponseDTO(
                    channel_id=latest_state.channel_id,
                    i=latest_state.i,
                    cumulative_owed_amount=cumulative_owed_amount,
                    created_at=latest_state.created_at,
                )

            raise ValueError(
                f"PayTree i must be increasing. Got {dto.i}, expected > {prev_i}"
            )

        if dto.i > payment_channel.paytree_max_i:
            raise ValueError("PayTree i exceeds channel max_i")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=payment_channel.paytree_unit_value
        )
        if cumulative_owed_amount > payment_channel.amount:
            raise ValueError(
                f"cumulative_owed_amount {cumulative_owed_amount} exceeds payment channel amount {payment_channel.amount}"
            )

        # Verify Merkle proof against root
        if not verify_paytree_proof(
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            root_b64=payment_channel.paytree_root_b64,
        ):
            raise ValueError("Invalid PayTree proof (root mismatch)")

        new_state = PaytreeState(
            channel_id=channel_id,
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            created_at=datetime.now(timezone.utc),
        )

        (
            status,
            stored_state,
            payment_channel,
        ) = await self._save_paytree_payment_with_retry(
            channel_id=channel_id,
            payment_channel=payment_channel,
            new_state=new_state,
            is_first_payment=is_first_payment,
        )

        if status == 1:
            if stored_state is None:
                raise RuntimeError(
                    "Unexpected: save_paytree_payment returned success but no state"
                )
            return PaytreePaymentResponseDTO(
                channel_id=stored_state.channel_id,
                i=stored_state.i,
                cumulative_owed_amount=cumulative_owed_amount,
                created_at=stored_state.created_at,
            )
        elif status == 0:
            current_i = stored_state.i if stored_state else "unknown"
            raise ValueError(
                f"PayTree i must be increasing (race detected). Got {dto.i}, DB has {current_i}"
            )
        elif status == 3:
            raise ValueError("PayTree i exceeds max_i for this channel")
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        """Settle a PayTree channel by settling the latest PayTree state on the issuer."""
        channel = await self.payment_channel_repository.get_by_channel_id(
            dto.channel_id
        )
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        if (
            channel.paytree_root_b64 is None
            or channel.paytree_unit_value is None
            or channel.paytree_max_i is None
        ):
            raise ValueError("Payment channel is not PayTree-enabled")

        latest_state = await self.payment_channel_repository.get_paytree_state(
            dto.channel_id
        )
        if not latest_state:
            raise ValueError("No PayTree payments received for this channel")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=latest_state.i, unit_value=channel.paytree_unit_value
        )
        if cumulative_owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        settlement_payload = PaytreeSettlementPayload(
            channel_id=dto.channel_id,
            i=latest_state.i,
            leaf_b64=latest_state.leaf_b64,
            siblings_b64=latest_state.siblings_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaytreeSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            i=latest_state.i,
            leaf_b64=latest_state.leaf_b64,
            siblings_b64=latest_state.siblings_b64,
            vendor_signature_b64=vendor_signature_b64,
        )

        async with AsyncIssuerClient(self.issuer_base_url) as issuer_client:
            await issuer_client.settle_paytree_payment_channel(
                dto.channel_id, request_dto
            )

        await self.payment_channel_repository.mark_closed(
            channel_id=dto.channel_id,
            close_payload_b64="",
            client_close_signature_b64="",
            amount=channel.amount,
            balance=cumulative_owed_amount,
            vendor_close_signature_b64=vendor_signature_b64,
        )

        return None
