"""Prover and verifier flows for Merkle tree with first-optimization sub-proofs.

Flow:
1. Prover (stateless) generates Merkle tree; ProverRepo stores nodes.
2. VerifierRepo stores Merkle root.
3. Full proof: Verifier does index + crypto ops, VerifierRepo stores proof data only
   (leaf + siblings). receive_leaf_subproof when known sub-root exists (e.g. root).
4. Pruned proof (sequential): client sends pruned proof; vendor uses verify_pruned_paytree_proof
   to retrieve missing nodes from stored proofs, validate full proof, then store proof data.
"""

from __future__ import annotations

import base64
import pytest

from nanomoni.crypto.merkle_index import key
from nanomoni.crypto.merkle_tree import hash_bytes
from nanomoni.protocol.paytree_first_opt import (
    NoSubTreeForSubPathError,
    Prover,
    Verifier,
    VerifierRepoBytes,
    verify_pruned_paytree_proof,
)
from nanomoni.protocol.paytree_first_opt.verifier_store import store_root


def _all_merkle_keys_for_tree(tree_size: int) -> set[str]:
    """All (level, position) keys for a complete Merkle tree of tree_size leaves."""
    if tree_size <= 0:
        return set()
    depth = tree_size.bit_length() - 1
    return {
        key(level, pos)
        for level in range(depth + 1)
        for pos in range(tree_size >> level)
    }


def _keys_that_should_not_be_in_repo(
    tree_size: int, expected_present: set[str]
) -> set[str]:
    """Keys that must NOT be in verifier_repo (all tree keys minus expected present)."""
    return _all_merkle_keys_for_tree(tree_size) - expected_present


def receive_leaf_subproof(
    verifier_repo: VerifierRepoBytes,
    leaf_index: int,
    leaf_hash: bytes,
    siblings: list[bytes],
) -> None:
    """Composed flow: Verifier (index + crypto) + VerifierRepo (storage)."""
    sub_root_level = len(siblings)
    sub_root_pos = Verifier.get_sub_root_position(leaf_index, sub_root_level)
    known_node = verifier_repo.get_node(sub_root_level, sub_root_pos)
    if known_node is None:
        raise NoSubTreeForSubPathError("no sub tree for that sub path")
    if not Verifier.verify_leaf_subproof(
        leaf_index, leaf_hash, siblings, known_node, sub_root_level
    ):
        raise ValueError("proof verification failed")
    verifier_repo.store_proof(leaf_index, leaf_hash, siblings)


# Hardcoded SHA-256 digests for reproducible tests (echo -n "x" | sha256sum).
HASH_A = bytes.fromhex(
    "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
)
HASH_B = bytes.fromhex(
    "3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d"
)
HASH_C = bytes.fromhex(
    "2e7d2c03a9507ae265ecf5b5356885a53393a2029d241394997265a1a25aefc6"
)
HASH_D = bytes.fromhex(
    "18ac3e7343f016890c510e93f935261169d9e3f565436429830faf0934f4f8e4"
)
HASH_E = bytes.fromhex(
    "3f79bb7b435b05321651daefd374cdc681dc06faa65e374e38337b88ca046dea"
)
HASH_F = bytes.fromhex(
    "252f10c83610ebca1a059c0bae8255eba2f95be4d1d7bcfa89d7248a82d9f111"
)
HASH_G = bytes.fromhex(
    "cd0aa9856147b6c5b4ff2b7dfee5da20aa38253099ef1b4a64aced233c9afe29"
)
HASH_H = bytes.fromhex(
    "aaa9402664f1a41f40ebbc52c9993eb66aeb366602958fdfaa283b71e64db123"
)
# Parent hashes: H(left || right) per merkle_tree convention.
HASH_AB = bytes.fromhex(
    "e5a01fee14e0ed5c48714f22180f25ad8365b53f9779f79dc4a3d7e93963f94a"
)
HASH_BC = bytes.fromhex(
    "8e8a6cb359bb83f141498d96a80d7a9ce4c5558c115660820e0f2ac13555d934"
)
HASH_CD = bytes.fromhex(
    "bffe0b34dba16bc6fac17c08bac55d676cded5a4ade41fe2c9924a5dde8f3e5b"
)
HASH_EF = bytes.fromhex(
    "04fa33f8b4bd3db545fa04cdd51b462509f611797c7bfe5c944ee2bb3b2ed908"
)
HASH_FG = bytes.fromhex(
    "272056471b0ef007bbfbb36aaaf6297655d311de30ca8c3749debfe5cb1e152a"
)
HASH_GH = bytes.fromhex(
    "140257c1540113794d2ae3394879e586ca5caebca19663ff87417892cf36fd23"
)
# Roots for 4-leaf trees.
HASH_AB_CD = bytes.fromhex(
    "14ede5e8e97ad9372327728f5099b95604a39593cac3bd38a343ad76205213e7"
)
HASH_EF_GH = bytes.fromhex(
    "8e2c530a100033894555cde1c7d4e36f7c6e553ee3914022ec7a13e1196baed2"
)
# Root for 8-leaf tree [A..H].
HASH_ABCDEFGH = bytes.fromhex(
    "bd7c8a900be9b67ba7df5c78a652a8474aedd78adb5083e80e49d9479138a23f"
)


