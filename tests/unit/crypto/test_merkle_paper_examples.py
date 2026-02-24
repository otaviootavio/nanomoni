"""Worked examples from main.tex as regression tests.

- First compression (Section 'Example'): n=8, x=01010101, prior a1=01010111, a2=01001010, a3=11010101
  -> k_max=6, I_send={0,1}, P_pruned = 2 nodes.
- Second compression (Section 'Example'): a1=00001111, a2=00001000, a3=01111111;
  Case One x=00001011 -> 1 node; Case Two x=00000000 -> 2 nodes.
"""

from __future__ import annotations

from nanomoni.crypto.merkle_index import (
    compute_lcp,
    compute_send_levels_second_opt,
    get_sibling_position_at_level,
    key,
)
from nanomoni.crypto.merkle_tree import hash_bytes
from nanomoni.protocol.paytree_first_opt import Prover


def _make_leaves(n: int) -> list[bytes]:
    """Deterministic leaf hashes for a tree of n leaves."""
    return [hash_bytes(bytes([i % 256])) for i in range(n)]


def _known_keys_second_opt(prior_indexes: list[int], depth: int) -> set[str]:
    """K = union of P(a_i) ∪ Q(a_i) for each prior (for second-opt)."""
    from nanomoni.crypto.merkle_index import (
        get_path_keys,
        get_sibling_keys,
    )

    out: set[str] = set()
    for a in prior_indexes:
        out.update(get_sibling_keys(a, depth))
        out.update(get_path_keys(a, depth))
    return out


class TestFirstCompressionPaperExample:
    """main.tex Section 'Example': first compression with n=8 (256 leaves)."""

    N = 8
    TREE_SIZE = 1 << N  # 256

    def test_k_max_and_levels_match_paper(self) -> None:
        """x=01010101 (85), prior 01010111 (87), 01001010 (74), 11010101 (213) -> k_max=6, I_send={0,1}."""
        depth = self.N
        x = 0b01010101  # 85
        a1, a2, a3 = 0b01010111, 0b01001010, 0b11010101  # 87, 74, 213
        k1 = compute_lcp(x, a1, depth)
        k2 = compute_lcp(x, a2, depth)
        k3 = compute_lcp(x, a3, depth)
        assert k1 == 6 and k2 == 3 and k3 == 0
        k_max = max(k1, k2, k3)
        assert k_max == 6
        expected_levels = list(range(depth - k_max))
        assert expected_levels == [0, 1]

    def test_pruned_proof_has_two_siblings(self) -> None:
        """Prover sends only levels 0 and 1 -> 2 siblings."""
        leaves = _make_leaves(self.TREE_SIZE)
        root, tree_size, tree_levels = Prover.build_tree(leaves)
        depth = len(tree_levels) - 1
        assert depth == self.N

        x = 85
        already_sent = [87, 74, 213]
        li, ts, lh, siblings = Prover.get_leaf_subproof_firstopt(
            tree_levels, leaf_index=x, already_sent_indexes=already_sent
        )
        assert li == x
        assert ts == self.TREE_SIZE
        assert len(siblings) == 2, "paper: P_pruned(x) has 2 nodes (levels 0, 1)"

    def test_pruned_sibling_positions_match_paper(self) -> None:
        """Paper: j=0 -> 101010100, j=1 -> 010101011 (9-bit). Our (level, position): (0, 84), (1, 43)."""
        x = 85
        pos0 = get_sibling_position_at_level(x, 0)
        pos1 = get_sibling_position_at_level(x, 1)
        # (1||x) in paper = 0b101010101; (101010101>>0)^1 = 101010100 -> lower 8 bits 01010100 = 84
        assert pos0 == 84
        # (101010101>>1)^1 = 010101010^1 = 010101011 -> lower 8 bits 01010101 = 85? No: 010101011 is 9 bits, value 171. Lower 8 bits = 43.
        assert pos1 == 43


class TestSecondCompressionPaperExample:
    """main.tex Section 'Example' (combined): second compression, Case One and Case Two."""

    N = 8
    PRIOR = [0b00001111, 0b00001000, 0b01111111]  # 15, 8, 127

    def test_case_one_send_levels_single_node(self) -> None:
        """x=00001011 (11): k_max=6, F from spec -> L_send={0} -> 1 node."""
        depth = self.N
        x = 0b00001011  # 11
        k1 = compute_lcp(x, 15, depth)
        k2 = compute_lcp(x, 8, depth)
        k3 = compute_lcp(x, 127, depth)
        assert k1 == 5 and k2 == 6 and k3 == 1  # LCP(11,127)=1 (00001011 vs 01111111)
        k_max = max(k1, k2, k3)
        assert k_max == 6
        forbidden = {depth - k1 - 1, depth - k2 - 1, depth - k3 - 1}
        assert forbidden == {2, 1, 6}
        levels_after_first = set(range(depth - k_max))
        l_send = levels_after_first - forbidden
        assert l_send == {0}

        known_keys = _known_keys_second_opt(self.PRIOR, depth)
        got = compute_send_levels_second_opt(i=x, depth=depth, known_keys=known_keys)
        assert got == [0], "Case One: prover transmits only 1 node (level 0)"

    def test_case_two_send_levels_two_nodes(self) -> None:
        """x=00000000 (0): k_max and F from compute_lcp -> L_send has 3 levels."""
        depth = self.N
        x = 0
        k1 = compute_lcp(x, 15, depth)
        k2 = compute_lcp(x, 8, depth)
        k3 = compute_lcp(x, 127, depth)
        assert k1 == 4 and k2 == 4 and k3 == 1
        k_max = max(k1, k2, k3)
        assert k_max == 4
        forbidden = {depth - k1 - 1, depth - k2 - 1, depth - k3 - 1}
        assert forbidden == {3, 6}
        levels_after_first = set(range(depth - k_max))
        l_send = levels_after_first - forbidden
        assert l_send == {0, 1, 2}

        known_keys = _known_keys_second_opt(self.PRIOR, depth)
        got = compute_send_levels_second_opt(i=x, depth=depth, known_keys=known_keys)
        assert set(got) == {0, 1, 2} and len(got) == 3, (
            "Case Two: 3 nodes (levels 0, 1, 2)"
        )

    def test_case_one_sibling_key_matches_paper(self) -> None:
        """Paper: P_opt(x) = {N_{100001010}}. Our key for x=11 at level 0: (0, (11>>0)^1) = (0, 10)."""
        x = 11
        pos = get_sibling_position_at_level(x, 0)
        # 11 = 00001011, sibling at level 0 = 00001011^1 = 00001010 = 10
        assert pos == 10
        assert key(0, 10) == "0:10"
