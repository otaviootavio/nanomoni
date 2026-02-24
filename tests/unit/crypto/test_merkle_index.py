"""Unit tests for merkle_index (path, siblings, keys; no hashes).

Concepts verified: path Q(a), authentication path P(a), LCP, Property 1 (auth path
intersection), Property 2 (cross-path intersection), first and second compression.
"""

import pytest

from nanomoni.crypto.merkle_index import (
    compute_lcp,
    compute_send_levels_first_opt,
    compute_send_levels_second_opt,
    compute_tree_depth,
    get_ancestor_at_level,
    get_path_indexes,
    get_path_keys,
    get_sibling_indexes,
    get_sibling_keys,
    get_sibling_position_at_level,
    is_left_child,
    key,
    parent_position,
)


class TestKey:
    """Glossary: key = "level:position" notation for storage/retrieval."""

    def test_level0_position5(self) -> None:
        assert key(0, 5) == "0:5"

    def test_level2_position1(self) -> None:
        assert key(2, 1) == "2:1"

    def test_level0_position0(self) -> None:
        assert key(0, 0) == "0:0"


class TestComputeTreeDepth:
    """Depth n for 2^n leaves; authentication path has n levels."""

    def test_one_leaf_depth_zero(self) -> None:
        assert compute_tree_depth(0) == 0

    def test_two_leaves_depth_one(self) -> None:
        assert compute_tree_depth(1) == 1

    def test_four_leaves_depth_two(self) -> None:
        assert compute_tree_depth(3) == 2

    def test_eight_leaves_depth_three(self) -> None:
        assert compute_tree_depth(7) == 3

    def test_sixteen_leaves_depth_four(self) -> None:
        assert compute_tree_depth(15) == 4

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_i must be >= 0"):
            compute_tree_depth(-1)


class TestComputeLcp:
    """k = LCP(a,b) determines path intersection (Property 1, 2)."""

    def test_same_index(self) -> None:
        assert compute_lcp(5, 5, 4) == 4

    def test_differ_last_bit(self) -> None:
        assert compute_lcp(5, 4, 4) == 3

    def test_differ_first_bit(self) -> None:
        assert compute_lcp(8, 0, 4) == 0

    def test_one_bit_common(self) -> None:
        assert compute_lcp(2, 3, 2) == 1

    def test_negative_a_raises(self) -> None:
        with pytest.raises(ValueError, match="indices must be >= 0"):
            compute_lcp(-1, 0, 4)

    def test_negative_n_raises(self) -> None:
        with pytest.raises(ValueError, match="n must be >= 0"):
            compute_lcp(0, 0, -1)


class TestGetAncestorAtLevel:
    """Path Q(a) node at level i: position = leaf_index >> level."""

    def test_leaf5_level0(self) -> None:
        assert get_ancestor_at_level(5, 0) == 5

    def test_leaf5_level1(self) -> None:
        assert get_ancestor_at_level(5, 1) == 2

    def test_leaf5_level2(self) -> None:
        assert get_ancestor_at_level(5, 2) == 1

    def test_leaf5_level3(self) -> None:
        assert get_ancestor_at_level(5, 3) == 0

    def test_leaf0_all_levels(self) -> None:
        assert get_ancestor_at_level(0, 0) == 0
        assert get_ancestor_at_level(0, 1) == 0
        assert get_ancestor_at_level(0, 2) == 0


class TestGetSiblingPositionAtLevel:
    """Auth path P(a) sibling at level i: position = (leaf_index >> level) ^ 1."""

    def test_leaf5_level0(self) -> None:
        assert get_sibling_position_at_level(5, 0) == 4

    def test_leaf5_level1(self) -> None:
        assert get_sibling_position_at_level(5, 1) == 3

    def test_leaf5_level2(self) -> None:
        assert get_sibling_position_at_level(5, 2) == 0

    def test_leaf0_level0(self) -> None:
        assert get_sibling_position_at_level(0, 0) == 1


class TestGetPathIndexes:
    """Path Q(a) from leaf-parent to root; one node per level 0..depth."""

    def test_leaf5_depth3(self) -> None:
        assert get_path_indexes(5, 3) == [(0, 5), (1, 2), (2, 1), (3, 0)]

    def test_leaf0_depth2(self) -> None:
        assert get_path_indexes(0, 2) == [(0, 0), (1, 0), (2, 0)]

    def test_leaf3_depth2(self) -> None:
        assert get_path_indexes(3, 2) == [(0, 3), (1, 1), (2, 0)]

    def test_depth_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="depth must be >= 0"):
            get_path_indexes(0, -1)


class TestGetSiblingIndexes:
    """Auth path P(a) = siblings of path nodes; static data for verification."""

    def test_leaf5_depth3(self) -> None:
        assert get_sibling_indexes(5, 3) == [(0, 4), (1, 3), (2, 0)]

    def test_leaf0_depth2(self) -> None:
        assert get_sibling_indexes(0, 2) == [(0, 1), (1, 1)]


