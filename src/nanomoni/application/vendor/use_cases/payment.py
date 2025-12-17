"""Use cases for the vendor application layer."""

from __future__ import annotations

from typing import Optional

import httpx
from pydantic import ValidationError

from ....application.shared.payment_channel_payloads import (
    CloseChannelRequestPayload,
    deserialize_off_chain_tx,
)
from ....application.issuer.dtos import (
    CloseChannelRequestDTO,
    GetPaymentChannelRequestDTO,
)
from ....crypto.certificates import (
    json_to_bytes,
    load_private_key_from_pem,
    load_public_key_from_der_b64,
    sign_bytes,
    verify_envelope,
    DERB64,
)
from ....domain.vendor.entities import OffChainTx, PaymentChannel
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
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

    async def _verify_payment_channel(self, computed_id: str) -> PaymentChannel:
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
                dto = GetPaymentChannelRequestDTO(computed_id=computed_id)
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

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError("Payment channel not found on issuer")
            raise ValueError(f"Failed to verify payment channel: {e}")
        except httpx.RequestError as e:
            raise ValueError(f"Could not connect to issuer: {e}")
        except ValidationError as e:
            raise ValueError(f"Invalid payment channel data from issuer: {e}")

    async def receive_payment(self, dto: ReceivePaymentDTO) -> OffChainTxResponseDTO:
        """Receive and validate an off-chain payment from a client."""
        # 1) Decode and validate payload (extract computed_id and key fields)
        payload = deserialize_off_chain_tx(dto.envelope)

        # 1.1) Ensure this payment is explicitly addressed to this vendor
        if payload.vendor_public_key_der_b64 != self.vendor_public_key_der_b64:
            raise ValueError("Payment not addressed to this vendor")

        # 2) Get full channel aggregate (lazy load)
        payment_channel = await self.payment_channel_repository.get_by_computed_id(
            payload.computed_id
        )

        # 2.1) If missing, verify with issuer and cache locally (First Payment flow)
        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_payment_channel(payload.computed_id)
            is_first_payment = True

        latest_tx = payment_channel.latest_tx
        prev_owed_amount = latest_tx.owed_amount if latest_tx else 0

        # 2.2) Ensure the channel remains bound to this vendor
        if payment_channel.vendor_public_key_der_b64 != self.vendor_public_key_der_b64:
            raise ValueError("Payment channel is not for this vendor")

        # 3) Consistency checks between payload and channel keys
        if (
            payload.client_public_key_der_b64
            != payment_channel.client_public_key_der_b64
        ):
            raise ValueError("Mismatched client public key for channel")

        if (
            payload.vendor_public_key_der_b64
            != payment_channel.vendor_public_key_der_b64
        ):
            raise ValueError("Mismatched vendor public key for channel")

        # 4) Verify client's signature using the channel-bound public key
        client_public_key = load_public_key_from_der_b64(
            DERB64(payment_channel.client_public_key_der_b64)
        )
        verify_envelope(client_public_key, dto.envelope)

        # 5) Check for double spending - owed amount must be increasing
        if payload.owed_amount <= prev_owed_amount:
            raise ValueError(
                f"Owed amount must be increasing. Got {payload.owed_amount}, expected > {prev_owed_amount}"
            )

        # 6) Check if the payment channel amount is bigger than the owed_amount
        # (Optimistic check for fast failure; authoritative check happens atomically in save_if_valid)
        if payload.owed_amount > payment_channel.amount:
            raise ValueError(
                f"Owed amount {payload.owed_amount} exceeds payment channel amount {payment_channel.amount}"
            )

        # 7) Create the off-chain transaction object
        off_chain_tx = OffChainTx(
            computed_id=payload.computed_id,
            client_public_key_der_b64=payment_channel.client_public_key_der_b64,
            vendor_public_key_der_b64=payment_channel.vendor_public_key_der_b64,
            owed_amount=payload.owed_amount,
            payload_b64=dto.envelope.payload_b64,
            client_signature_b64=dto.envelope.signature_b64,
        )

        status: int = 0
        stored_tx: Optional[OffChainTx] = None

        if is_first_payment:
            # Atomic save of channel metadata + first transaction
            (
                status,
                stored_tx,
            ) = await self.payment_channel_repository.save_channel_and_initial_payment(
                payment_channel, off_chain_tx
            )
            if status == 0:
                # Race condition: Channel was created by another concurrent request.
                # Fallback to standard save_payment flow.
                is_first_payment = False
                # Refresh aggregate to get the tx that beat us
                payment_channel = (
                    await self.payment_channel_repository.get_by_computed_id(
                        payload.computed_id
                    )
                )
                if not payment_channel:
                    # Should not happen if save_channel_and_initial_payment failed due to existence
                    raise RuntimeError(
                        "Race condition handling failed: channel missing after collision"
                    )

        if not is_first_payment:
            # Standard flow: update existing channel
            status, stored_tx = await self.payment_channel_repository.save_payment(
                payment_channel, off_chain_tx
            )

            if status == 2:
                # Channel missing locally (edge case: evicted? or race on delete?)
                # Verify with issuer and create cache, then retry
                payment_channel = await self._verify_payment_channel(
                    payload.computed_id
                )
                # Try atomic init again (since it's missing now)
                (
                    status,
                    stored_tx,
                ) = await self.payment_channel_repository.save_channel_and_initial_payment(
                    payment_channel, off_chain_tx
                )
                # If that fails again, it's a very tight loop of creation/deletion, or just simple race.
                # We can retry save_payment one last time if init failed.
                if status == 0:
                    payment_channel = (
                        await self.payment_channel_repository.get_by_computed_id(
                            payload.computed_id
                        )
                    )
                    if payment_channel:
                        (
                            status,
                            stored_tx,
                        ) = await self.payment_channel_repository.save_payment(
                            payment_channel, off_chain_tx
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
            current_amt = stored_tx.owed_amount if stored_tx else "unknown"
            raise ValueError(
                f"Owed amount must be increasing (race detected). Got {payload.owed_amount}, DB has {current_amt}"
            )
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def close_channel(self, dto: CloseChannelDTO) -> None:
        """Close a payment channel by sending the latest off-chain tx to issuer and marking local channel closed."""

        # 1) Fetch channel aggregate (includes latest tx)
        channel = await self.payment_channel_repository.get_by_computed_id(
            dto.computed_id
        )

        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        latest_tx = channel.latest_tx
        if not latest_tx:
            raise ValueError("No off-chain payments received for this channel")

        # 3) Build close payload from latest tx
        close_payload = CloseChannelRequestPayload(
            computed_id=latest_tx.computed_id,
            client_public_key_der_b64=latest_tx.client_public_key_der_b64,
            vendor_public_key_der_b64=latest_tx.vendor_public_key_der_b64,
            owed_amount=latest_tx.owed_amount,
        )
        payload_bytes = json_to_bytes(close_payload.model_dump())

        # 4) Vendor signs client's payload bytes
        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_close_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        # 5) Send close request to issuer
        request_dto = CloseChannelRequestDTO(
            client_public_key_der_b64=latest_tx.client_public_key_der_b64,
            vendor_public_key_der_b64=latest_tx.vendor_public_key_der_b64,
            close_payload_b64=latest_tx.payload_b64,
            client_close_signature_b64=latest_tx.client_signature_b64,
            vendor_close_signature_b64=vendor_close_signature_b64,
        )

        async with AsyncIssuerClient(self.issuer_base_url) as issuer_client:
            await issuer_client.close_payment_channel(
                latest_tx.computed_id,
                request_dto,
            )

        # 6) Mark closed locally
        await self.payment_channel_repository.mark_closed(
            computed_id=dto.computed_id,
            close_payload_b64=latest_tx.payload_b64,
            client_close_signature_b64=latest_tx.client_signature_b64,
            amount=channel.amount,
            balance=latest_tx.owed_amount,
            vendor_close_signature_b64=vendor_close_signature_b64,
        )

        return None