# ---------------------------------------------------------------------------
# Flow tests (prover and verifier imported from nanomoni.crypto)
# ---------------------------------------------------------------------------


class TestProverVerifierFlow:
    """End-to-end: Prover (stateless) + Verifier (stateless) + VerifierRepo (dummy)."""

    def test_flow_two_leaves_first_leaf(self) -> None:
        leaves = [HASH_A, HASH_B]
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        verifier_repo.store_root(root, tree_size)
        assert verifier_repo[key(1, 0)] == HASH_AB

        leaf_index, tree_size_out, leaf_hash, siblings = (
            Prover.get_leaf_subproof_firstopt(
                tree_levels, leaf_index=0, already_sent_indexes=None
            )
        )
        assert tree_size_out == 2
        assert len(siblings) == 1

        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 0)] == HASH_A
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(1, 0)] == HASH_AB

    def test_flow_two_leaves_second_leaf(self) -> None:
        leaves = [HASH_A, HASH_B]
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        verifier_repo.store_root(root, tree_size)

        leaf_index, _, leaf_hash, siblings = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=1, already_sent_indexes=None
        )
        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(0, 0)] == HASH_A

    def test_flow_four_leaves_first_opt_no_leaf_sent_yet(self) -> None:
        leaves = [HASH_A, HASH_B, HASH_C, HASH_D]
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        verifier_repo.store_root(root, tree_size)
        assert len(tree_levels) - 1 == 2
        assert verifier_repo[key(2, 0)] == HASH_AB_CD

        leaf_index, tree_size_out, leaf_hash, siblings = (
            Prover.get_leaf_subproof_firstopt(
                tree_levels, leaf_index=2, already_sent_indexes=None
            )
        )
        assert tree_size_out == 4
        assert len(siblings) == 2

        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 2)] == HASH_C
        assert verifier_repo[key(0, 3)] == HASH_D
        assert verifier_repo[key(1, 0)] == HASH_AB
        assert verifier_repo[key(2, 0)] == HASH_AB_CD

    def test_verifier_raises_when_sub_root_missing(self) -> None:
        leaves = [HASH_A, HASH_B]
        verifier_repo = VerifierRepoBytes()
        _, _, tree_levels = Prover.build_tree(leaves)
        # Do NOT call verifier_repo.store_root – vendor has no root

        _, _, leaf_hash, siblings = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=0, already_sent_indexes=None
        )
        with pytest.raises(
            NoSubTreeForSubPathError, match="no sub tree for that sub path"
        ):
            receive_leaf_subproof(verifier_repo, 0, leaf_hash, siblings)

    def test_verifier_raises_when_proof_invalid(self) -> None:
        leaves = [HASH_A, HASH_B]
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        verifier_repo.store_root(root, tree_size)

        _, _, leaf_hash, _ = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=0, already_sent_indexes=None
        )
        bad_siblings = [hash_bytes(b"wrong")]
        with pytest.raises(ValueError, match="proof verification failed"):
            receive_leaf_subproof(verifier_repo, 0, leaf_hash, bad_siblings)

    def test_flow_sequential_leaves_fill_repo(self) -> None:
        """First-opt: pruned proofs; vendor retrieves missing nodes from stored proofs, validates full proof."""
        leaves = [HASH_E, HASH_F, HASH_G, HASH_H]
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        max_i = tree_size - 1
        repo: dict[str, str] = {}
        store_root(repo, base64.b64encode(root).decode(), tree_size)

        for idx in range(4):
            li, _, lh, sib = Prover.get_leaf_subproof_firstopt(
                tree_levels,
                leaf_index=idx,
                already_sent_indexes=range(idx) if idx > 0 else None,
            )
            leaf_b64 = base64.b64encode(lh).decode()
            pruned_b64 = [base64.b64encode(s).decode() for s in sib]
            ok, _, repo = verify_pruned_paytree_proof(
                i=li,
                root_b64=base64.b64encode(root).decode(),
                leaf_b64=leaf_b64,
                pruned_siblings_b64=pruned_b64,
                max_i=max_i,
                last_verified_index=idx - 1 if idx else None,
                repo=repo,
            )
            assert ok

        assert base64.b64decode(repo[key(0, 0)]) == HASH_E
        assert base64.b64decode(repo[key(0, 1)]) == HASH_F
        assert base64.b64decode(repo[key(0, 2)]) == HASH_G
        assert base64.b64decode(repo[key(0, 3)]) == HASH_H
        assert base64.b64decode(repo[key(2, 0)]) == HASH_EF_GH


