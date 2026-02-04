"""Use cases for the vendor PayWord (hash-chain) flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.payword_dtos import PaywordSettlementRequestDTO
from ....application.shared.payword_payloads import PaywordSettlementPayload
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ....crypto.payword import (
    b64_to_bytes,
    compute_cumulative_owed_amount,
    verify_token_against_root,
    verify_token_incremental,
)
from ....domain.shared import IssuerClientFactory
from ....domain.vendor.entities import PaywordPaymentChannel, PaywordState
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..payword_dtos import PaywordPaymentResponseDTO, ReceivePaywordPaymentDTO
from .payword_validators import (
    validate_payword_k,
    validate_payword_amount,
    check_duplicate_payword_payment,
)


class PaywordPaymentService:
    """Service for handling PayWord payments and PayWord settlement."""

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

    async def _verify_payword_channel(self, channel_id: str) -> PaywordPaymentChannel:
        """
        Verify that the PayWord channel exists on the issuer side and return it.

        This uses the issuer PayWord channel endpoint so PayWord commitment
        fields are present and validated.
        """
        try:
            async with self.issuer_client_factory() as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_payword_payment_channel(dto)
                channel_data = issuer_channel.model_dump()

                payment_channel = PaywordPaymentChannel.model_validate(channel_data)

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

    async def _save_payword_payment_with_retry(
        self,
        *,
        channel_id: str,
        payment_channel: PaywordPaymentChannel,
        new_state: PaywordState,
        is_first_payment: bool,
    ) -> tuple[int, Optional[PaywordState], PaywordPaymentChannel]:
        """
        Save a PayWord payment state, reconciling vendor cache races.

        Repository status codes:
          - 1: stored successfully (returns stored_state)
          - 0: rejected (race / not increasing; returns current state or None)
          - 2: channel missing in vendor cache (needs issuer verification)

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
                ) = await self.payment_channel_repository.save_channel_and_initial_payword_state(
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
                if not isinstance(cached, PaywordPaymentChannel):
                    raise TypeError("Cached channel is not PayWord-enabled")
                payment_channel = cached

            (
                status,
                stored_state,
            ) = await self.payment_channel_repository.save_payword_payment(
                payment_channel, new_state
            )

            if status != 2:
                return status, stored_state, payment_channel

            # status == 2: vendor cache is missing the channel; fetch from issuer,
            # then cache it and retry the save flow once.
            if attempt == 0:
                payment_channel = await self._verify_payword_channel(channel_id)
                is_first_payment = True
                continue

        # If we get here, something is inconsistent (e.g., channel was verified
        # but still appears missing in storage).
        return status, stored_state, payment_channel

    async def receive_payword_payment(
        self, channel_id: str, dto: ReceivePaywordPaymentDTO
    ) -> PaywordPaymentResponseDTO:
        """Receive and validate a PayWord (hash-chain) payment from a client."""
        (
            payment_channel,
            latest_state,
        ) = await self.payment_channel_repository.get_payword_channel_and_latest_state(
            channel_id
        )

        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_payword_channel(channel_id)
            is_first_payment = True
            latest_state = None

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")

        prev_k = latest_state.k if latest_state else 0
        prev_token_b64 = latest_state.token_b64 if latest_state else None

        # Idempotency + replay protection (pure function)
        # - If the client retries the *exact same* payment (same k + same token),
        #   accept it and return the stored state (handles transient disconnects).
        # - If k is the same but token differs, reject as a replay/double-spend attempt.
        # - Otherwise, enforce strictly increasing k.
        is_duplicate = check_duplicate_payword_payment(
            k=dto.k,
            token=dto.token_b64,
            prev_k=prev_k,
            prev_token=prev_token_b64,
        )
        if is_duplicate:
            # If duplicate check returns True, latest_state must not be None
            assert latest_state is not None
            cumulative_owed_amount = compute_cumulative_owed_amount(
                k=latest_state.k, unit_value=payment_channel.payword_unit_value
            )
            return PaywordPaymentResponseDTO(
                channel_id=latest_state.channel_id,
                k=latest_state.k,
                cumulative_owed_amount=cumulative_owed_amount,
                created_at=latest_state.created_at,
            )

        # Validate k (pure function)
        validate_payword_k(
            k=dto.k,
            prev_k=prev_k,
            max_k=payment_channel.payword_max_k,
        )

        cumulative_owed_amount = compute_cumulative_owed_amount(
            k=dto.k, unit_value=payment_channel.payword_unit_value
        )
        # Validate amount (pure function)
        validate_payword_amount(
            cumulative_owed=cumulative_owed_amount,
            channel_amount=payment_channel.amount,
        )

        try:
            token = b64_to_bytes(dto.token_b64)
        except Exception as e:
            raise ValueError(f"Invalid token_b64: {e}") from e

        if latest_state is None:
            try:
                root = b64_to_bytes(payment_channel.payword_root_b64)
            except Exception as e:
                raise ValueError(f"Invalid payword_root_b64: {e}") from e
            if not verify_token_against_root(token=token, k=dto.k, root=root):
                raise ValueError("Invalid PayWord token for k (root mismatch)")
        else:
            delta_k = dto.k - prev_k
            if delta_k <= 0:
                raise ValueError("Invalid PayWord delta_k")
            try:
                prev_token = b64_to_bytes(prev_token_b64) if prev_token_b64 else b""
            except Exception as e:
                raise ValueError(f"Invalid stored PayWord token: {e}") from e
            if not verify_token_incremental(
                token=token, prev_token=prev_token, delta_k=delta_k
            ):
                raise ValueError("Invalid PayWord token for k (incremental mismatch)")

        new_state = PaywordState(
            channel_id=channel_id,
            k=dto.k,
            token_b64=dto.token_b64,
            created_at=datetime.now(timezone.utc),
        )

        (
            status,
            stored_state,
            payment_channel,
        ) = await self._save_payword_payment_with_retry(
            channel_id=channel_id,
            payment_channel=payment_channel,
            new_state=new_state,
            is_first_payment=is_first_payment,
        )

        if status == 1:
            if stored_state is None:
                raise RuntimeError(
                    "Unexpected: save_payword_payment returned success but no state"
                )
            return PaywordPaymentResponseDTO(
                channel_id=stored_state.channel_id,
                k=stored_state.k,
                cumulative_owed_amount=cumulative_owed_amount,
                created_at=stored_state.created_at,
            )
        elif status == 0:
            current_k = stored_state.k if stored_state else "unknown"
            raise ValueError(
                f"PayWord k must be increasing (race detected). Got {dto.k}, DB has {current_k}"
            )
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, channel_id: str, dto: CloseChannelDTO) -> None:
        """Settle a PayWord channel by settling the latest PayWord state on the issuer."""
        if dto.channel_id != channel_id:
            raise ValueError("Channel ID mismatch between path and payload")
        channel = await self.payment_channel_repository.get_by_channel_id(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, PaywordPaymentChannel):
            raise TypeError("Payment channel is not PayWord-enabled")
        if channel.is_closed:
            return None

        latest_state = await self.payment_channel_repository.get_payword_state(
            channel_id
        )
        if not latest_state:
            raise ValueError("No PayWord payments received for this channel")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            k=latest_state.k, unit_value=channel.payword_unit_value
        )
        if cumulative_owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        settlement_payload = PaywordSettlementPayload(
            channel_id=channel_id,
            k=latest_state.k,
            token_b64=latest_state.token_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaywordSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            k=latest_state.k,
            token_b64=latest_state.token_b64,
            vendor_signature_b64=vendor_signature_b64,
        )

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_payword_payment_channel(channel_id, request_dto)

        await self.payment_channel_repository.mark_closed(
            channel_id=channel_id,
            amount=channel.amount,
            balance=cumulative_owed_amount,
        )

        return None
