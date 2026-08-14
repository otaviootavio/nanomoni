"""Unit tests for flamebearer tree reconstruction and name-based tick summation.

The fixture below deliberately reproduces a pattern confirmed against a live
Pyroscope trace: ``receive_payment`` appears as both an ancestor and a
descendant of itself (a router wrapping a same-named use-case call). Summing
every node with a given name would double-count that nested occurrence; the
outermost-occurrence rules under test exist specifically to avoid it.
"""

from __future__ import annotations

from typing import Any, Dict

from bench_plotter.flamebearer import (
    build_tree,
    focus_on,
    iter_levels,
    outermost_nodes,
    root_total_ticks,
    sample_rate,
    sum_ticks_by_name,
    sum_ticks_within,
)

# names: 0 total, 1 outer, 2 receive_payment, 3 idle, 4 get_by_id, 5 verify, 6 get_x
_NAMES = ["total", "outer", "receive_payment", "idle", "get_by_id", "verify", "get_x"]
_LEVELS = [
    [0, 100, 0, 0],
    [0, 100, 0, 1],
    [0, 80, 0, 2, 0, 20, 20, 3],
    [0, 30, 0, 2, 0, 20, 20, 4],
    [0, 10, 10, 5, 0, 5, 5, 6],
]


def _payload() -> Dict[str, Any]:
    return {
        "flamebearer": {
            "names": list(_NAMES),
            "levels": [list(lvl) for lvl in _LEVELS],
        },
        "metadata": {"sampleRate": 1_000_000_000},
    }


class TestBuildTree:
    def test_reconstructs_parent_child_shape(self) -> None:
        root = build_tree(_payload())
        assert root.name == "total"
        assert root.total_ticks == 100
        assert len(root.children) == 1

        outer = root.children[0]
        assert outer.name == "outer"
        assert [c.name for c in outer.children] == ["receive_payment", "idle"]

        outer_rp, idle = outer.children
        assert outer_rp.total_ticks == 80
        assert idle.total_ticks == 20 and idle.self_ticks == 20

        assert [c.name for c in outer_rp.children] == ["receive_payment", "get_by_id"]
        nested_rp, get_by_id = outer_rp.children
        assert nested_rp.total_ticks == 30
        assert get_by_id.total_ticks == 20

        assert [c.name for c in nested_rp.children] == ["verify", "get_x"]


class TestSampleRateAndTotals:
    def test_sample_rate(self) -> None:
        assert sample_rate(_payload()) == 1_000_000_000.0

    def test_root_total_ticks(self) -> None:
        assert root_total_ticks(_payload()) == 100


class TestIterLevels:
    def test_resolves_names_and_spans(self) -> None:
        levels = iter_levels(_payload())
        assert levels[2] == [
            (0, 80, 80, 0, "receive_payment", False),
            (80, 100, 20, 20, "idle", False),
        ]

    def test_marks_nested_occurrence_as_shadowed(self) -> None:
        # depth 3's "receive_payment" (0-30) is nested inside depth 2's (0-80)
        # -- the same shape a store's own mget wrapping redis-py's own mget
        # has. Only the inner occurrence is shadowed; the outer one and
        # unrelated names are not.
        levels = iter_levels(_payload(), shadow_names=["receive_payment"])
        assert levels[2] == [
            (0, 80, 80, 0, "receive_payment", False),
            (80, 100, 20, 20, "idle", False),
        ]
        assert levels[3] == [
            (0, 30, 30, 0, "receive_payment", True),
            (30, 50, 20, 20, "get_by_id", False),
        ]

    def test_no_shadow_names_marks_nothing(self) -> None:
        levels = iter_levels(_payload())
        assert levels[3] == [
            (0, 30, 30, 0, "receive_payment", False),
            (30, 50, 20, 20, "get_by_id", False),
        ]


class TestOutermostNodes:
    def test_finds_only_the_outer_occurrence(self) -> None:
        root = build_tree(_payload())
        nodes = outermost_nodes(root, "receive_payment")
        assert len(nodes) == 1
        assert nodes[0].total_ticks == 80

    def test_missing_name_returns_empty(self) -> None:
        root = build_tree(_payload())
        assert outermost_nodes(root, "does_not_exist") == []


