"""Use cases for the vendor application layer."""

from __future__ import annotations

import base64
from typing import Optional

from pydantic import ValidationError

from ....application.shared.payment_channel_payloads import (
    deserialize_signature_payment,
)
from ....application.issuer.dtos import (
    CloseChannelRequestDTO,
    GetPaymentChannelRequestDTO,
)
from ....crypto.certificates import (
    load_private_key_from_pem,
    load_public_key_from_der_b64,
    sign_bytes,
    verify_envelope,
    DERB64,
)
from ....domain.vendor.entities import OffChainTx, PaymentChannel
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ....infrastructure.issuer.issuer_client import AsyncIssuerClient
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
        issuer_base_url: str,
        vendor_public_key_der_b64: str,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_channel_repository = payment_channel_repository
        self.issuer_base_url = issuer_base_url
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_payment_channel(self, channel_id: str) -> PaymentChannel:
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
            async with AsyncIssuerClient(self.issuer_base_url) as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_payment_channel(dto)
                channel_data = issuer_channel.model_dump()

                # Safely deserialize using the entity
                payment_channel = PaymentChannel.model_validate(channel_data)

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
        payment_channel: PaymentChannel,
        new_tx: OffChainTx,
        is_first_payment: bool,
    ) -> tuple[int, Optional[OffChainTx], PaymentChannel]:
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
                    stored_tx,
                ) = await self.payment_channel_repository.save_channel_and_initial_payment(
                    payment_channel, new_tx
                )
                if status == 1:
                    return status, stored_tx, payment_channel

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

            status, stored_tx = await self.payment_channel_repository.save_payment(
                payment_channel, new_tx
            )

            if status != 2:
                return status, stored_tx, payment_channel

            # status == 2: vendor cache is missing the channel; fetch from issuer,
            # then cache it and retry the save flow once.
            if attempt == 0:
                payment_channel = await self._verify_payment_channel(channel_id)
                is_first_payment = True
                continue

        # If we get here, something is inconsistent (e.g., channel was verified
        # but still appears missing in storage).
        return status, stored_tx, payment_channel

    async def receive_payment(self, dto: ReceivePaymentDTO) -> OffChainTxResponseDTO:
        """Receive and validate an off-chain payment from a client."""
        # 1) Decode and validate payload (extract channel_id and key fields)
        payload = deserialize_signature_payment(dto.envelope)

        # 2) Get full channel aggregate (lazy load)
        payment_channel = await self.payment_channel_repository.get_by_channel_id(
            payload.channel_id
        )

        # 2.1) If missing, verify with issuer and cache locally (First Payment flow)
        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_payment_channel(payload.channel_id)
            is_first_payment = True

        latest_tx = payment_channel.latest_tx
        prev_cumulative_owed_amount = latest_tx.cumulative_owed_amount if latest_tx else 0

        # 2.2) Ensure the channel remains bound to this vendor
        if payment_channel.vendor_public_key_der_b64 != self.vendor_public_key_der_b64:
            raise ValueError("Payment channel is not for this vendor")

        # 4) Verify client's signature using the channel-bound public key
        client_public_key = load_public_key_from_der_b64(
            DERB64(payment_channel.client_public_key_der_b64)
        )
        verify_envelope(client_public_key, dto.envelope)

        # 5) Idempotency + double spending protection.
        #
        # If the client retries the *exact same* payment (e.g., due to a transient
        # disconnect after the vendor stored the tx but before the client read the
        # response), accept the duplicate and return the stored tx.
        if latest_tx and payload.cumulative_owed_amount == prev_cumulative_owed_amount:
            if (
                dto.envelope.payload_b64 != latest_tx.payload_b64
                or dto.envelope.signature_b64 != latest_tx.client_signature_b64
            ):
                raise ValueError(
                    "Duplicate owed amount with mismatched payload/signature (possible replay attack)"
                )
            return OffChainTxResponseDTO(**latest_tx.model_dump())

        # Otherwise, enforce strictly increasing owed amount.
        if payload.cumulative_owed_amount < prev_cumulative_owed_amount:
            raise ValueError(
                f"Owed amount must be increasing. Got {payload.cumulative_owed_amount}, expected > {prev_cumulative_owed_amount}"
            )

        # 6) Check if the payment channel amount is bigger than the cumulative_owed_amount
        # (Optimistic check for fast failure; authoritative check happens atomically in save_if_valid)
        if payload.cumulative_owed_amount > payment_channel.amount:
            raise ValueError(
                f"Owed amount {payload.cumulative_owed_amount} exceeds payment channel amount {payment_channel.amount}"
            )

        # 7) Create the off-chain transaction object
        off_chain_tx = OffChainTx(
            channel_id=payload.channel_id,
            client_public_key_der_b64=payment_channel.client_public_key_der_b64,
            vendor_public_key_der_b64=payment_channel.vendor_public_key_der_b64,
            cumulative_owed_amount=payload.cumulative_owed_amount,
            payload_b64=dto.envelope.payload_b64,
            client_signature_b64=dto.envelope.signature_b64,
        )

        (
            status,
            stored_tx,
            _payment_channel,
        ) = await self._save_payment_with_retry(
            channel_id=payload.channel_id,
            payment_channel=payment_channel,
            new_tx=off_chain_tx,
            is_first_payment=is_first_payment,
        )

        if status == 1:
            # Success: transaction was stored
            if stored_tx is None:
                raise RuntimeError(
                    "Unexpected: save_payment returned success but no transaction"
                )
            return OffChainTxResponseDTO(**stored_tx.model_dump())
        elif status == 0:
            # Rejected: amount was not greater than current or exceeded channel capacity
            current_amt = stored_tx.cumulative_owed_amount if stored_tx else "unknown"
            raise ValueError(
                f"Owed amount must be increasing (race detected). Got {payload.cumulative_owed_amount}, DB has {current_amt}"
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
        if channel.is_closed:
            return None

        latest_tx = channel.latest_tx
        if not latest_tx:
            raise ValueError("No off-chain payments received for this channel")

        # 3) Vendor signs the exact same payload bytes the client signed in the last payment.
        # The payload is "thin" (channel_id + cumulative_owed_amount). Issuer infers keys from channel state.
        payload_bytes = base64.b64decode(latest_tx.payload_b64)

        # 4) Vendor signs the same payload bytes (detached signature)
        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_close_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        # 5) Send close request to issuer
        request_dto = CloseChannelRequestDTO(
            close_payload_b64=latest_tx.payload_b64,
            client_close_signature_b64=latest_tx.client_signature_b64,
            vendor_close_signature_b64=vendor_close_signature_b64,
        )

        async with AsyncIssuerClient(self.issuer_base_url) as issuer_client:
            await issuer_client.settle_payment_channel(
                latest_tx.channel_id,
                request_dto,
            )

        # 6) Mark closed locally
        await self.payment_channel_repository.mark_closed(
            channel_id=dto.channel_id,
            close_payload_b64=latest_tx.payload_b64,
            client_close_signature_b64=latest_tx.client_signature_b64,
            amount=channel.amount,
            balance=latest_tx.cumulative_owed_amount,
            vendor_close_signature_b64=vendor_close_signature_b64,
        )

        return None
