"""Prover and verifier flows for Merkle tree with first-optimization sub-proofs.

Flow:
1. Prover generates Merkle tree.
2. Prover sends Merkle root to vendor (vendor stores it).
3. Prover sends leaf X (index, tree size) and its sub-proof using first optimization
   (no leaf sent yet => already_sent_indexes=None, full auth path).
4. Vendor looks up sub-root for that sub-proof in repo by keys; if not found raises
   error "no sub tree for that sub path"; if found, verifies proof; if valid, adds
   all proof nodes to the repo.

Prover and verifier use shared library from nanomoni.crypto. Vendor stores nodes
in an in-memory repo (see verifier_repo_paytree_first_opt).
"""

from __future__ import annotations

import pytest

from nanomoni.crypto.merkle_index import key
from nanomoni.crypto.merkle_tree import hash_bytes
from nanomoni.crypto.paytree_first_opt import (
    NoSubTreeForSubPathError,
    ProverPaytreeFirstOpt,
    ProverRepo,
    VerifierPaytreeFirstOpt,
    VerifierRepoBytes,
)

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
    """End-to-end: prover builds tree, sends root, sends leaf sub-proof; vendor verifies and stores in repo."""

    def test_flow_two_leaves_first_leaf(self) -> None:
        leaves = [HASH_A, HASH_B]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)
        assert verifier_repo[key(1, 0)] == HASH_AB

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=0, already_sent_indexes=None)
        )
        assert tree_size_out == 2
        assert len(siblings) == 1

        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 0)] == HASH_A
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(1, 0)] == HASH_AB

    def test_flow_two_leaves_second_leaf(self) -> None:
        leaves = [HASH_A, HASH_B]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=1, already_sent_indexes=None)
        )
        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(0, 0)] == HASH_A

    def test_flow_four_leaves_first_opt_no_leaf_sent_yet(self) -> None:
        leaves = [HASH_A, HASH_B, HASH_C, HASH_D]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)
        assert prover.depth == 2
        assert verifier_repo[key(2, 0)] == HASH_AB_CD

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=2, already_sent_indexes=None)
        )
        assert tree_size_out == 4
        assert len(siblings) == 2

        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 2)] == HASH_C
        # First opt: only received leaf + siblings (0:3, 1:0); root from step 2
        assert verifier_repo[key(0, 3)] == HASH_D
        assert verifier_repo[key(1, 0)] == HASH_AB
        assert verifier_repo[key(2, 0)] == HASH_AB_CD

    def test_verifier_raises_when_sub_root_missing(self) -> None:
        leaves = [HASH_A, HASH_B]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        # Do NOT call verifier.save_root – vendor has no root

        _, tree_size, leaf_hash, siblings = prover.get_leaf_subproof_firstopt(
            leaf_index=0, already_sent_indexes=None
        )
        with pytest.raises(
            NoSubTreeForSubPathError, match="no sub tree for that sub path"
        ):
            verifier.save_leaf_subproof(0, leaf_hash, siblings)

    def test_verifier_raises_when_proof_invalid(self) -> None:
        leaves = [HASH_A, HASH_B]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        _, _, leaf_hash, siblings = prover.get_leaf_subproof_firstopt(
            leaf_index=0, already_sent_indexes=None
        )
        bad_siblings = [hash_bytes(b"wrong")]  # arbitrary invalid hash
        with pytest.raises(ValueError, match="proof verification failed"):
            verifier.save_leaf_subproof(0, leaf_hash, bad_siblings)

    def test_flow_sequential_leaves_fill_repo(self) -> None:
        leaves = [HASH_E, HASH_F, HASH_G, HASH_H]
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(leaves)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        for idx in range(4):
            li, ts, lh, sib = prover.get_leaf_subproof_firstopt(
                leaf_index=idx, already_sent_indexes=None
            )
            verifier.save_leaf_subproof(li, lh, sib)

        assert verifier_repo[key(0, 0)] == HASH_E
        assert verifier_repo[key(0, 1)] == HASH_F
        assert verifier_repo[key(0, 2)] == HASH_G
        assert verifier_repo[key(0, 3)] == HASH_H
        assert verifier_repo[key(2, 0)] == HASH_EF_GH


