"""Explicit level-set assertions for first and second compression (main.tex).

Asserts that the set of levels to send matches the spec:
- First opt: L_send = {0, 1, ..., n - k_max - 1}; only k_max = max_i LCP(x, a_i) matters.
- Second opt: L_send = {0, ..., n - k_max - 1} \\ F with F = {n - k_i - 1} for prior leaves.
"""

from __future__ import annotations

import pytest

from nanomoni.crypto.merkle_index import (
    compute_lcp,
    compute_send_levels_first_opt,
    compute_send_levels_second_opt,
    get_path_keys,
    get_sibling_keys,
)


def _expected_send_levels_first_opt(
    x: int, prior_indexes: list[int], depth: int
) -> list[int]:
    """Spec: send levels j in {0, 1, ..., n - k_max - 1} with k_max = max LCP(x, a_i)."""
    if not prior_indexes:
        return list(range(depth))
    k_max = max(compute_lcp(x, a, depth) for a in prior_indexes)
    return list(range(max(0, depth - k_max)))


def _expected_send_levels_second_opt(
    x: int, prior_indexes: list[int], depth: int
) -> list[int]:
    """Spec: L_send = {0, ..., n - k_max - 1} \\ F, F = {n - k_i - 1} for each prior."""
    if not prior_indexes:
        return list(range(depth))
    k_max = max(compute_lcp(x, a, depth) for a in prior_indexes)
    levels_after_first = set(range(depth - k_max))
    forbidden = {depth - compute_lcp(x, a, depth) - 1 for a in prior_indexes}
    return sorted(levels_after_first - forbidden)


def _known_keys_for_priors(prior_indexes: list[int], depth: int) -> set[str]:
    """K = union of P(a_i) ∪ Q(a_i) for each prior leaf a_i."""
    out: set[str] = set()
    for a in prior_indexes:
        out.update(get_sibling_keys(a, depth))
        out.update(get_path_keys(a, depth))
    return out


class TestFirstOptLevelSets:
    """First compression: assert send levels equal {0, ..., n - k_max - 1}."""

    @pytest.mark.parametrize("depth", [1, 2, 3, 8])
    def test_no_prior_sends_all_levels(self, depth: int) -> None:
        max_i = (1 << depth) - 1
        for x in [0, max_i, max_i // 2]:
            got = compute_send_levels_first_opt(
                i=x, last_verified_index=None, depth=depth
            )
            expected = list(range(depth))
            assert got == expected, f"x={x} depth={depth}"

    def test_single_prior_level_set(self) -> None:
        depth = 8
        # x=85 (01010101), a=87 (01010111) -> LCP=6, send levels 0..8-6-1 = {0,1}
        x, a = 85, 87
        got = compute_send_levels_first_opt(i=x, last_verified_index=a, depth=depth)
        expected = _expected_send_levels_first_opt(x, [a], depth)
        assert got == expected
        assert got == [0, 1]
        assert len(got) == depth - compute_lcp(x, a, depth)

    def test_multiple_priors_only_k_max_matters(self) -> None:
        depth = 8
        x = 85  # 01010101
        prior = [87, 74, 213]  # 01010111, 01001010, 11010101 -> k_max = 6 from a1
        got = compute_send_levels_first_opt(
            i=x, last_verified_index=prior[0], depth=depth
        )
        expected = _expected_send_levels_first_opt(x, prior, depth)
        assert expected == [0, 1], "spec: k_max=6 => levels {0,1}"
        assert got == expected

    def test_first_opt_level_count_equals_depth_minus_k_max(self) -> None:
        """Spec: number of levels sent = n - k_max."""
        depth = 3
        # x=2 (010), prior=[3] (011): LCP=2, send [0] only -> len 1 = depth - 2
        x, prior = 2, [3]
        expected = _expected_send_levels_first_opt(x, prior, depth)
        k_max = compute_lcp(x, prior[0], depth)
        assert len(expected) == depth - k_max
        assert expected == [0]


class TestSecondOptLevelSets:
    """Second compression: assert L_send = {0..n-k_max-1} \\ forbidden levels."""

    def test_no_prior_sends_all_levels(self) -> None:
        depth = 8
        got = compute_send_levels_second_opt(i=100, depth=depth, known_keys=set())
        assert set(got) == set(range(depth))

    def test_case_one_paper_forbidden_levels(self) -> None:
        """main.tex Section Example: x=00001011, a1,a2,a3 -> F={2,1,7}, L_send={0}."""
        depth = 8
        x = 0b00001011  # 11
        prior = [0b00001111, 0b00001000, 0b01111111]  # 15, 8, 127
        expected_levels = _expected_send_levels_second_opt(x, prior, depth)
        assert expected_levels == [0], "spec: Case One sends only level 0"

        known_keys = _known_keys_for_priors(prior, depth)
        got = compute_send_levels_second_opt(i=x, depth=depth, known_keys=known_keys)
        assert got == expected_levels

    def test_case_two_paper_forbidden_levels(self) -> None:
        """main.tex Section Example: x=00000000; L_send from spec formula (implementation LCP)."""
        depth = 8
        x = 0  # 00000000
        prior = [0b00001111, 0b00001000, 0b01111111]
        expected_levels = _expected_send_levels_second_opt(x, prior, depth)
        # With compute_lcp: LCP(0,15)=4, LCP(0,8)=4, LCP(0,127)=1 => k_max=4, F={3,6}, L_send={0,1,2}
        assert expected_levels == [0, 1, 2]

        known_keys = _known_keys_for_priors(prior, depth)
        got = compute_send_levels_second_opt(i=x, depth=depth, known_keys=known_keys)
        assert got == expected_levels

    def test_forbidden_level_formula(self) -> None:
        """Each prior a_i contributes forbidden level n - LCP(x, a_i) - 1."""
        depth = 8
        x = 11
        k1 = compute_lcp(x, 15, depth)
        k2 = compute_lcp(x, 8, depth)
        k3 = compute_lcp(x, 127, depth)
        assert k1 == 5 and k2 == 6 and k3 == 1  # 127: 00001011 vs 01111111 -> LCP 1
        f1 = depth - k1 - 1  # 2
        f2 = depth - k2 - 1  # 1
        f3 = depth - k3 - 1  # 6
        assert {f1, f2, f3} == {2, 1, 6}


class TestLevelSetConsistencyWithImplementation:
    """First-opt and second-opt implementations return the same sets as spec formulas."""

    def test_first_opt_matches_spec_for_several_pairs(self) -> None:
        depth = 8
        for x in [0, 85, 255]:
            for last in [None, 0, 85, 87, 255]:
                prior = [last] if last is not None else []
                expected = (
                    _expected_send_levels_first_opt(x, prior, depth)
                    if prior
                    else list(range(depth))
                )
                got = compute_send_levels_first_opt(
                    i=x, last_verified_index=last, depth=depth
                )
                assert got == expected

    def test_second_opt_matches_spec_for_paper_like_priors(self) -> None:
        depth = 8
        prior = [15, 8, 127]
        known_keys = _known_keys_for_priors(prior, depth)
        for x in [0, 11, 15, 8, 127, 200]:
            expected = _expected_send_levels_second_opt(x, prior, depth)
            got = compute_send_levels_second_opt(
                i=x, depth=depth, known_keys=known_keys
            )
            assert set(got) == set(expected), f"x={x}"
            assert sorted(got) == expected
