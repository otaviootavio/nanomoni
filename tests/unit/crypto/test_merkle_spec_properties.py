"""Direct tests for main.tex spec properties (Property 1 and Property 2).

- Property 1 (Authentication path intersection): |P(a) ∩ P(b)| = LCP(a, b).
- Property 2 (Cross-path intersection): |P(x) ∩ Q(a)| = 1 at level n - LCP(x, a) - 1.
- Cardinality of P(x) ∩ ∪_i Q(a_i): between 1 and m (distinct levels).
"""

from __future__ import annotations

import pytest

from nanomoni.crypto.merkle_index import (
    compute_lcp,
    get_ancestor_at_level,
    get_sibling_keys,
    get_sibling_position_at_level,
    key,
)


def _p_set(leaf_index: int, depth: int) -> set[str]:
    """Authentication path P(a) as set of keys (level, sibling position)."""
    return set(get_sibling_keys(leaf_index, depth))


def _q_set(leaf_index: int, depth: int) -> set[str]:
    """Node path Q(a) as set of keys (level, ancestor position). Levels 0..depth-1 (P has same)."""
    return {
        key(level, get_ancestor_at_level(leaf_index, level)) for level in range(depth)
    }


class TestProperty1AuthenticationPathIntersection:
    """Property 1: |P(a) ∩ P(b)| = LCP(a, b)."""

    def test_property1_two_leaves_same_prefix(self) -> None:
        """a=85 (01010101), b=87 (01010111): LCP=6 => |P(a)∩P(b)|=6."""
        depth = 8
        a, b = 85, 87
        pa = _p_set(a, depth)
        pb = _p_set(b, depth)
        inter = pa & pb
        k = compute_lcp(a, b, depth)
        assert len(inter) == k, "Property 1: |P(a) ∩ P(b)| = LCP(a,b)"
        assert k == 6

    def test_property1_two_leaves_no_common_prefix(self) -> None:
        """a=0, b=255: LCP=0 => intersection empty."""
        depth = 8
        a, b = 0, 255
        pa = _p_set(a, depth)
        pb = _p_set(b, depth)
        k = compute_lcp(a, b, depth)
        assert len(pa & pb) == k
        assert k == 0

    def test_property1_identical_leaves(self) -> None:
        """a=b => LCP=n => |P(a)∩P(b)| = n."""
        depth = 8
        a = 42
        pa = _p_set(a, depth)
        k = compute_lcp(a, a, depth)
        assert k == depth
        assert len(pa) == depth
        assert len(pa & pa) == depth

    def test_property1_paper_example_p_a2_cap_p_a1(self) -> None:
        """main.tex Section 4.1: P(a) ∩ P(b) has size LCP(a,b); intersection = siblings of k common ancestors."""
        depth = 8
        a1 = 0b10110101  # 181
        a2 = 0b10110011  # 179
        k = compute_lcp(a1, a2, depth)
        assert k == 5, "paper: LCP(10110101, 10110011) = 5"
        pa1 = _p_set(a1, depth)
        pa2 = _p_set(a2, depth)
        assert len(pa1 & pa2) == k

    @pytest.mark.parametrize("depth", [1, 2, 3, 5, 8])
    def test_property1_holds_for_random_pairs(self, depth: int) -> None:
        max_i = (1 << depth) - 1
        for a in [0, 1, max_i // 2, max_i]:
            for b in [0, 1, max_i // 2, max_i]:
                if a == b:
                    continue
                pa = _p_set(a, depth)
                pb = _p_set(b, depth)
                k = compute_lcp(a, b, depth)
                assert len(pa & pb) == k


class TestProperty2CrossPathIntersection:
    """Property 2: |P(x) ∩ Q(a)| = 1 at level i = n - LCP(x, a) - 1."""

    def test_property2_unique_intersection_level(self) -> None:
        """Intersection is exactly one key, at level n - LCP(x,a) - 1."""
        depth = 8
        x, a = 0b10110011, 0b10110101  # paper example: a1=181, a2=179; P(a2)∩Q(a1)
        k = compute_lcp(a, x, depth)
        expected_level = depth - k - 1
        px = _p_set(x, depth)
        qa = _q_set(a, depth)
        inter = px & qa
        assert len(inter) == 1, "Property 2: exactly one intersection"
        (key_str,) = inter
        level = int(key_str.split(":")[0])
        assert level == expected_level, (
            f"intersection at level n-k-1 = {expected_level}"
        )

    def test_property2_paper_example_level_two(self) -> None:
        """main.tex Section 'Example of Characterizing P(a2) ∩ Q(a1)': LCP=5, n=8 => level 2."""
        depth = 8
        a1 = 0b10110101  # 181
        a2 = 0b10110011  # 179
        k = compute_lcp(a1, a2, depth)
        assert k == 5
        assert depth - k - 1 == 2
        qa1 = _q_set(a1, depth)
        pa2 = _p_set(a2, depth)
        inter = pa2 & qa1
        assert len(inter) == 1
        (key_str,) = inter
        level = int(key_str.split(":")[0])
        assert level == 2
        pos = int(key_str.split(":")[1])
        assert get_sibling_position_at_level(a2, 2) == pos
        assert get_ancestor_at_level(a1, 2) == pos

    @pytest.mark.parametrize("depth", [2, 3, 5, 8])
    def test_property2_holds_for_distinct_pairs(self, depth: int) -> None:
        max_i = (1 << depth) - 1
        for x in [0, 1, max_i // 3, max_i]:
            for a in [0, 1, max_i // 3, max_i]:
                if x == a:
                    continue
                px = _p_set(x, depth)
                qa = _q_set(a, depth)
                inter = px & qa
                assert len(inter) == 1
                k = compute_lcp(x, a, depth)
                expected_level = depth - k - 1
                (key_str,) = inter
                level = int(key_str.split(":")[0])
                assert level == expected_level


class TestCrossPathUnionCardinality:
    """|P(x) ∩ ∪_i Q(a_i)| is between 1 and m (main.tex Section 5)."""

    def test_cardinality_lower_bound_one(self) -> None:
        """All priors same LCP with x => single intersection level => size 1."""
        depth = 8
        x = 85
        prior = [87, 86, 84]  # all share high LCP with 85
        levels = {depth - compute_lcp(x, a, depth) - 1 for a in prior}
        assert len(levels) >= 1
        # When all LCP equal, one level
        prior_same = [87, 86]  # 01010111, 01010110 -> LCP with 85 = 6 for both
        levels_same = {depth - compute_lcp(x, a, depth) - 1 for a in prior_same}
        assert len(levels_same) == 1

    def test_cardinality_upper_bound_m(self) -> None:
        """Distinct LCP(x, a_i) => at most m distinct levels."""
        depth = 8
        x = 0
        prior = [0b00001111, 0b00001000, 0b01111111]  # 15, 8, 127
        levels = {depth - compute_lcp(x, a, depth) - 1 for a in prior}
        assert 1 <= len(levels) <= len(prior)
        # LCP(0,15)=4, LCP(0,8)=4, LCP(0,127)=1 => levels {3, 3, 6} => {3, 6}
        assert levels == {3, 6}