class TestProverVerifierFlowEightLeaves:
    """End-to-end: 8-leaf Merkle tree [A..H]; root HASH_ABCDEFGH."""

    EIGHT_LEAVES = [HASH_A, HASH_B, HASH_C, HASH_D, HASH_E, HASH_F, HASH_G, HASH_H]

    def test_flow_eight_leaves_root_and_first_leaf(self) -> None:
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(self.EIGHT_LEAVES)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)
        assert prover.depth == 3
        assert tree_size == 8
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=0, already_sent_indexes=None)
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 0)] == HASH_A
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(1, 1)] == HASH_CD
        assert verifier_repo[key(2, 1)] == HASH_EF_GH
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_middle_leaf(self) -> None:
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(self.EIGHT_LEAVES)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=4, already_sent_indexes=None)
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 4)] == HASH_E
        assert verifier_repo[key(0, 5)] == HASH_F
        assert verifier_repo[key(1, 3)] == HASH_GH
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_last_leaf(self) -> None:
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(self.EIGHT_LEAVES)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        leaf_index, tree_size_out, leaf_hash, siblings = (
            prover.get_leaf_subproof_firstopt(leaf_index=7, already_sent_indexes=None)
        )
        assert tree_size_out == 8
        assert len(siblings) == 3
        verifier.save_leaf_subproof(leaf_index, leaf_hash, siblings)
        assert verifier_repo[key(0, 7)] == HASH_H
        assert verifier_repo[key(0, 6)] == HASH_G
        assert verifier_repo[key(1, 2)] == HASH_EF
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_sequential_all_fill_repo(self) -> None:
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(self.EIGHT_LEAVES)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)

        for idx in range(8):
            li, ts, lh, sib = prover.get_leaf_subproof_firstopt(
                leaf_index=idx, already_sent_indexes=None
            )
            verifier.save_leaf_subproof(li, lh, sib)

        assert verifier_repo[key(0, 0)] == HASH_A
        assert verifier_repo[key(0, 1)] == HASH_B
        assert verifier_repo[key(0, 2)] == HASH_C
        assert verifier_repo[key(0, 3)] == HASH_D
        assert verifier_repo[key(0, 4)] == HASH_E
        assert verifier_repo[key(0, 5)] == HASH_F
        assert verifier_repo[key(0, 6)] == HASH_G
        assert verifier_repo[key(0, 7)] == HASH_H
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

    def test_flow_eight_leaves_order_2_4_6_verify_middle_steps(self) -> None:
        """Send leaves 2, 4, 6 in order; verify repo after each step.

        After leaf 2: only nodes from that proof (C, D, HASH_AB, HASH_EF_GH);
        should NOT have A, B.
        After leaf 2 and 4: nodes from both proofs; should NOT have A, B, G, H.
        After leaf 2, 4, 6: nodes from all three proofs; should NOT have A, B.
        """
        prover_repo: ProverRepo = {}
        verifier_repo: VerifierRepoBytes = {}
        prover = ProverPaytreeFirstOpt(prover_repo)
        verifier = VerifierPaytreeFirstOpt(verifier_repo)

        prover.build_tree(self.EIGHT_LEAVES)
        root, tree_size = prover.get_root()
        verifier.save_root(root, tree_size)
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH

        # Send leaf 2 (C)
        li, ts, lh, sib = prover.get_leaf_subproof_firstopt(
            leaf_index=2, already_sent_indexes=None
        )
        verifier.save_leaf_subproof(li, lh, sib)
        assert verifier_repo[key(0, 2)] == HASH_C
        assert verifier_repo[key(0, 3)] == HASH_D
        assert verifier_repo[key(1, 0)] == HASH_AB
        assert verifier_repo[key(2, 1)] == HASH_EF_GH
        assert verifier_repo[key(3, 0)] == HASH_ABCDEFGH
        assert key(0, 0) not in verifier_repo  # should NOT have A
        assert key(0, 1) not in verifier_repo  # should NOT have B

        # Send leaf 4 (E)
        li, ts, lh, sib = prover.get_leaf_subproof_firstopt(
            leaf_index=4, already_sent_indexes=None
        )
        verifier.save_leaf_subproof(li, lh, sib)
        assert verifier_repo[key(0, 4)] == HASH_E
        assert verifier_repo[key(0, 5)] == HASH_F
        assert verifier_repo[key(1, 3)] == HASH_GH
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert key(0, 0) not in verifier_repo  # should NOT have A
        assert key(0, 1) not in verifier_repo  # should NOT have B
        assert key(0, 6) not in verifier_repo  # should NOT have G
        assert key(0, 7) not in verifier_repo  # should NOT have H

        # Send leaf 6 (G)
        li, ts, lh, sib = prover.get_leaf_subproof_firstopt(
            leaf_index=6, already_sent_indexes=None
        )
        verifier.save_leaf_subproof(li, lh, sib)
        assert verifier_repo[key(0, 6)] == HASH_G
        assert verifier_repo[key(0, 7)] == HASH_H
        assert verifier_repo[key(1, 2)] == HASH_EF
        assert verifier_repo[key(2, 0)] == HASH_AB_CD
        assert key(0, 0) not in verifier_repo  # should NOT have A
        assert key(0, 1) not in verifier_repo  # should NOT have B
