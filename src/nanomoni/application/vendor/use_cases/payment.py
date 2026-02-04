"""Use cases for the vendor application layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.shared.payment_channel_payloads import (
    SignatureChannelSettlementPayload,
)
from ....application.shared.serialization import payload_to_bytes
from ....application.issuer.dtos import (
    CloseChannelRequestDTO,
    GetPaymentChannelRequestDTO,
)
from ....crypto.certificates import (
    load_private_key_from_pem,
    load_public_key_from_der_b64,
    sign_bytes,
    verify_signature_bytes,
    dto_to_canonical_json_bytes,
    DERB64,
)
from ....domain.shared import IssuerClientFactory
from ....domain.vendor.entities import SignaturePaymentChannel, SignatureState
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
)


class PaymentService:
    """Service for handling off-chain payment transactions."""

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

    async def _verify_payment_channel(self, channel_id: str) -> SignaturePaymentChannel:
        """
        Verify that the payment channel exists on the issuer side and return it.

        This method:
        - fetches the channel from the issuer,
        - validates that it is open, and
        - validates that it belongs to this vendor (by public key).

        It does NOT persist the channel locally. Caching is performed only
        after a fully validated first payment in receive_payment.
        """
        try:
            async with self.issuer_client_factory() as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_payment_channel(dto)
                channel_data = issuer_channel.model_dump()

                # Safely deserialize using the entity
                payment_channel = SignaturePaymentChannel.model_validate(channel_data)

                # Check if channel is closed
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
        payment_channel: SignaturePaymentChannel,
        new_state: SignatureState,
        is_first_payment: bool,
    ) -> tuple[int, Optional[SignatureState], SignaturePaymentChannel]:
        """
        Save an off-chain payment, reconciling vendor cache races.

        Repository status codes:
          - 1: stored successfully (returns stored_tx)
          - 0: rejected (race / not increasing; returns current tx or None)
          - 2: channel missing in vendor cache (needs issuer verification)

        """

        # We may need up to two passes:
        # - First attempt using current local knowledge.
        # - If status==2, fetch from issuer, then retry initial-cache + save.
        for attempt in range(2):
            if is_first_payment:
                (
                    status,
                    stored_state,
                ) = await self.payment_channel_repository.save_channel_and_initial_payment(
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
                if not isinstance(cached, SignaturePaymentChannel):
                    raise TypeError("Cached channel is not signature-mode")
                payment_channel = cached

            status, stored_state = await self.payment_channel_repository.save_payment(
                payment_channel, new_state
            )

            if status != 2:
                return status, stored_state, payment_channel

            # status == 2: vendor cache is missing the channel; fetch from issuer,
            # then cache it and retry the save flow once.
            if attempt == 0:
                payment_channel = await self._verify_payment_channel(channel_id)
                is_first_payment = True
                continue

        # If we get here, something is inconsistent (e.g., channel was verified
        # but still appears missing in storage).
        return status, stored_state, payment_channel

    async def receive_payment(self, dto: ReceivePaymentDTO) -> OffChainTxResponseDTO:
        """Receive and validate an off-chain payment from a client."""
        # 1) Get full channel aggregate (lazy load)
        payment_channel = await self.payment_channel_repository.get_by_channel_id(
            dto.channel_id
        )

        # 1.1) If missing, verify with issuer and cache locally (First Payment flow)
        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_payment_channel(dto.channel_id)
            is_first_payment = True
        elif not isinstance(payment_channel, SignaturePaymentChannel):
            raise TypeError("Payment channel is not signature-mode")

        latest_state = payment_channel.signature_state
        prev_cumulative_owed_amount = (
            latest_state.cumulative_owed_amount if latest_state else 0
        )

        # 1.2) Ensure the channel remains bound to this vendor
        if payment_channel.vendor_public_key_der_b64 != self.vendor_public_key_der_b64:
            raise ValueError("Payment channel is not for this vendor")

        # 2) Reconstruct canonical JSON from DTO fields (excluding signature)
        payload_bytes = dto_to_canonical_json_bytes(dto)

        # 3) Verify client's signature using the channel-bound public key
        client_public_key = load_public_key_from_der_b64(
            DERB64(payment_channel.client_public_key_der_b64)
        )
        try:
            verify_signature_bytes(client_public_key, payload_bytes, dto.signature_b64)
        except Exception as e:
            raise ValueError("Invalid client signature for payment") from e

        # 4) Idempotency + double spending protection.
        #
        # If the client retries the *exact same* payment (e.g., due to a transient
        # disconnect after the vendor stored the tx but before the client read the
        # response), accept the duplicate and return the stored tx.
        if latest_state and dto.cumulative_owed_amount == prev_cumulative_owed_amount:
            if dto.signature_b64 != latest_state.client_signature_b64:
                raise ValueError(
                    "Duplicate owed amount with mismatched signature (possible replay attack)"
                )
            return OffChainTxResponseDTO(
                channel_id=latest_state.channel_id,
                cumulative_owed_amount=latest_state.cumulative_owed_amount,
                created_at=latest_state.created_at,
            )

        # Otherwise, enforce strictly increasing owed amount.
        if dto.cumulative_owed_amount < prev_cumulative_owed_amount:
            raise ValueError(
                f"Owed amount must be increasing. Got {dto.cumulative_owed_amount}, expected > {prev_cumulative_owed_amount}"
            )

        # 5) Check if the payment channel amount is bigger than the cumulative_owed_amount
        # (Optimistic check for fast failure; authoritative check happens atomically in save_if_valid)
        if dto.cumulative_owed_amount > payment_channel.amount:
            raise ValueError(
                f"Owed amount {dto.cumulative_owed_amount} exceeds payment channel amount {payment_channel.amount}"
            )

        # 6) Create the latest signature state object (no payload persistence)
        signature_state = SignatureState(
            channel_id=dto.channel_id,
            cumulative_owed_amount=dto.cumulative_owed_amount,
            client_signature_b64=dto.signature_b64,
            created_at=datetime.now(timezone.utc),
        )

        (
            status,
            stored_tx,
            _payment_channel,
        ) = await self._save_payment_with_retry(
            channel_id=dto.channel_id,
            payment_channel=payment_channel,
            new_state=signature_state,
            is_first_payment=is_first_payment,
        )

        if status == 1:
            # Success: transaction was stored
            if stored_tx is None:
                raise RuntimeError(
                    "Unexpected: save_payment returned success but no transaction"
                )
            return OffChainTxResponseDTO(
                channel_id=stored_tx.channel_id,
                cumulative_owed_amount=stored_tx.cumulative_owed_amount,
                created_at=stored_tx.created_at,
            )
        elif status == 0:
            # Rejected: amount was not greater than current or exceeded channel capacity
            current_amt = stored_tx.cumulative_owed_amount if stored_tx else "unknown"
            raise ValueError(
                f"Owed amount must be increasing (race detected). Got {dto.cumulative_owed_amount}, DB has {current_amt}"
            )
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        """Settle a payment channel by sending the latest off-chain tx to issuer and marking local channel closed."""

        # 1) Fetch channel aggregate (includes latest tx)
        channel = await self.payment_channel_repository.get_by_channel_id(
            dto.channel_id
        )

        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, SignaturePaymentChannel):
            raise TypeError("Payment channel is not signature-mode")
        if channel.is_closed:
            return None

        latest_state = channel.signature_state
        if not latest_state:
            raise ValueError("No off-chain payments received for this channel")

        # 3) Reconstruct the canonical settlement payload bytes (same bytes the client signed).
        settlement_payload = SignatureChannelSettlementPayload(
            channel_id=dto.channel_id,
            cumulative_owed_amount=latest_state.cumulative_owed_amount,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        # 4) Vendor signs the same payload bytes (detached signature)
        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_close_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        # 5) Send close request to issuer with flat DTO structure
        request_dto = CloseChannelRequestDTO(
            channel_id=dto.channel_id,
            cumulative_owed_amount=latest_state.cumulative_owed_amount,
            client_close_signature_b64=latest_state.client_signature_b64,
            vendor_close_signature_b64=vendor_close_signature_b64,
        )

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_payment_channel(
                dto.channel_id,
                request_dto,
            )

        # 6) Mark closed locally
        await self.payment_channel_repository.mark_closed(
            channel_id=dto.channel_id,
            amount=channel.amount,
            balance=latest_state.cumulative_owed_amount,
        )

        return None
