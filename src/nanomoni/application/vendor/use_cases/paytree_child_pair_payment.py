"""Vendor use case: PayTree child-pair payments (heap-indexed child reveal).

Per payment k, the client reveals the two children of node k (Eytzinger
index); the vendor accepts iff H(left, right) equals the hash it already
knows for node k (starting from the root at k=1), then learns nodes 2k and
2k+1. Unlike first-opt, node keys are simply `str(k)` — no depth/level math
is needed to address the sparse node store.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from ....application.issuer.dtos import GetPaymentChannelRequestDTO
from ....application.issuer.paytree_dtos import PaytreeChildPairSettlementRequestDTO
from ....application.shared.paytree_payloads import PaytreeChildPairSettlementPayload
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import load_private_key_from_pem, sign_bytes
from ....protocol import build_child_pair_close_proof
from ....crypto.paytree import b64_to_bytes, bytes_to_b64
from ...shared.paytree_scheme import PaytreeChildPairCryptoScheme
from ....domain.shared.crypto_proof import CryptoProof
from ....domain.shared import IssuerClientFactory
from ....domain.shared.proof_reference import PaymentScheme, ProofReference
from ....domain.vendor.entities import PaymentChannel, PaymentState
from ....domain.vendor.merkle_node_repository import MerkleNodeRepository
from ....domain.vendor.payment_repository import PaymentRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..paytree_dtos import (
    PaytreeChildPairPaymentResponseDTO,
    ReceivePaytreeChildPairPaymentDTO,
)
from .payment_validators import (
    check_proof_reference_duplicate,
    validate_proof_reference,
)

ROOT_KEY = "1"


def _fingerprint(left_b64: str, right_b64: str) -> str:
    return f"{left_b64}:{right_b64}"


async def _fetch_and_validate_channel(
    channel_id: str,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
) -> PaymentChannel:
    """Fetch and validate channel from the issuer (child-pair endpoint)."""
    try:
        async with issuer_client_factory() as issuer_client:
            dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
            issuer_channel = await issuer_client.get_paytree_child_pair_payment_channel(
                dto
            )

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
                scheme=PaymentScheme.PAYTREE_CHILD_PAIR,
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


class PaytreeChildPairPaymentService:
    """Handles child-pair PayTree payments and settlement."""

    def __init__(
        self,
        payment_repository: PaymentRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        crypto_scheme: PaytreeChildPairCryptoScheme,
        node_repo: MerkleNodeRepository,
        *,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_repository = payment_repository
        self.issuer_client_factory = issuer_client_factory
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.crypto_scheme = crypto_scheme
        self.node_repo = node_repo
        self.vendor_private_key_pem = vendor_private_key_pem

    async def receive_payment(
        self,
        channel_id: str,
        dto: ReceivePaytreeChildPairPaymentDTO,
    ) -> PaytreeChildPairPaymentResponseDTO:
        node_repo = self.node_repo
        k_key = str(dto.k)

        channel_json, nodes = await node_repo.get_channel_and_nodes(
            channel_id, [ROOT_KEY, k_key]
        )

        if not channel_json:
            payment_channel = await _fetch_and_validate_channel(
                channel_id, self.issuer_client_factory, self.vendor_public_key_der_b64
            )
            if payment_channel.commitment:
                await node_repo.merge_nodes(
                    channel_id, {ROOT_KEY: payment_channel.commitment}
                )
                nodes[ROOT_KEY] = payment_channel.commitment
        else:
            payment_channel = PaymentChannel.model_validate_json(channel_json)
            if not nodes.get(ROOT_KEY) and payment_channel.commitment:
                await node_repo.merge_nodes(
                    channel_id, {ROOT_KEY: payment_channel.commitment}
                )
                nodes[ROOT_KEY] = payment_channel.commitment

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")

        new_ref = ProofReference(value=dto.k)
        prev_ref = (
            ProofReference(value=payment_channel.last_proof_reference)
            if payment_channel.last_proof_reference is not None
            else None
        )
        cumulative_owed = new_ref.value * payment_channel.unit_value
        fingerprint = _fingerprint(dto.left_b64, dto.right_b64)

        if prev_ref is not None and new_ref.value <= prev_ref.value:
            prev_state = await self.payment_repository.get_state(channel_id)
            prev_fingerprint = prev_state.proof_fingerprint if prev_state else None
            is_dup = check_proof_reference_duplicate(
                new_ref=new_ref,
                new_fingerprint=fingerprint,
                prev_ref=prev_ref,
                prev_fingerprint=prev_fingerprint,
            )
            if is_dup:
                known_parent_b64 = nodes.get(k_key, "")
                if not known_parent_b64 or not self.crypto_scheme.verify(
                    known_parent_b64, dto.left_b64, dto.right_b64
                ):
                    raise ValueError("Invalid PayTree child-pair proof")
                created_at = (
                    prev_state.created_at if prev_state else datetime.now(timezone.utc)
                )
                return PaytreeChildPairPaymentResponseDTO(
                    channel_id=channel_id,
                    k=dto.k,
                    cumulative_owed_amount=cumulative_owed,
                    created_at=created_at,
                )
            raise ValueError(
                f"PayTree k must be increasing. Got {dto.k}, channel has {prev_ref.value}"
            )

        validate_proof_reference(
            new_ref=new_ref, prev_ref=prev_ref, max_steps=payment_channel.max_steps
        )
        if cumulative_owed > payment_channel.amount:
            raise ValueError(
                f"Cumulative owed {cumulative_owed} exceeds channel amount {payment_channel.amount}"
            )

        # The parent hash must come from a previously verified node (or the
        # channel's own commitment, seeded at k=1) — never fall back to
        # unverified client input.
        known_parent_b64 = nodes.get(k_key, "")
        if not known_parent_b64:
            raise ValueError(
                f"Unknown parent node for k={dto.k}; payments must reveal children "
                "of an already-verified node, in increasing k order"
            )

        if not self.crypto_scheme.verify(known_parent_b64, dto.left_b64, dto.right_b64):
            raise ValueError("Invalid PayTree child-pair proof (verification failed)")

        node_updates = self.crypto_scheme.build_node_updates(
            dto.k, dto.left_b64, dto.right_b64
        )

        created_at = datetime.now(timezone.utc)
        new_state = PaymentState(
            channel_id=channel_id,
            proof_reference=dto.k,
            cumulative_owed=cumulative_owed,
            proof_fingerprint=fingerprint,
            created_at=created_at,
        )
        store_proof = CryptoProof(
            scheme=PaymentScheme.PAYTREE_CHILD_PAIR,
            data={"left_b64": dto.left_b64, "right_b64": dto.right_b64},
        )

        payment_channel.last_proof_reference = dto.k
        channel_json_updated = payment_channel.model_dump_json()
        state_json = new_state.model_dump_json()
        proof_json = json.dumps(
            {"scheme": store_proof.scheme.value, **store_proof.data}
        )

        status, stored_ref = await node_repo.save_nodes_and_payment(
            channel_id=channel_id,
            node_updates=node_updates,
            new_ref=dto.k,
            channel_json=channel_json_updated,
            state_json=state_json,
            proof_json=proof_json,
            is_closed=payment_channel.is_closed,
            created_at_ts=payment_channel.created_at.timestamp(),
        )

        if status == 1:
            return PaytreeChildPairPaymentResponseDTO(
                channel_id=channel_id,
                k=dto.k,
                cumulative_owed_amount=cumulative_owed,
                created_at=created_at,
            )
        if status == 0:
            raise ValueError(
                f"PayTree k must be increasing (race detected). Got {dto.k}, "
                f"channel has {stored_ref}"
            )
        if status == 3:
            raise ValueError("PayTree k exceeds max_k for this channel")
        raise RuntimeError(f"Unexpected result from atomic save: status={status}")

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        channel_id = dto.channel_id
        channel = await self.payment_repository.get_channel(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            return None

        state = await self.payment_repository.get_state(channel_id)
        if not state:
            raise ValueError("No complete PayTree proof available for settlement")

        k = state.proof_reference
        cumulative_owed = k * channel.unit_value
        if cumulative_owed > channel.amount:
            raise ValueError("Invalid owed amount")

        # Fetch every node needed to walk from k's children up to (but not
        # including) the root: str(2k), str(2k+1), then str(sibling) at each
        # level on the way up.
        keys_needed = [str(2 * k), str(2 * k + 1)]
        current = k
        while current != 1:
            keys_needed.append(str(current ^ 1))
            current //= 2

        nodes_b64 = await self.node_repo.get_nodes(channel_id, keys_needed)
        try:
            known: dict[int, bytes] = {
                int(key): b64_to_bytes(value) for key, value in nodes_b64.items()
            }
            left, right, siblings = build_child_pair_close_proof(k, known)
        except KeyError:
            raise ValueError("No complete PayTree proof available for settlement")

        left_b64 = bytes_to_b64(left)
        right_b64 = bytes_to_b64(right)
        siblings_b64 = [bytes_to_b64(s) for s in siblings]

        settlement_payload = PaytreeChildPairSettlementPayload(
            channel_id=channel_id,
            k=k,
            left_b64=left_b64,
            right_b64=right_b64,
            siblings_b64=siblings_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)

        if not self.vendor_private_key_pem:
            raise ValueError("Vendor private key is not configured")
        vendor_private_key = load_private_key_from_pem(self.vendor_private_key_pem)
        vendor_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

        request_dto = PaytreeChildPairSettlementRequestDTO(
            vendor_public_key_der_b64=channel.vendor_public_key_der_b64,
            k=k,
            left_b64=left_b64,
            right_b64=right_b64,
            siblings_b64=siblings_b64,
            vendor_signature_b64=vendor_signature_b64,
        )

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_paytree_child_pair_payment_channel(
                channel_id, request_dto
            )

        await self.payment_repository.mark_closed(
            channel_id=channel_id,
            amount=channel.amount,
            balance=cumulative_owed,
        )
