"""Use cases for the vendor PayWord (hash-chain) flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.payword_dtos import PaywordSettlementRequestDTO
from ....application.shared.payword_payloads import PaywordSettlementPayload
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ...shared.payword_scheme import PaywordCryptoScheme
from ....domain.shared.crypto_proof import CryptoProof
from ....domain.shared import IssuerClientFactory
from ....domain.shared.proof_reference import PaymentScheme, ProofReference
from ....domain.vendor.entities import PaymentChannel, PaymentState
from ....domain.vendor.payment_repository import PaymentRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..payword_dtos import PaywordPaymentResponseDTO, ReceivePaywordPaymentDTO
from .payment_validators import (
    check_proof_reference_duplicate,
    validate_proof_reference,
)


class PaywordPaymentService:
    """Service for handling PayWord payments and settlement."""

    def __init__(
        self,
        payment_repository: PaymentRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        crypto_scheme: PaywordCryptoScheme,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_repository = payment_repository
        self.issuer_client_factory = issuer_client_factory
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.crypto_scheme = crypto_scheme
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_payword_channel(self, channel_id: str) -> PaymentChannel:
        """Fetch and validate the channel from the issuer, return as unified PaymentChannel."""
        try:
            async with self.issuer_client_factory() as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_payword_payment_channel(dto)

                if issuer_channel.is_closed:
                    raise ValueError("Payment channel is closed")
                if (
                    issuer_channel.vendor_public_key_der_b64
                    != self.vendor_public_key_der_b64
                ):
                    raise ValueError("Payment channel is not for this vendor")

                return PaymentChannel(
                    channel_id=issuer_channel.channel_id,
                    client_public_key_der_b64=issuer_channel.client_public_key_der_b64,
                    vendor_public_key_der_b64=issuer_channel.vendor_public_key_der_b64,
                    salt_b64=issuer_channel.salt_b64,
                    amount=issuer_channel.amount,
                    balance=issuer_channel.balance,
                    is_closed=issuer_channel.is_closed,
                    created_at=issuer_channel.created_at,
                    commitment=issuer_channel.payword_root_b64,
                    scheme=PaymentScheme.PAYWORD,
                    max_steps=issuer_channel.payword_max_k,
                    unit_value=issuer_channel.payword_unit_value,
                )

        except HttpResponseError as e:
            if e.response.status_code == 404:
                raise ValueError("Payment channel not found on issuer")
            raise ValueError(f"Failed to verify payment channel: {e}")
        except HttpRequestError as e:
            raise ValueError(f"Could not connect to issuer: {e}")
        except ValidationError as e:
            raise ValueError(f"Invalid payment channel data from issuer: {e}")

    async def receive_payword_payment(
        self, channel_id: str, dto: ReceivePaywordPaymentDTO
    ) -> PaywordPaymentResponseDTO:
        """Receive and validate a PayWord payment from a client."""
        channel, prev_state = await self.payment_repository.get_channel_and_state(
            channel_id
        )

        is_first_payment = False
        if not channel:
            channel = await self._verify_payword_channel(channel_id)
            is_first_payment = True

        if channel.is_closed:
            raise ValueError("Payment channel is closed")

        new_ref = ProofReference(value=dto.k)
        prev_ref = (
            ProofReference(value=channel.last_proof_reference)
            if channel.last_proof_reference is not None
            else None
        )
        cumulative_owed = new_ref.value * channel.unit_value

        # Idempotency check (token_b64 is the fingerprint for PayWord)
        prev_fingerprint = prev_state.proof_fingerprint if prev_state else None
        is_dup = check_proof_reference_duplicate(
            new_ref=new_ref,
            new_fingerprint=dto.token_b64,
            prev_ref=prev_ref,
            prev_fingerprint=prev_fingerprint,
        )
        if is_dup:
            assert prev_state is not None
            return PaywordPaymentResponseDTO(
                channel_id=channel_id,
                k=prev_state.proof_reference,
                cumulative_owed_amount=prev_state.proof_reference * channel.unit_value,
                created_at=prev_state.created_at,
            )

        validate_proof_reference(
            new_ref=new_ref, prev_ref=prev_ref, max_steps=channel.max_steps
        )
        if cumulative_owed > channel.amount:
            raise ValueError(
                f"Cumulative owed {cumulative_owed} exceeds channel amount {channel.amount}"
            )

        # Build verify proof (includes incremental fields)
        verify_proof = CryptoProof(
            scheme=PaymentScheme.PAYWORD,
            data={
                "k": dto.k,
                "token_b64": dto.token_b64,
                "prev_token_b64": prev_fingerprint,
                "delta_k": (dto.k - prev_ref.value) if prev_ref else None,
            },
        )
        if not self.crypto_scheme.verify(channel.commitment, new_ref, verify_proof):
            if prev_ref is None:
                raise ValueError("Invalid PayWord token for k (root mismatch)")
            raise ValueError("Invalid PayWord token for k (incremental mismatch)")

        new_state = PaymentState(
            channel_id=channel_id,
            proof_reference=dto.k,
            cumulative_owed=cumulative_owed,
            proof_fingerprint=dto.token_b64,
            created_at=datetime.now(timezone.utc),
        )
        # Storage proof: only persistent fields
        store_proof = CryptoProof(
            scheme=PaymentScheme.PAYWORD,
            data={"token_b64": dto.token_b64},
        )

        if is_first_payment:
            (
                status,
                stored_state,
            ) = await self.payment_repository.save_channel_and_initial_state(
                channel, new_state, store_proof
            )
        else:
            status, stored_state = await self.payment_repository.save_payment(
                channel, new_state, store_proof
            )

        if status == 1:
            if stored_state is None:
                raise RuntimeError("Unexpected: save returned success but no state")
            return PaywordPaymentResponseDTO(
                channel_id=channel_id,
                k=stored_state.proof_reference,
                cumulative_owed_amount=cumulative_owed,
                created_at=stored_state.created_at,
            )
        elif status == 0:
            # Race: re-fetch and retry once
            channel2, _ = await self.payment_repository.get_channel_and_state(
                channel_id
            )
            if not channel2:
                raise RuntimeError(
                    "Race condition: channel disappeared after save collision"
                )
            status2, stored_state2 = await self.payment_repository.save_payment(
                channel2, new_state, store_proof
            )
            if status2 == 1 and stored_state2:
                return PaywordPaymentResponseDTO(
                    channel_id=channel_id,
                    k=stored_state2.proof_reference,
                    cumulative_owed_amount=cumulative_owed,
                    created_at=stored_state2.created_at,
                )
            current_k = stored_state2.proof_reference if stored_state2 else "unknown"
            raise ValueError(
                f"PayWord k must be increasing (race detected). Got {dto.k}, DB has {current_k}"
            )
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, channel_id: str, dto: CloseChannelDTO) -> None:
        """Settle a PayWord channel by submitting the latest proof to the issuer."""
        if dto.channel_id != channel_id:
            raise ValueError("Channel ID mismatch between path and payload")

        channel = await self.payment_repository.get_channel(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        state = await self.payment_repository.get_state(channel_id)
        if not state:
            raise ValueError("No PayWord payments received for this channel")

        # token_b64 is the fingerprint for PayWord
        raw_proof = await self.payment_repository.get_crypto_proof_raw(channel_id)
        token_b64: Optional[str] = None
        if raw_proof:
            proof_data = json.loads(raw_proof)
            token_b64 = proof_data.get("token_b64")
        if not token_b64:
            token_b64 = state.proof_fingerprint

        cumulative_owed = state.proof_reference * channel.unit_value
        if cumulative_owed > channel.amount:
            raise ValueError("Invalid owed amount")

        settlement_payload = PaywordSettlementPayload(
            channel_id=channel_id,
            k=state.proof_reference,
            token_b64=token_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaywordSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            k=state.proof_reference,
            token_b64=token_b64,
            vendor_signature_b64=vendor_signature_b64,
        )

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_payword_payment_channel(channel_id, request_dto)

        await self.payment_repository.mark_closed(
            channel_id=channel_id,
            amount=channel.amount,
            balance=cumulative_owed,
        )