class TestSumTicksByName:
    def test_recursive_name_is_not_double_counted(self) -> None:
        root = build_tree(_payload())
        totals = sum_ticks_by_name(root, ["receive_payment"])
        # Naively summing both occurrences (80 + 30) would double-count the
        # nested one, since the outer node's total already includes it.
        assert totals["receive_payment"] == 80

    def test_sums_multiple_independent_names(self) -> None:
        root = build_tree(_payload())
        totals = sum_ticks_by_name(
            root, ["receive_payment", "verify", "get_by_id", "get_x", "idle"]
        )
        assert totals == {
            "receive_payment": 80,
            "verify": 10,
            "get_by_id": 20,
            "get_x": 5,
            "idle": 20,
        }

    def test_absent_name_totals_zero(self) -> None:
        root = build_tree(_payload())
        assert sum_ticks_by_name(root, ["nope"]) == {"nope": 0}


class TestSumTicksWithin:
    def test_scoped_to_given_subtrees_only(self) -> None:
        root = build_tree(_payload())
        endpoint_nodes = outermost_nodes(root, "receive_payment")
        totals = sum_ticks_within(endpoint_nodes, ["verify", "get_by_id", "idle"])
        # "idle" is a sibling of receive_payment, not inside its subtree.
        assert totals == {"verify": 10, "get_by_id": 20, "idle": 0}


# names: 0 total, 1 outer, 2 run_endpoint_function, 3 idle, 4 receive_payment, 5 verify
# Two separate run_endpoint_function occurrences (two requests handled in the
# window), each with its own receive_payment -> verify subtree, interleaved
# with unrelated "idle" siblings -- reproduces the shape a real trimmed-window
# profile has (many per-request subtrees scattered across a busy event loop).
_FOCUS_NAMES = [
    "total",
    "outer",
    "run_endpoint_function",
    "idle",
    "receive_payment",
    "verify",
]
_FOCUS_LEVELS = [
    [0, 100, 0, 0],
    [0, 100, 0, 1],
    [0, 30, 10, 2, 0, 10, 10, 3, 0, 30, 5, 2, 0, 30, 30, 3],
    [0, 20, 15, 4, 20, 25, 15, 4],
    [0, 5, 5, 5, 35, 10, 10, 5],
]


def _focus_payload() -> Dict[str, Any]:
    return {
        "flamebearer": {
            "names": list(_FOCUS_NAMES),
            "levels": [list(lvl) for lvl in _FOCUS_LEVELS],
        },
        "metadata": {"sampleRate": 10.0},
    }


class TestFocusOn:
    def test_tiles_every_occurrence_from_depth_zero(self) -> None:
        levels, total_ticks = focus_on(_focus_payload(), "run_endpoint_function")
        assert total_ticks == 60  # 30 + 30, the two occurrences

        assert levels[0] == [
            (0, 30, 30, 10, "run_endpoint_function", False),
            (30, 60, 30, 5, "run_endpoint_function", False),
        ]
        assert levels[1] == [
            (0, 20, 20, 15, "receive_payment", False),
            (30, 55, 25, 15, "receive_payment", False),
        ]
        assert levels[2] == [
            (0, 5, 5, 5, "verify", False),
            (30, 40, 10, 10, "verify", False),
        ]

    def test_missing_name_returns_empty(self) -> None:
        levels, total_ticks = focus_on(_focus_payload(), "does_not_exist")
        assert levels == []
        assert total_ticks == 0

    def test_marks_name_nested_inside_the_focused_subtree_as_shadowed(self) -> None:
        # Reproduces a store's own "mget" wrapping redis-py's own "mget" one
        # level below the focused endpoint: within a single
        # run_endpoint_function occurrence, "receive_payment" here wraps a
        # same-named nested call, mirroring _FOCUS_LEVELS' first occurrence
        # shape but naming the child after its parent.
        names = ["total", "outer", "run_endpoint_function", "mget", "mget"]
        levels_raw = [
            [0, 30, 0, 0],
            [0, 30, 0, 1],
            [0, 30, 5, 2],
            [0, 25, 5, 3],
            [0, 20, 20, 4],
        ]
        payload = {
            "flamebearer": {"names": names, "levels": levels_raw},
            "metadata": {"sampleRate": 10.0},
        }
        levels, _total_ticks = focus_on(
            payload, "run_endpoint_function", shadow_names=["mget"]
        )
        assert levels[1] == [(0, 25, 25, 5, "mget", False)]
        assert levels[2] == [(0, 20, 20, 20, "mget", True)]
