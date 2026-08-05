"""Vendor use case: standard PayTree payments (full leaf→root proof)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.paytree_dtos import PaytreeSettlementRequestDTO
from ....application.shared.paytree_payloads import PaytreeSettlementPayload
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ...shared.paytree_scheme import PaytreeStdCryptoScheme
from ....domain.shared.crypto_proof import CryptoProof
from ....domain.shared import IssuerClientFactory
from ....domain.shared.proof_reference import PaymentScheme, ProofReference
from ....domain.vendor.entities import PaymentChannel, PaymentState
from ....domain.vendor.payment_repository import PaymentRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..paytree_dtos import PaytreePaymentResponseDTO, ReceivePaytreeStdPaymentDTO
from .payment_validators import (
    check_proof_reference_duplicate,
    validate_proof_reference,
)


async def _fetch_and_validate_channel(
    channel_id: str,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
) -> PaymentChannel:
    """Fetch and validate channel from the issuer (std endpoint)."""
    try:
        async with issuer_client_factory() as issuer_client:
            dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
            issuer_channel = await issuer_client.get_paytree_std_payment_channel(dto)

            if issuer_channel.is_closed:
                raise ValueError("Payment channel is closed")
            if issuer_channel.vendor_public_key_der_b64 != vendor_public_key_der_b64:
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
                commitment=issuer_channel.paytree_root_b64,
                scheme=PaymentScheme.PAYTREE,
                max_steps=issuer_channel.paytree_max_i,
                unit_value=issuer_channel.paytree_unit_value,
            )

    except HttpResponseError as e:
        if e.response.status_code == 404:
            raise ValueError("Payment channel not found on issuer")
        raise ValueError(f"Failed to verify payment channel: {e}")
    except HttpRequestError as e:
        raise ValueError(f"Could not connect to issuer: {e}")
    except ValidationError as e:
        raise ValueError(f"Invalid payment channel data from issuer: {e}")


class PaytreeStdPaymentService:
    """Handles standard (full-proof) PayTree payments and settlement."""

    def __init__(
        self,
        payment_repository: PaymentRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        crypto_scheme: PaytreeStdCryptoScheme,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_repository = payment_repository
        self.issuer_client_factory = issuer_client_factory
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.crypto_scheme = crypto_scheme
        self.vendor_private_key_pem = vendor_private_key_pem

    async def receive_payment(
        self,
        channel_id: str,
        dto: ReceivePaytreeStdPaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        channel, prev_state = await self.payment_repository.get_channel_and_state(
            channel_id
        )

        is_first_payment = False
        if not channel:
            channel = await _fetch_and_validate_channel(
                channel_id, self.issuer_client_factory, self.vendor_public_key_der_b64
            )
            is_first_payment = True
        if channel.is_closed:
            raise ValueError("Payment channel is closed")

        new_ref = ProofReference(value=dto.i)
        prev_ref = (
            ProofReference(value=channel.last_proof_reference)
            if channel.last_proof_reference is not None
            else None
        )
        cumulative_owed = new_ref.value * channel.unit_value

        prev_fingerprint = prev_state.proof_fingerprint if prev_state else None
        is_dup = check_proof_reference_duplicate(
            new_ref=new_ref,
            new_fingerprint=dto.leaf_b64,
            prev_ref=prev_ref,
            prev_fingerprint=prev_fingerprint,
        )
        if is_dup:
            if not self.crypto_scheme.verify(
                channel.commitment,
                new_ref,
                CryptoProof(
                    scheme=PaymentScheme.PAYTREE,
                    data={
                        "leaf_b64": dto.leaf_b64,
                        "siblings_b64": dto.siblings_b64,
                        "max_steps": channel.max_steps,
                    },
                ),
            ):
                raise ValueError("Invalid PayTree proof (root mismatch)")
            assert prev_state is not None
            return PaytreePaymentResponseDTO(
                channel_id=channel_id,
                i=dto.i,
                cumulative_owed_amount=cumulative_owed,
                created_at=prev_state.created_at,
            )

        validate_proof_reference(
            new_ref=new_ref, prev_ref=prev_ref, max_steps=channel.max_steps
        )
        if cumulative_owed > channel.amount:
            raise ValueError(
                f"Cumulative owed {cumulative_owed} exceeds channel amount {channel.amount}"
            )

        verify_proof = CryptoProof(
            scheme=PaymentScheme.PAYTREE,
            data={
                "leaf_b64": dto.leaf_b64,
                "siblings_b64": dto.siblings_b64,
                "max_steps": channel.max_steps,
            },
        )
        if not self.crypto_scheme.verify(channel.commitment, new_ref, verify_proof):
            raise ValueError("Invalid PayTree proof (root mismatch)")

        new_state = PaymentState(
            channel_id=channel_id,
            proof_reference=dto.i,
            cumulative_owed=cumulative_owed,
            proof_fingerprint=dto.leaf_b64,
            created_at=datetime.now(timezone.utc),
        )
        store_proof = CryptoProof(
            scheme=PaymentScheme.PAYTREE,
            data={"leaf_b64": dto.leaf_b64, "siblings_b64": dto.siblings_b64},
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
            return PaytreePaymentResponseDTO(
                channel_id=channel_id,
                i=stored_state.proof_reference,
                cumulative_owed_amount=cumulative_owed,
                created_at=stored_state.created_at,
            )
        elif status == 0:
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
                return PaytreePaymentResponseDTO(
                    channel_id=channel_id,
                    i=stored_state2.proof_reference,
                    cumulative_owed_amount=cumulative_owed,
                    created_at=stored_state2.created_at,
                )
            current_ref = stored_state2.proof_reference if stored_state2 else "unknown"
            raise ValueError(
                f"PayTree i must be increasing (race detected). Got {dto.i}, DB has {current_ref}"
            )
        elif status == 3:
            raise ValueError("PayTree i exceeds max_i for this channel")
        else:
            raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        channel_id = dto.channel_id
        channel = await self.payment_repository.get_channel(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        state = await self.payment_repository.get_state(channel_id)
        leaf_b64: Optional[str] = None
        siblings_b64: Optional[list[str]] = None

        if state:
            raw_proof = await self.payment_repository.get_crypto_proof_raw(channel_id)
            if raw_proof:
                proof_data = json.loads(raw_proof)
                leaf_b64 = proof_data.get("leaf_b64")
                siblings_b64 = proof_data.get("siblings_b64")

        if not state or leaf_b64 is None or siblings_b64 is None:
            raise ValueError("No complete PayTree proof available for settlement")

        cumulative_owed = state.proof_reference * channel.unit_value
        if cumulative_owed > channel.amount:
            raise ValueError("Invalid owed amount")

        settlement_payload = PaytreeSettlementPayload(
            channel_id=channel_id,
            i=state.proof_reference,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaytreeSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            i=state.proof_reference,
            leaf_b64=leaf_b64,
            siblings_b64=siblings_b64,
            vendor_signature_b64=vendor_signature_b64,
        )

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_paytree_std_payment_channel(
                channel_id, request_dto
            )

        await self.payment_repository.mark_closed(
            channel_id=channel_id,
            amount=channel.amount,
            balance=cumulative_owed,
        )
