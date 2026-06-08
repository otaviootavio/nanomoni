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
from ...shared.paytree_proof import (
    verify_paytree_proof_first_opt,
    verify_paytree_proof_standard,
)
from ....crypto.merkle_index import (
    compute_tree_depth,
    get_sibling_position_at_level,
    key_eytzinger,
)
from ....crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    build_node_from_dependencies,
    get_proof_dependency_indexes,
)
from ....crypto.paytree import (
    b64_to_bytes,
    bytes_to_b64,
    compute_cumulative_owed_amount,
)
from ....domain.shared import IssuerClientFactory
from ....domain.vendor.entities import PaytreePaymentChannel, PaytreeState
from ....domain.vendor.paytree_first_opt_repository import PaytreeFirstOptNodeRepository
from ....domain.vendor.paytree_repository import PaytreeRepository
from ....protocol import infer_subroot_index_for_incoming_pruned_merkle_proof
from ....infrastructure.http.http_client import HttpRequestError, HttpResponseError
from ..dtos import CloseChannelDTO
from ..paytree_dtos import PaytreePaymentResponseDTO, ReceivePaytreePaymentDTO
from .paytree_validators import (
    check_duplicate_paytree_payment_by_leaf,
    validate_paytree_amount,
    validate_paytree_i,
)


