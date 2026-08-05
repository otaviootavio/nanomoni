"""Smoke tests for the flame-graph renderer, including the default crop to
the ``run_endpoint_function`` subtree (see flamebearer.focus_on)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from bench_plotter.plotting.flame_renderer import create_flame_graph

# names: 0 total, 1 outer, 2 run_endpoint_function, 3 receive_payment, 4 verify, 5 idle
_NAMES = [
    "total",
    "outer",
    "run_endpoint_function",
    "receive_payment",
    "verify",
    "idle",
]
_LEVELS = [
    [0, 100, 0, 0],
    [0, 100, 0, 1],
    [0, 80, 0, 2, 0, 20, 20, 5],
    [0, 60, 0, 3],
    [0, 10, 10, 4],
]

# Same shape but with no run_endpoint_function frame anywhere in the trace.
_NO_ENDPOINT_NAMES = ["total", "outer", "receive_payment", "verify", "idle"]
_NO_ENDPOINT_LEVELS = [
    [0, 100, 0, 0],
    [0, 100, 0, 1],
    [0, 80, 0, 2, 0, 20, 20, 4],
    [0, 10, 10, 3],
]


def _payload() -> Dict[str, Any]:
    return {
        "flamebearer": {
            "names": list(_NAMES),
            "levels": [list(lvl) for lvl in _LEVELS],
        },
        "metadata": {"sampleRate": 10.0},
    }


def _no_endpoint_payload() -> Dict[str, Any]:
    return {
        "flamebearer": {
            "names": list(_NO_ENDPOINT_NAMES),
            "levels": [list(lvl) for lvl in _NO_ENDPOINT_LEVELS],
        },
        "metadata": {"sampleRate": 10.0},
    }


class TestCreateFlameGraph:
    def test_default_focus_crops_to_run_endpoint_function(self, tmp_path: Path) -> None:
        out = tmp_path / "flame.png"
        create_flame_graph(
            _payload(),
            title="test flame graph",
            output_path=str(out),
            highlight={"verify": "#eda100"},
        )
        assert out.exists()
        assert out.stat().st_size > 0

    def test_focus_none_renders_full_tree(self, tmp_path: Path) -> None:
        out = tmp_path / "flame.png"
        create_flame_graph(_payload(), output_path=str(out), focus=None)
        assert out.exists()

    def test_focus_name_absent_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "flame.png"
        create_flame_graph(_no_endpoint_payload(), output_path=str(out))
        assert not out.exists()

    def test_empty_levels_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "flame.png"
        payload = {
            "flamebearer": {"names": [], "levels": []},
            "metadata": {"sampleRate": 10.0},
        }
        create_flame_graph(payload, output_path=str(out))
        assert not out.exists()