class TestProverVerifierFlowEightLeaves:
    """End-to-end: 8-leaf Merkle tree [A..H]; root HASH_ABCDEFGH."""

    EIGHT_LEAVES = [HASH_A, HASH_B, HASH_C, HASH_D, HASH_E, HASH_F, HASH_G, HASH_H]

    def test_flow_eight_leaves_root_and_first_leaf(self) -> None:
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(self.EIGHT_LEAVES)
        verifier_repo.store_root(root, tree_size)
        assert len(tree_levels) - 1 == 3
        assert tree_size == 8
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

        leaf_index, tree_size_out, leaf_hash, siblings = (
            Prover.get_leaf_subproof_firstopt(
                tree_levels, leaf_index=0, already_sent_indexes=None
            )
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 0)] == HASH_A
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(1, 1)] == HASH_CD
        assert verifier_repo[key(2, 1)] == HASH_EF_GH
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_middle_leaf(self) -> None:
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(self.EIGHT_LEAVES)
        verifier_repo.store_root(root, tree_size)

        leaf_index, tree_size_out, leaf_hash, siblings = (
            Prover.get_leaf_subproof_firstopt(
                tree_levels, leaf_index=4, already_sent_indexes=None
            )
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 4)] == HASH_E
        assert verifier_repo[key(0, 5)] == HASH_F
        assert verifier_repo[key(1, 3)] == HASH_GH
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_last_leaf(self) -> None:
        verifier_repo = VerifierRepoBytes()
        root, tree_size, tree_levels = Prover.build_tree(self.EIGHT_LEAVES)
        verifier_repo.store_root(root, tree_size)

        leaf_index, tree_size_out, leaf_hash, siblings = (
            Prover.get_leaf_subproof_firstopt(
                tree_levels, leaf_index=7, already_sent_indexes=None
            )
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        receive_leaf_subproof(verifier_repo, leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 7)] == HASH_H
        assert verifier_repo[key(0, 6)] == HASH_G
        assert verifier_repo[key(1, 2)] == HASH_EF
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_sequential_all_fill_repo(self) -> None:
        """First-opt: pruned proofs; vendor retrieves missing nodes from stored proofs."""
        root, tree_size, tree_levels = Prover.build_tree(self.EIGHT_LEAVES)
        max_i = tree_size - 1
        repo: dict[str, str] = {}
        store_root(repo, base64.b64encode(root).decode(), tree_size)

        for idx in range(8):
            li, _, lh, sib = Prover.get_leaf_subproof_firstopt(
                tree_levels,
                leaf_index=idx,
                already_sent_indexes=range(idx) if idx > 0 else None,
            )
            leaf_b64 = base64.b64encode(lh).decode()
            pruned_b64 = [base64.b64encode(s).decode() for s in sib]
            ok, _, repo = verify_pruned_paytree_proof(
                i=li,
                root_b64=base64.b64encode(root).decode(),
                leaf_b64=leaf_b64,
                pruned_siblings_b64=pruned_b64,
                max_i=max_i,
                last_verified_index=idx - 1 if idx else None,
                repo=repo,
            )
            assert ok

        assert base64.b64decode(repo[key(0, 0)]) == HASH_A
        assert base64.b64decode(repo[key(0, 1)]) == HASH_B
        assert base64.b64decode(repo[key(0, 2)]) == HASH_C
        assert base64.b64decode(repo[key(0, 3)]) == HASH_D
        assert base64.b64decode(repo[key(0, 4)]) == HASH_E
        assert base64.b64decode(repo[key(0, 5)]) == HASH_F
        assert base64.b64decode(repo[key(0, 6)]) == HASH_G
        assert base64.b64decode(repo[key(0, 7)]) == HASH_H
        assert base64.b64decode(repo[key(3, 0)]) == HASH_ABCDEFGH

    def test_flow_eight_leaves_order_2_4_6_verify_middle_steps(self) -> None:
        """Send leaves 2, 4, 6 in order; verify repo after each step (first-opt: proof data only)."""
        root, tree_size, tree_levels = Prover.build_tree(self.EIGHT_LEAVES)
        repo: dict[str, str] = {}
        store_root(repo, base64.b64encode(root).decode(), tree_size)
        assert base64.b64decode(repo[key(3, 0)]) == HASH_ABCDEFGH

        # Send leaf 2 (C)
        li, _, lh, sib = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=2, already_sent_indexes=None
        )
        ok, _, repo = verify_pruned_paytree_proof(
            i=li,
            root_b64=base64.b64encode(root).decode(),
            leaf_b64=base64.b64encode(lh).decode(),
            pruned_siblings_b64=[base64.b64encode(s).decode() for s in sib],
            max_i=7,
            last_verified_index=None,
            repo=repo,
        )
        assert ok
        sent_indexes: list[int] = [2]
        assert base64.b64decode(repo[key(0, 2)]) == HASH_C
        assert base64.b64decode(repo[key(0, 3)]) == HASH_D
        assert base64.b64decode(repo[key(1, 0)]) == HASH_AB
        assert base64.b64decode(repo[key(2, 1)]) == HASH_EF_GH
        assert base64.b64decode(repo[key(3, 0)]) == HASH_ABCDEFGH
        # First-opt: only proof data (leaf + siblings), no computed path nodes
        expected_after_2 = {key(0, 2), key(0, 3), key(1, 0), key(2, 1), key(3, 0)}
        assert len(repo) == len(expected_after_2)
        for k in _keys_that_should_not_be_in_repo(8, expected_after_2):
            assert k not in repo

        # Send leaf 4 (E)
        li, _, lh, sib = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=4, already_sent_indexes=sent_indexes
        )
        ok, _, repo = verify_pruned_paytree_proof(
            i=li,
            root_b64=base64.b64encode(root).decode(),
            leaf_b64=base64.b64encode(lh).decode(),
            pruned_siblings_b64=[base64.b64encode(s).decode() for s in sib],
            max_i=7,
            last_verified_index=2,
            repo=repo,
        )
        assert ok
        sent_indexes.append(4)
        assert base64.b64decode(repo[key(0, 4)]) == HASH_E
        assert base64.b64decode(repo[key(0, 5)]) == HASH_F
        assert base64.b64decode(repo[key(1, 3)]) == HASH_GH
        assert base64.b64decode(repo[key(2, 0)]) == HASH_AB_CD
        expected_after_4 = {
            key(0, 2),
            key(0, 3),
            key(0, 4),
            key(0, 5),
            key(1, 0),
            key(1, 3),
            key(2, 0),
            key(2, 1),
            key(3, 0),
        }
        assert len(repo) == len(expected_after_4)
        for k in _keys_that_should_not_be_in_repo(8, expected_after_4):
            assert k not in repo

        # Send leaf 6 (G)
        li, _, lh, sib = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=6, already_sent_indexes=sent_indexes
        )
        ok, _, repo = verify_pruned_paytree_proof(
            i=li,
            root_b64=base64.b64encode(root).decode(),
            leaf_b64=base64.b64encode(lh).decode(),
            pruned_siblings_b64=[base64.b64encode(s).decode() for s in sib],
            max_i=7,
            last_verified_index=4,
            repo=repo,
        )
        assert ok
        assert base64.b64decode(repo[key(0, 6)]) == HASH_G
        assert base64.b64decode(repo[key(0, 7)]) == HASH_H
        assert base64.b64decode(repo[key(1, 2)]) == HASH_EF
        assert base64.b64decode(repo[key(2, 0)]) == HASH_AB_CD
        expected_after_6 = {
            key(0, 2),
            key(0, 3),
            key(0, 4),
            key(0, 5),
            key(0, 6),
            key(0, 7),
            key(1, 0),
            key(1, 2),
            key(1, 3),
            key(2, 0),
            key(2, 1),
            key(3, 0),
        }
        assert len(repo) == len(expected_after_6)
        for k in _keys_that_should_not_be_in_repo(8, expected_after_6):
            assert k not in repo
