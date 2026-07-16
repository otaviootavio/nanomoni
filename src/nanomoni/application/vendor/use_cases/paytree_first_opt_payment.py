"""Vendor use case: first-opt PayTree payments (pruned leaf→sub-root proof)."""

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
from ....crypto.merkle_index import compute_tree_depth, key_eytzinger
from ....crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    build_node_from_dependencies,
    get_proof_dependency_indexes,
)
from ....crypto.paytree import b64_to_bytes, bytes_to_b64
from ....crypto.paytree_scheme import PaytreeFirstOptCryptoScheme
from ....crypto.scheme import CryptoProof
from ....domain.shared import IssuerClientFactory
from ....domain.shared.proof_reference import PaymentScheme, ProofReference
from ....domain.vendor.entities import PaymentChannel, PaymentState
from ....domain.vendor.payment_repository import PaymentRepository
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ....protocol import infer_subroot_index_for_incoming_pruned_merkle_proof
from ..dtos import CloseChannelDTO
from ..paytree_dtos import PaytreePaymentResponseDTO, ReceivePaytreeFirstOptPaymentDTO
from .payment_validators import (
    check_proof_reference_duplicate,
    validate_proof_reference,
)


async def _fetch_and_validate_channel(
    channel_id: str,
    issuer_client_factory: IssuerClientFactory,
    vendor_public_key_der_b64: str,
) -> PaymentChannel:
    """Fetch and validate channel from the issuer (first-opt endpoint)."""
    try:
        async with issuer_client_factory() as issuer_client:
            dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
            issuer_channel = await issuer_client.get_paytree_first_opt_payment_channel(
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


class PaytreeFirstOptPaymentService:
    """Handles first-opt (pruned-proof) PayTree payments and settlement."""

    def __init__(
        self,
        payment_repository: PaymentRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        crypto_scheme: PaytreeFirstOptCryptoScheme,
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
        dto: ReceivePaytreeFirstOptPaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        node_repo = self.crypto_scheme._node_repo
        depth = compute_tree_depth(dto.paytree_max_i)
        root_key = key_eytzinger(depth, 0, depth)
        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            dto.i, len(dto.siblings_b64), depth
        )

        channel_json, nodes = await node_repo.get_channel_and_nodes(
            channel_id, [root_key, subroot_index]
        )

        if not channel_json:
            payment_channel = await _fetch_and_validate_channel(
                channel_id, self.issuer_client_factory, self.vendor_public_key_der_b64
            )
            if payment_channel.commitment:
                await node_repo.merge_nodes(
                    channel_id, {root_key: payment_channel.commitment}
                )
        else:
            payment_channel = PaymentChannel.model_validate_json(channel_json)
            root_b64 = nodes.get(root_key) or ""
            if not root_b64 and payment_channel.commitment:
                await node_repo.merge_nodes(
                    channel_id, {root_key: payment_channel.commitment}
                )

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")

        new_ref = ProofReference(value=dto.i)
        prev_ref = (
            ProofReference(value=payment_channel.last_proof_reference)
            if payment_channel.last_proof_reference is not None
            else None
        )
        cumulative_owed = new_ref.value * payment_channel.unit_value

        if prev_ref is not None and new_ref.value <= prev_ref.value:
            prev_state = await self.payment_repository.get_state(channel_id)
            prev_fingerprint = prev_state.proof_fingerprint if prev_state else None
            is_dup = check_proof_reference_duplicate(
                new_ref=new_ref,
                new_fingerprint=dto.leaf_b64,
                prev_ref=prev_ref,
                prev_fingerprint=prev_fingerprint,
            )
            if is_dup:
                verify_proof = CryptoProof(
                    scheme=PaymentScheme.PAYTREE,
                    data={
                        "leaf_b64": dto.leaf_b64,
                        "siblings_b64": dto.siblings_b64,
                        "max_steps": payment_channel.max_steps,
                        "channel_id": channel_id,
                    },
                )
                if not await self.crypto_scheme.verify(
                    payment_channel.commitment, new_ref, verify_proof
                ):
                    raise ValueError("Invalid PayTree first-opt proof")
                created_at = (
                    prev_state.created_at if prev_state else datetime.now(timezone.utc)
                )
                return PaytreePaymentResponseDTO(
                    channel_id=channel_id,
                    i=dto.i,
                    cumulative_owed_amount=cumulative_owed,
                    created_at=created_at,
                )
            raise ValueError(
                f"PayTree i must be increasing. Got {dto.i}, channel has {prev_ref.value}"
            )

        validate_proof_reference(
            new_ref=new_ref, prev_ref=prev_ref, max_steps=payment_channel.max_steps
        )
        if cumulative_owed > payment_channel.amount:
            raise ValueError(
                f"Cumulative owed {cumulative_owed} exceeds channel amount {payment_channel.amount}"
            )

        verify_proof = CryptoProof(
            scheme=PaymentScheme.PAYTREE,
            data={
                "leaf_b64": dto.leaf_b64,
                "siblings_b64": dto.siblings_b64,
                "max_steps": payment_channel.max_steps,
                "channel_id": channel_id,
            },
        )
        if not await self.crypto_scheme.verify(
            payment_channel.commitment, new_ref, verify_proof
        ):
            raise ValueError("Invalid PayTree first-opt proof (verification failed)")

        node_updates = self.crypto_scheme.build_node_updates(
            dto.i, dto.leaf_b64, dto.siblings_b64, depth
        )

        created_at = datetime.now(timezone.utc)
        new_state = PaymentState(
            channel_id=channel_id,
            proof_reference=dto.i,
            cumulative_owed=cumulative_owed,
            proof_fingerprint=dto.leaf_b64,
            created_at=created_at,
        )
        store_proof = CryptoProof(
            scheme=PaymentScheme.PAYTREE,
            data={"leaf_b64": dto.leaf_b64, "siblings_b64": dto.siblings_b64},
        )

        payment_channel.last_proof_reference = dto.i
        channel_json_updated = payment_channel.model_dump_json()
        state_json = new_state.model_dump_json()
        proof_json = json.dumps(
            {"scheme": store_proof.scheme.value, **store_proof.data}
        )

        await node_repo.save_nodes_and_payment(
            channel_id=channel_id,
            node_updates=node_updates,
            new_ref=dto.i,
            channel_json=channel_json_updated,
            state_json=state_json,
            proof_json=proof_json,
            is_closed=payment_channel.is_closed,
            created_at_ts=payment_channel.created_at.timestamp(),
        )

        return PaytreePaymentResponseDTO(
            channel_id=channel_id,
            i=dto.i,
            cumulative_owed_amount=cumulative_owed,
            created_at=created_at,
        )

    async def _rebuild_paytree_proof_for_settlement(
        self,
        channel_id: str,
        channel: PaymentChannel,
        last_i: int,
        last_leaf_b64: str,
    ) -> Optional[tuple[str, list[str]]]:
        node_repo = self.crypto_scheme._node_repo
        depth = compute_tree_depth(channel.max_steps)
        full_sibling_indexes = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
            0, last_i, depth, 0
        )
        dependency_indexes = get_proof_dependency_indexes(full_sibling_indexes, depth)
        node_keys = [key_eytzinger(lev, pos, depth) for lev, pos in dependency_indexes]
        nodes_b64 = await node_repo.get_nodes(channel_id, node_keys)

        node_hashes: dict[tuple[int, int], bytes] = {}
        for lev, pos in dependency_indexes:
            key = key_eytzinger(lev, pos, depth)
            if (lev, pos) == (0, last_i):
                node_hashes[(lev, pos)] = b64_to_bytes(last_leaf_b64)
            else:
                b64 = nodes_b64.get(key)
                if b64:
                    node_hashes[(lev, pos)] = b64_to_bytes(b64)
                elif lev == depth and pos == 0 and channel.commitment:
                    node_hashes[(lev, pos)] = b64_to_bytes(channel.commitment)

        try:
            full_siblings = [
                build_node_from_dependencies(lev, pos, node_hashes, depth)
                for lev, pos in full_sibling_indexes
            ]
        except KeyError:
            return None

        return last_leaf_b64, [bytes_to_b64(s) for s in full_siblings]

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
            result = await self._rebuild_paytree_proof_for_settlement(
                channel_id, channel, state.proof_reference, state.proof_fingerprint
            )
            if result:
                leaf_b64, siblings_b64 = result

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
            await issuer_client.settle_paytree_first_opt_payment_channel(
                channel_id, request_dto
            )

        await self.payment_repository.mark_closed(
            channel_id=channel_id,
            amount=channel.amount,
            balance=cumulative_owed,
        )