class TestGetPathKeys:
    """Keys for path Q(a); maps (level, index) to storage key "level:index"."""

    def test_leaf5_depth3(self) -> None:
        assert get_path_keys(5, 3) == ["0:5", "1:2", "2:1", "3:0"]


class TestGetSiblingKeys:
    """Keys for authentication path P(a); maps siblings to storage keys."""

    def test_leaf5_depth3(self) -> None:
        assert get_sibling_keys(5, 3) == ["0:4", "1:3", "2:0"]


class TestComputeSendLevelsFirstOpt:
    """First compression: P_pruned = levels j < n - k_max; only k_max matters."""

    def test_no_previous_proof_send_all_levels(self) -> None:
        assert compute_send_levels_first_opt(
            i=5, last_verified_index=None, depth=3
        ) == [0, 1, 2]

    def test_same_leaf_as_last_send_none(self) -> None:
        assert compute_send_levels_first_opt(i=5, last_verified_index=5, depth=3) == []

    def test_adjacent_leaf_send_level_zero_only(self) -> None:
        assert compute_send_levels_first_opt(i=5, last_verified_index=4, depth=3) == [0]

    def test_different_branches_send_all_levels(self) -> None:
        assert compute_send_levels_first_opt(i=2, last_verified_index=5, depth=3) == [
            0,
            1,
            2,
        ]

    def test_negative_i_raises(self) -> None:
        with pytest.raises(ValueError, match="i must be >= 0"):
            compute_send_levels_first_opt(i=-1, last_verified_index=None, depth=3)


class TestComputeSendLevelsSecondOpt:
    """Second compression: omit levels whose sibling is in known P union Q."""

    def test_empty_cache_send_all(self) -> None:
        assert compute_send_levels_second_opt(i=5, depth=3, known_keys=set()) == [
            0,
            1,
            2,
        ]

    def test_full_known_keys_send_none(self) -> None:
        known = {"0:4", "1:3", "2:0"}
        assert compute_send_levels_second_opt(i=5, depth=3, known_keys=known) == []

    def test_partial_known_keys_send_missing_levels(self) -> None:
        known = {"0:4"}
        assert compute_send_levels_second_opt(i=5, depth=3, known_keys=known) == [1, 2]


class TestIsLeftChild:
    """left_is_first = (index % 2) == 0; Hash order depends on this."""

    def test_even_position_is_left(self) -> None:
        assert is_left_child(0) is True
        assert is_left_child(2) is True
        assert is_left_child(4) is True

    def test_odd_position_is_right(self) -> None:
        assert is_left_child(1) is False
        assert is_left_child(5) is False


class TestParentPosition:
    """Parent index = q >> 1; parent of path node q_i at level i."""

    def test_parent_of_position(self) -> None:
        assert parent_position(0) == 0
        assert parent_position(1) == 0
        assert parent_position(2) == 1
        assert parent_position(3) == 1
        assert parent_position(5) == 2


class TestPathAndSiblingsForLeaf010In8LeafTree:
    """Example: leaf 010 (index 2), n=3; P(010) siblings at indices 1011, 0100, 0011.

    Derived as (1010>>i)^1 for i in 0..2.
    """

    def test_path_and_sibling_indexes_match_formula(self) -> None:
        depth = 3
        a = 2  # 010
        assert get_path_indexes(a, depth) == [(0, 2), (1, 1), (2, 0), (3, 0)]
        assert get_sibling_indexes(a, depth) == [(0, 3), (1, 0), (2, 1)]
        assert get_sibling_keys(a, depth) == ["0:3", "1:0", "2:1"]

    def test_sibling_at_each_level_equals_path_index_xor_one(self) -> None:
        a = 2
        assert get_sibling_position_at_level(a, 0) == 3  # (2>>0)^1
        assert get_sibling_position_at_level(a, 1) == 0  # (2>>1)^1
        assert get_sibling_position_at_level(a, 2) == 1  # (2>>2)^1


class TestAuthenticationPathIntersectionHasCardinalityK:
    """Property 1: |P(a1) cap P(a2)| = k where k = LCP(a1, a2).

    Intersection = siblings of the k common ancestors; paths converge at LCA.
    """

    def test_intersection_size_equals_lcp_for_two_leaves(self) -> None:
        n = 3
        depth = 3
        a1, a2 = 2, 3  # 010 and 011
        k = compute_lcp(a1, a2, n)
        assert k == 2
        # P(a1) siblings at levels 0,1,2; P(a2) siblings at levels 0,1,2.
        # Same sibling at level i iff path positions at level i are siblings, i.e. (a1>>i)^1 = (a2>>j)^1 for some j.
        # Same node = same (level, index). Intersection of (level, index) sets.
        p1_set = set(get_sibling_indexes(a1, depth))
        p2_set = set(get_sibling_indexes(a2, depth))
        intersection = p1_set & p2_set
        assert len(intersection) == k

    def test_no_common_prefix_implies_empty_intersection(self) -> None:
        n = 2
        depth = 2
        a1, a2 = 0, 3  # 00 and 11, LCP = 0
        k = compute_lcp(a1, a2, n)
        assert k == 0
        p1_set = set(get_sibling_indexes(a1, depth))
        p2_set = set(get_sibling_indexes(a2, depth))
        assert len(p1_set & p2_set) == 0


