"""Use cases for the vendor application layer."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import httpx
from pydantic import ValidationError

from ....crypto.certificates import (
    CloseChannelRequestPayload,
    deserialize_off_chain_tx,
    json_to_bytes,
    load_private_key_from_pem,
    load_public_key_from_der_b64,
    sign_bytes,
    verify_envelope,
    DERB64,
)
from ....domain.vendor.entities import OffChainTx, PaymentChannel
from ....domain.vendor.off_chain_tx_repository import OffChainTxRepository
from ....domain.vendor.payment_channel_repository import PaymentChannelRepository
from ..dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
)


class PaymentService:
    """Service for handling off-chain payment transactions."""

    def __init__(
        self,
        off_chain_tx_repository: OffChainTxRepository,
        payment_channel_repository: PaymentChannelRepository,
        issuer_base_url: str,
        vendor_public_key_der_b64: str,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.off_chain_tx_repository = off_chain_tx_repository
        self.payment_channel_repository = payment_channel_repository
        self.issuer_base_url = issuer_base_url
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_payment_channel(self, computed_id: str) -> PaymentChannel:
        """
        Verify that the payment channel exists on the issuer side, stores it,
        and returns the channel entity.
        """
        try:
            # TODO
            # Extract this request as a client on the infrastructure folder
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.issuer_base_url}/issuer/payment-channel/{computed_id}"
                )
                response.raise_for_status()
                channel_data = response.json()

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

                # Store the incoming payment channel
                await self.payment_channel_repository.create(payment_channel)

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
        # 1) Verify client's signature
        client_public_key = load_public_key_from_der_b64(
            DERB64(dto.client_public_key_der_b64)
        )
        verify_envelope(client_public_key, dto.envelope)

        # 2) Decode and validate payload
        payload = deserialize_off_chain_tx(dto.envelope)

        # 3) Get the latest transaction for this payment channel to check for double spending
        latest_tx = await self.off_chain_tx_repository.get_latest_by_computed_id(
            payload.computed_id
        )
        prev_owed_amount = latest_tx.owed_amount if latest_tx else 0

        # 3.1) If this is the first payment for this channel, verify it exists on issuer
        payment_channel: Optional[PaymentChannel] = None
        if latest_tx is None:
            payment_channel = await self._verify_payment_channel(payload.computed_id)
        else:
            payment_channel = await self.payment_channel_repository.get_by_computed_id(
                payload.computed_id
            )

        if not payment_channel:
            raise ValueError("Payment channel could not be found or verified.")

        # 4) Check for double spending - owed amount must be increasing
        if payload.owed_amount <= prev_owed_amount:
            raise ValueError(
                f"Owed amount must be increasing. Got {payload.owed_amount}, expected > {prev_owed_amount}"
            )

        # 5) Check if the payment channel amount is bigger than the owed_amount
        if payload.owed_amount > payment_channel.amount:
            raise ValueError(
                f"Owed amount {payload.owed_amount} exceeds payment channel amount {payment_channel.amount}"
            )

        # 6) Create and store the off-chain transaction
        off_chain_tx = OffChainTx(
            computed_id=payload.computed_id,
            client_public_key_der_b64=payload.client_public_key_der_b64,
            vendor_public_key_der_b64=payload.vendor_public_key_der_b64,
            owed_amount=payload.owed_amount,
            payload_b64=dto.envelope.payload_b64,
            client_signature_b64=dto.envelope.signature_b64,
        )

        # Save to repository
        # Option 1: append
        # created_tx = await self.off_chain_tx_repository.create(off_chain_tx)
        # Option 2: override the last one - optimize storage by keeping only the latest
        if latest_tx:
            # Overwrite the existing transaction with new data, keeping the same ID
            created_tx = await self.off_chain_tx_repository.overwrite(
                latest_tx.id, off_chain_tx
            )
        else:
            # Create new transaction if this is the first one for this computed_id
            created_tx = await self.off_chain_tx_repository.create(off_chain_tx)

        return OffChainTxResponseDTO(**created_tx.model_dump())

    async def get_payment_by_id(self, tx_id: UUID) -> Optional[OffChainTxResponseDTO]:
        """Get an off-chain transaction by ID."""
        tx = await self.off_chain_tx_repository.get_by_id(tx_id)
        if not tx:
            return None
        return OffChainTxResponseDTO(**tx.model_dump())

    async def get_payments_by_channel(
        self, computed_id: str
    ) -> List[OffChainTxResponseDTO]:
        """Get all payments for a payment channel."""
        txs = await self.off_chain_tx_repository.get_by_computed_id(computed_id)
        return [OffChainTxResponseDTO(**tx.model_dump()) for tx in txs]

    async def close_channel(self, dto: CloseChannelDTO) -> None:
        """Close a payment channel by sending the latest off-chain tx to issuer and marking local channel closed."""

        # 1) Load channel and ensure it exists locally
        channel = await self.payment_channel_repository.get_by_computed_id(
            dto.computed_id
        )
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        # 2) Get latest off-chain tx
        latest_tx = await self.off_chain_tx_repository.get_latest_by_computed_id(
            dto.computed_id
        )
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
        request_body = {
            "client_public_key_der_b64": latest_tx.client_public_key_der_b64,
            "vendor_public_key_der_b64": latest_tx.vendor_public_key_der_b64,
            "close_payload_b64": latest_tx.payload_b64,
            "client_close_signature_b64": latest_tx.client_signature_b64,
            "vendor_close_signature_b64": vendor_close_signature_b64,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.issuer_base_url}/issuer/payment-channel/close",
                json=request_body,
            )
            resp.raise_for_status()

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