class PaytreePaymentService:
    """Service for handling PayTree payments and PayTree settlement."""

    def __init__(
        self,
        payment_channel_repository: PaytreeRepository,
        issuer_client_factory: IssuerClientFactory,
        vendor_public_key_der_b64: str,
        *,
        paytree_first_opt_node_repository: Optional[
            PaytreeFirstOptNodeRepository
        ] = None,
        vendor_private_key_pem: Optional[str] = None,
    ):
        self.payment_channel_repository = payment_channel_repository
        self.issuer_client_factory = issuer_client_factory
        self.vendor_public_key_der_b64 = vendor_public_key_der_b64
        self.paytree_first_opt_node_repository = paytree_first_opt_node_repository
        self.vendor_private_key_pem = vendor_private_key_pem

    async def _verify_paytree_channel(self, channel_id: str) -> PaytreePaymentChannel:
        """
        Verify that the PayTree channel exists on the issuer side and return it.

        This uses the issuer PayTree channel endpoint so PayTree commitment
        fields are present and validated.
        """
        try:
            async with self.issuer_client_factory() as issuer_client:
                dto = GetPaymentChannelRequestDTO(channel_id=channel_id)
                issuer_channel = await issuer_client.get_paytree_payment_channel(dto)
                channel_data = issuer_channel.model_dump()

                payment_channel = PaytreePaymentChannel.model_validate(channel_data)

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
        payment_channel: PaytreePaymentChannel,
        new_state: PaytreeState,
        is_first_payment: bool,
    ) -> tuple[int, Optional[PaytreeState], PaytreePaymentChannel]:
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
                if not isinstance(cached, PaytreePaymentChannel):
                    raise TypeError("Cached channel is not PayTree-enabled")
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

    def _build_first_opt_node_updates(
        self,
        leaf_index: int,
        leaf_b64: str,
        siblings_b64: list[str],
        depth: int,
    ) -> dict[str, str]:
        """Build node_key -> hash_b64 updates from verified proof: leaf + siblings.

        Like test_paytree_first_opt_walkthrough: verifier stores proof siblings in
        the node store and leaf hashes (test uses secret store then hash_bytes(secret)).
        Storing the leaf (0, leaf_index) allows rebuild to satisfy dependency_indexes
        for level 0; together with stored siblings we can build internal nodes via
        build_node_from_dependencies.
        """
        updates: dict[str, str] = {}
        updates[key_eytzinger(0, leaf_index, depth)] = leaf_b64
        siblings = [b64_to_bytes(s) for s in siblings_b64]
        for level, sib in enumerate(siblings):
            pos = get_sibling_position_at_level(leaf_index, level)
            updates[key_eytzinger(level, pos, depth)] = bytes_to_b64(sib)
        return updates

    async def _receive_paytree_payment_first_opt(
        self,
        *,
        channel_id: str,
        dto: ReceivePaytreePaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        """First-opt flow: verify pruned proof, store nodes, update channel metadata."""
        if not self.paytree_first_opt_node_repository:
            raise ValueError(
                "PayTree first-opt repository is not configured (optimization_type=1)"
            )
        if dto.paytree_max_i <= 0:
            raise ValueError(
                "paytree_max_i required for first-opt (client must send it)"
            )

        depth = compute_tree_depth(dto.paytree_max_i)
        root_key = key_eytzinger(depth, 0, depth)
        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            dto.i, len(dto.siblings_b64), depth
        )

        # One DB shot: GET channel + MGET nodes
        (
            channel_json,
            nodes,
        ) = await self.paytree_first_opt_node_repository.get_channel_and_nodes(
            channel_id, [root_key, subroot_index]
        )

        is_first_payment = False
        if not channel_json:
            payment_channel = await self._verify_paytree_channel(channel_id)
            is_first_payment = True
            # Root backfill for first payment (channel not in vendor cache)
            if payment_channel.paytree_root_b64:
                await self.paytree_first_opt_node_repository.merge_nodes(
                    channel_id, {root_key: payment_channel.paytree_root_b64}
                )
            root_b64 = payment_channel.paytree_root_b64 or ""
            subroot_b64 = nodes.get(subroot_index) or ""
        else:
            payment_channel = PaytreePaymentChannel.model_validate_json(channel_json)
            root_b64 = nodes.get(root_key) or ""
            subroot_b64 = nodes.get(subroot_index) or ""
            if not root_b64 and payment_channel.paytree_root_b64:
                root_b64 = payment_channel.paytree_root_b64 or ""

        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")
        prev_i = payment_channel.last_leaf_index
        prev_leaf = payment_channel.last_leaf_b64
        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=payment_channel.paytree_unit_value
        )

        # Walkthrough: when subroot is the root we may have just merged it; when subroot is the leaf (0 siblings) we use leaf from proof
        if not subroot_b64 and subroot_index == root_key:
            subroot_b64 = root_b64
        if not subroot_b64 and subroot_index == key_eytzinger(0, dto.i, depth):
            subroot_b64 = dto.leaf_b64

        # Duplicate check
        if dto.i <= prev_i:
            if prev_i >= 0 and prev_leaf is None:
                raise RuntimeError(
                    "Channel has last_leaf_index but no last_leaf_b64 (data inconsistency)"
                )
            is_duplicate = check_duplicate_paytree_payment_by_leaf(
                i=dto.i,
                leaf=dto.leaf_b64,
                prev_i=prev_i,
                prev_leaf=prev_leaf,
            )
            if is_duplicate:
                if not subroot_b64:
                    raise ValueError(
                        "Invalid first-opt proof (subroot missing in store)"
                    )
                if not verify_paytree_proof_first_opt(
                    i=dto.i,
                    leaf_b64=dto.leaf_b64,
                    siblings_b64=dto.siblings_b64,
                    subroot_b64=subroot_b64,
                    subroot_index=subroot_index,
                    depth=depth,
                ):
                    raise ValueError("Invalid PayTree first-opt proof")
                created_at = payment_channel.last_paytree_created_at or datetime.now(
                    timezone.utc
                )
                return PaytreePaymentResponseDTO(
                    channel_id=channel_id,
                    i=dto.i,
                    cumulative_owed_amount=cumulative_owed_amount,
                    created_at=created_at,
                )

        validate_paytree_i(
            i=dto.i,
            prev_i=prev_i,
            max_i=payment_channel.paytree_max_i,
        )
        validate_paytree_amount(
            cumulative_owed=cumulative_owed_amount,
            channel_amount=payment_channel.amount,
        )

        # subroot_b64 already from single get_nodes above
        if not subroot_b64:
            raise ValueError(
                "Invalid first-opt proof (subroot missing in store; "
                "client may have sent pruned proof for unknown prior)"
            )
        if not verify_paytree_proof_first_opt(
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            subroot_b64=subroot_b64,
            subroot_index=subroot_index,
            depth=depth,
        ):
            raise ValueError("Invalid PayTree first-opt proof (verification failed)")

        updates = self._build_first_opt_node_updates(
            dto.i, dto.leaf_b64, dto.siblings_b64, depth
        )

        if is_first_payment:
            await self.payment_channel_repository.save_channel(payment_channel)

        payment_channel.last_leaf_index = dto.i
        payment_channel.last_leaf_b64 = dto.leaf_b64
        payment_channel.last_paytree_created_at = datetime.now(timezone.utc)
        await (
            self.paytree_first_opt_node_repository.save_nodes_and_save_payment_channel(
                channel_id,
                updates,
                payment_channel.model_dump_json(),
                payment_channel.is_closed,
                payment_channel.created_at.timestamp(),
            )
        )

        return PaytreePaymentResponseDTO(
            channel_id=channel_id,
            i=dto.i,
            cumulative_owed_amount=cumulative_owed_amount,
            created_at=payment_channel.last_paytree_created_at,
        )

    async def _receive_paytree_payment_std(
        self,
        *,
        channel_id: str,
        dto: ReceivePaytreePaymentDTO,
    ) -> PaytreePaymentResponseDTO:
        """Standard flow: full proof, PaytreeState, Lua-script atomic save."""
        payment_channel = (
            await self.payment_channel_repository.get_paytree_pruned_channel_state(
                channel_id
            )
        )
        is_first_payment = False
        if not payment_channel:
            payment_channel = await self._verify_paytree_channel(channel_id)
            is_first_payment = True
        elif not isinstance(payment_channel, PaytreePaymentChannel):
            raise TypeError("Payment channel is not PayTree-enabled")
        if payment_channel.is_closed:
            raise ValueError("Payment channel is closed")
        prev_i = payment_channel.last_leaf_index
        prev_leaf = payment_channel.last_leaf_b64
        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=payment_channel.paytree_unit_value
        )

        if dto.i <= prev_i:
            if prev_i >= 0 and prev_leaf is None:
                raise RuntimeError(
                    "Channel has last_leaf_index but no last_leaf_b64 (data inconsistency)"
                )
            is_duplicate = check_duplicate_paytree_payment_by_leaf(
                i=dto.i,
                leaf=dto.leaf_b64,
                prev_i=prev_i,
                prev_leaf=prev_leaf,
            )
            if is_duplicate:
                if not verify_paytree_proof_standard(
                    i=dto.i,
                    leaf_b64=dto.leaf_b64,
                    siblings_b64=dto.siblings_b64,
                    root_b64=payment_channel.paytree_root_b64,
                    max_i=payment_channel.paytree_max_i,
                ):
                    raise ValueError("Invalid PayTree proof (root mismatch)")
                created_at = payment_channel.last_paytree_created_at or datetime.now(
                    timezone.utc
                )
                return PaytreePaymentResponseDTO(
                    channel_id=channel_id,
                    i=dto.i,
                    cumulative_owed_amount=cumulative_owed_amount,
                    created_at=created_at,
                )

        validate_paytree_i(
            i=dto.i,
            prev_i=prev_i,
            max_i=payment_channel.paytree_max_i,
        )
        validate_paytree_amount(
            cumulative_owed=cumulative_owed_amount,
            channel_amount=payment_channel.amount,
        )

        if not verify_paytree_proof_standard(
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            root_b64=payment_channel.paytree_root_b64,
            max_i=payment_channel.paytree_max_i,
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
            _,
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

    async def _rebuild_full_paytree_state_from_first_opt(
        self,
        channel_id: str,
        channel: PaytreePaymentChannel,
    ) -> Optional[PaytreeState]:
        """Rebuild full PayTree proof (leaf -> root) from first-opt node store for settlement.

        Same strategy as test_paytree_first_opt_walkthrough (batch_get_node_hashes_or_secrets
        + build_node_from_dependencies): we have proof siblings in the node store and leaf
        hashes (test has secrets then hash_bytes(secret); we store leaf_b64 per payment).
        Even when a dependency node is missing from the stored proof, we can build internal
        nodes from children, so the full proof can be reconstructed.
        """
        if not self.paytree_first_opt_node_repository:
            return None
        if channel.last_leaf_index is None or channel.last_leaf_b64 is None:
            return None
        depth = compute_tree_depth(channel.paytree_max_i)
        last_i = channel.last_leaf_index
        # Full proof (leaf -> root): same as test's build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(0, last_leaf_index, depth, 0)
        full_sibling_indexes = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
            0, last_i, depth, 0
        )
        dependency_indexes = get_proof_dependency_indexes(full_sibling_indexes, depth)
        node_keys = [key_eytzinger(lev, pos, depth) for lev, pos in dependency_indexes]
        nodes_b64 = await self.paytree_first_opt_node_repository.get_nodes(
            channel_id, node_keys
        )
        node_hashes: dict[tuple[int, int], bytes] = {}
        for lev, pos in dependency_indexes:
            key = key_eytzinger(lev, pos, depth)
            if (lev, pos) == (0, last_i):
                node_hashes[(lev, pos)] = b64_to_bytes(channel.last_leaf_b64)
            else:
                b64 = nodes_b64.get(key)
                if b64:
                    node_hashes[(lev, pos)] = b64_to_bytes(b64)
                elif lev == depth and pos == 0 and channel.paytree_root_b64:
                    node_hashes[(lev, pos)] = b64_to_bytes(channel.paytree_root_b64)
        try:
            full_siblings = [
                build_node_from_dependencies(lev, pos, node_hashes, depth)
                for lev, pos in full_sibling_indexes
            ]
        except KeyError:
            return None
        siblings_b64 = [bytes_to_b64(s) for s in full_siblings]
        return PaytreeState(
            channel_id=channel_id,
            i=last_i,
            leaf_b64=channel.last_leaf_b64,
            siblings_b64=siblings_b64,
            created_at=channel.last_paytree_created_at or datetime.now(timezone.utc),
        )

    async def receive_paytree_payment(
        self, channel_id: str, dto: ReceivePaytreePaymentDTO
    ) -> PaytreePaymentResponseDTO:
        """Receive and validate a PayTree (Merkle proof) payment from a client."""
        # Branch first on optimization mode (from DTO); each flow does its own
        # channel fetch and checks (node replication across flows is acceptable)
        if dto.optimization_type == 1:
            return await self._receive_paytree_payment_first_opt(
                channel_id=channel_id,
                dto=dto,
            )
        return await self._receive_paytree_payment_std(
            channel_id=channel_id,
            dto=dto,
        )

    async def settle_channel(self, dto: CloseChannelDTO) -> None:
        """Settle a PayTree channel by settling the latest PayTree state on the issuer."""
        channel = await self.payment_channel_repository.get_by_channel_id(
            dto.channel_id
        )
        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, PaytreePaymentChannel):
            raise TypeError("Payment channel is not PayTree-enabled")
        if channel.is_closed:
            return None

        latest_state = await self.payment_channel_repository.get_paytree_state(
            dto.channel_id
        )
        if not latest_state and self.paytree_first_opt_node_repository:
            # First-opt flow: channel with last_leaf_index/last_leaf_b64 is stored in
            # the first-opt repo only; main payment_channel_repository has the channel
            # from open/first save without those fields. Load from first-opt for rebuild.
            depth = compute_tree_depth(channel.paytree_max_i)
            root_key = key_eytzinger(depth, 0, depth)
            (
                channel_json,
                _,
            ) = await self.paytree_first_opt_node_repository.get_channel_and_nodes(
                dto.channel_id, [root_key, root_key]
            )
            if channel_json:
                channel = PaytreePaymentChannel.model_validate_json(channel_json)
            latest_state = await self._rebuild_full_paytree_state_from_first_opt(
                dto.channel_id, channel
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

        async with self.issuer_client_factory() as issuer_client:
            await issuer_client.settle_paytree_payment_channel(
                dto.channel_id, request_dto
            )

        await self.payment_channel_repository.mark_closed(
            channel_id=dto.channel_id,
            amount=channel.amount,
            balance=cumulative_owed_amount,
        )

        return None