class TestCrossPathIntersectionAtLevelNMinusKMinus1:
    """Property 2: P(a2) cap Q(a1) has exactly one element at level n - k - 1.

    Unique intersection one layer below lowest common ancestor. Forbidden levels
    for second compression: F = {n - LCP(x, a_i) - 1} for each prior leaf a_i.
    """

    def test_intersection_level_equals_n_minus_lcp_minus_one(self) -> None:
        n = 8
        a1 = 0b10110101
        a2 = 0b10110011
        k = compute_lcp(a1, a2, n)
        assert k == 5
        intersection_level = n - k - 1
        assert intersection_level == 2

    def test_forbidden_levels_are_n_minus_ki_minus_one(self) -> None:
        n = 8
        x = 0b00001011
        k1 = compute_lcp(x, 0b00001111, n)
        k2 = compute_lcp(x, 0b00001000, n)
        k3 = compute_lcp(x, 0b01111111, n)
        assert k1 == 5 and k2 == 6
        assert k3 == 1
        forbidden = {n - k1 - 1, n - k2 - 1, n - k3 - 1}
        assert forbidden == {2, 1, 6}


# --- First compression: send levels 0 .. n - k_max - 1 ---


class TestPrunedPathSendsOnlyLevelsBelowNMinusKMax:
    """First compression: P_pruned(x) = nodes at levels j in {0, .., n-k_max-1}.

    Verifier knows levels j >= n - k_max from prior P(a_i). Only k_max matters.
    """

    def test_single_previous_leaf_k_max_determines_send_levels(self) -> None:
        n = 8
        x = 0b01010101
        a1 = 0b01010111
        k1 = compute_lcp(x, a1, n)
        assert k1 == 6
        send = compute_send_levels_first_opt(i=x, last_verified_index=a1, depth=n)
        assert send == [0, 1]

    def test_only_max_lcp_among_previous_leaves_matters(self) -> None:
        n = 8
        x = 0b01010101
        a1, a2, a3 = 0b01010111, 0b01001010, 0b11010101
        assert compute_lcp(x, a1, n) == 6
        assert compute_lcp(x, a2, n) == 3
        assert compute_lcp(x, a3, n) == 0
        send = compute_send_levels_first_opt(i=x, last_verified_index=a1, depth=n)
        assert send == [0, 1]


# --- Direct computation: L_send = {0, ..., n - k_max - 1} minus forbidden F ---


class TestLevelsToSendAfterFirstAndSecondCompression:
    """Direct computation: L_send = {0,..,n-k_max-1} minus forbidden F.

    First compression gives candidate levels; second compression removes forbidden
    levels (nodes verifier computed in Q(a_i)). Combines both strategies.
    """

    def test_case_x_00001011_k_max_6_F_1_2_6_L_send_0(self) -> None:
        n = 8
        x = 0b00001011
        a1, a2, a3 = 0b00001111, 0b00001000, 0b01111111
        k_max = max(compute_lcp(x, a1, n), compute_lcp(x, a2, n), compute_lcp(x, a3, n))
        assert k_max == 6
        levels_after_first = list(range(n - k_max))
        assert levels_after_first == [0, 1]
        forbidden = {
            n - compute_lcp(x, a1, n) - 1,
            n - compute_lcp(x, a2, n) - 1,
            n - compute_lcp(x, a3, n) - 1,
        }
        assert forbidden == {2, 1, 6}
        L_send = set(levels_after_first) - forbidden
        assert L_send == {0}

    def test_case_x_00000000_k_max_4_F_3_6_L_send_0_1_2(self) -> None:
        n = 8
        x = 0b00000000
        a1, a2, a3 = 0b00001111, 0b00001000, 0b01111111
        k_max = max(compute_lcp(x, a1, n), compute_lcp(x, a2, n), compute_lcp(x, a3, n))
        assert k_max == 4
        levels_after_first = list(range(n - k_max))
        assert levels_after_first == [0, 1, 2, 3]
        forbidden = {
            n - compute_lcp(x, a1, n) - 1,
            n - compute_lcp(x, a2, n) - 1,
            n - compute_lcp(x, a3, n) - 1,
        }
        assert forbidden == {3, 6}
        L_send = set(levels_after_first) - forbidden
        assert L_send == {0, 1, 2}
