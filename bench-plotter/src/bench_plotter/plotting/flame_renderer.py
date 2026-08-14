"""Render a Pyroscope flamebearer as a static icicle-style flame graph.

Pyroscope's own ``/render?format=png`` is not implemented by the deployed
server version (confirmed live: it silently falls back to JSON), so the image
is built here with matplotlib -- one horizontal row per call-tree depth via
``ax.broken_barh``, root at the top. Frames matching a target function name
(crypto / db read / db write, per mode -- see ``profiling.mode_functions``)
are colored to match the aggregate macro/micro bar chart's legend; everything
else is neutral grey. Labels are skipped on frames narrower than a fixed
fraction of the total width, the standard flamegraph convention -- a real
trace has ~900 distinct names and would be unreadable fully labeled.

By default the graph is cropped to the target function's subtree(s) (one per
request handled in the profiled window, tiled left-to-right) via
``flamebearer.focus_on`` -- the full process stack spends ~25 levels on
event-loop/syscall frames before ever reaching the handler code, which leaves
almost no room for the part anyone actually wants to read.

The axes is placed with ``fig.add_axes`` (fixed figure-fraction rect) rather
than ``plt.subplots``: ``save_figure()`` unconditionally calls
``fig.tight_layout()`` before saving, which recomputes subplot spacing and
undoes any manual title/legend placement above a `plt.subplots` axes -- axes
added via ``add_axes`` are left untouched by ``tight_layout`` (confirmed:
it emits a "not compatible" warning and skips them), which is what makes a
fixed top strip for the title + horizontal legend hold regardless of how
short the cropped graph is.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from bench_plotter.flamebearer import (
    focus_on,
    iter_levels,
    root_total_ticks,
    sample_rate,
)

from .common import save_figure
from .profile_bar_renderer import (
    _CRYPTO_COLOR,
    _DB_READ_COLOR,
    _DB_WRITE_COLOR,
)

_OTHER_COLOR = "#cfcfcf"
_MIN_LABEL_FRACTION = 0.006
_ROW_HEIGHT_IN = 0.16
DEFAULT_FOCUS = "run_endpoint_function"

# Fixed absolute margins (inches) reserved above/below the plot for the
# title+legend and the x-axis label, independent of fig_height -- this is
# what keeps them from colliding on a short (heavily cropped) graph.
_TOP_MARGIN_IN = 1.0
_BOTTOM_MARGIN_IN = 0.5
_SIDE_MARGIN_IN = 0.3


def create_flame_graph(
    flamebearer_payload: Dict[str, Any],
    title: str = "Flame graph",
    output_path: str = "flame.png",
    highlight: Optional[Dict[str, str]] = None,
    focus: Optional[str] = DEFAULT_FOCUS,
) -> None:
    """Draw one flame graph PNG from a Pyroscope flamebearer payload.

    ``highlight`` maps a function name to a hex color (crypto/db functions
    for the mode this profile belongs to); unmatched frames render neutral
    grey.
    ``focus`` (default ``"run_endpoint_function"``) crops the graph to that
    function's outermost occurrence(s) instead of rendering the full process
    stack; pass ``None`` to render the whole tree from the true root.
    """
    try:
        rate = sample_rate(flamebearer_payload)
        if focus:
            levels, total_ticks = focus_on(flamebearer_payload, focus)
            if not levels:
                print(f"'{focus}' not found in this profile; skipping: {title}")
                return
        else:
            levels = iter_levels(flamebearer_payload)
            total_ticks = root_total_ticks(flamebearer_payload)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"No flamebearer data for flame graph: {title} ({exc})")
        return
    if not levels or total_ticks <= 0:
        print(f"No flamebearer data for flame graph: {title}")
        return

    highlight = highlight or {}
    min_label_ticks = total_ticks * _MIN_LABEL_FRACTION
    n_levels = len(levels)
    fig_width = 14.0
    plot_height_in = max(2.0, min(26.0, n_levels * _ROW_HEIGHT_IN))
    fig_height = plot_height_in + _TOP_MARGIN_IN + _BOTTOM_MARGIN_IN
    fig = plt.figure(figsize=(fig_width, fig_height))

    # A fixed-fraction rect (not plt.subplots) so tight_layout -- called
    # unconditionally by save_figure() -- leaves this axes alone; see the
    # module docstring for why that matters here.
    left = _SIDE_MARGIN_IN / fig_width
    bottom = _BOTTOM_MARGIN_IN / fig_height
    top = 1 - _TOP_MARGIN_IN / fig_height
    ax = fig.add_axes((left, bottom, 1 - 2 * left, top - bottom))

    for depth, row in enumerate(levels):
        bars = [
            (start, end - start)
            for start, end, _total, _self, _name in row
            if end > start
        ]
        colors = [
            highlight.get(name, _OTHER_COLOR)
            for _s, _e, _t, _sf, name in row
            if _e > _s
        ]
        if not bars:
            continue
        ax.broken_barh(
            bars, (depth, 0.9), facecolors=colors, edgecolors="white", linewidth=0.15
        )
        for start, end, _total, _self, name in row:
            width = end - start
            if width < min_label_ticks:
                continue
            label = ax.text(
                start + width / 2,
                depth + 0.45,
                name,
                ha="center",
                va="center",
                fontsize=6,
                clip_on=True,
            )
            # Clip to this box's own rectangle so a label never bleeds into a
            # neighboring frame -- axes-boundary clipping alone doesn't do this.
            clip_box = plt.Rectangle((start, depth), width, 0.9, transform=ax.transData)
            label.set_clip_path(clip_box)

    ax.set_xlim(0, total_ticks)
    ax.set_ylim(0, n_levels)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    scope = f"'{focus}' total" if focus else "total"
    ax.set_xlabel(f"CPU time ({scope} {total_ticks / rate:.2f}s)", fontsize=11)

    # Title and legend live in the fixed top margin, positioned in absolute
    # figure-fraction terms (derived from fig_height, which we control) so
    # they never collide regardless of how short the cropped graph is -- an
    # axes-fraction bbox_to_anchor (e.g. 1.06) shrinks to almost nothing in
    # physical terms once the axes itself is only ~2in tall.
    fig.text(0.5, 1 - 0.32 / fig_height, title, ha="center", va="top", fontsize=14)

    legend_patches = [
        mpatches.Patch(color=_CRYPTO_COLOR, label="crypto (verify)"),
        mpatches.Patch(color=_DB_READ_COLOR, label="db read (mget)"),
        mpatches.Patch(color=_DB_WRITE_COLOR, label="db write (run_script)"),
        mpatches.Patch(color=_OTHER_COLOR, label="other"),
    ]
    fig.legend(
        handles=legend_patches,
        loc="center",
        bbox_to_anchor=(0.5, 1 - 0.72 / fig_height),
        bbox_transform=fig.transFigure,
        ncol=4,
        fontsize=9,
    )

    with warnings.catch_warnings():
        # Expected: save_figure()'s tight_layout() call skips this add_axes
        # axes by design (see module docstring); the warning would otherwise
        # fire on every single flame graph rendered.
        warnings.filterwarnings("ignore", message="This figure includes Axes")
        save_figure(fig, output_path)
    print(f"Flame graph saved to: {output_path}")
