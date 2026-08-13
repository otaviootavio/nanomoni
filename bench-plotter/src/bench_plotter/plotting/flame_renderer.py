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

A highlighted name can occur nested inside itself (confirmed live: our own
``KeyValueStore.mget`` wraps redis-py's own ``mget`` frame). Coloring every
matching frame regardless of tree position would paint that inner occurrence
the same color as the outer one, which reads as the read being counted
twice -- it isn't; ``profiling.aggregate`` sums only the outermost occurrence
per path, since the outer node's ``total_ticks`` already includes the inner
one's. ``flamebearer.iter_levels``/``focus_on``'s ``shadow_names`` tags each
such inner occurrence as ``shadowed``, and this renderer draws a shadowed
frame as a plain "other" frame instead of re-highlighting it, so the picture
matches what the numbers actually count.

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

Figure width tracks height at a ~4:3 ratio rather than a flat constant: height
already scales with tree depth (``_ROW_HEIGHT_IN`` per level, clamped), so a
heavily-cropped graph -- the common case, since the default focus crops to one
handler's subtree -- used to sit in a canvas far wider than its content needed.
Clamped to ``[_MIN_WIDTH_IN, _MAX_WIDTH_IN]`` so neither a very shallow nor a
very deep trace pushes the aspect ratio to an extreme.
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
    _INSIDE_TEXT_COLOR,
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

# Width = height * 4/3, clamped to this range -- see module docstring.
_MIN_WIDTH_IN = 8.0
_MAX_WIDTH_IN = 12.0

# In-frame label styling for categorized (crypto/db) frames vs. neutral grey
# ones: a real trace has ~900 distinct grey "other" names, and making all of
# them legible isn't the goal -- picking the handful of categorized ones out
# from the clutter is.
_HIGHLIGHT_FONTSIZE = 9
_OTHER_FONTSIZE = 6


def create_flame_graph(
    flamebearer_payload: Dict[str, Any],
    title: str = "Flame graph",
    output_path: str = "flame.png",
    highlight: Optional[Dict[str, str]] = None,
    focus: Optional[str] = DEFAULT_FOCUS,
    show_title: bool = True,
) -> None:
    """Draw one flame graph PNG from a Pyroscope flamebearer payload.

    ``highlight`` maps a function name to a hex color (crypto/db functions
    for the mode this profile belongs to); unmatched frames render neutral
    grey.
    ``focus`` (default ``"run_endpoint_function"``) crops the graph to that
    function's outermost occurrence(s) instead of rendering the full process
    stack; pass ``None`` to render the whole tree from the true root.
    """
    highlight = highlight or {}
    try:
        rate = sample_rate(flamebearer_payload)
        if focus:
            levels, total_ticks = focus_on(
                flamebearer_payload, focus, shadow_names=highlight.keys()
            )
            if not levels:
                print(f"'{focus}' not found in this profile; skipping: {title}")
                return
        else:
            levels = iter_levels(flamebearer_payload, shadow_names=highlight.keys())
            total_ticks = root_total_ticks(flamebearer_payload)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"No flamebearer data for flame graph: {title} ({exc})")
        return
    if not levels or total_ticks <= 0:
        print(f"No flamebearer data for flame graph: {title}")
        return

    min_label_ticks = total_ticks * _MIN_LABEL_FRACTION
    n_levels = len(levels)
    plot_height_in = max(2.0, min(26.0, n_levels * _ROW_HEIGHT_IN))
    fig_height = plot_height_in + _TOP_MARGIN_IN + _BOTTOM_MARGIN_IN
    fig_width = max(_MIN_WIDTH_IN, min(_MAX_WIDTH_IN, fig_height * 4 / 3))
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
            for start, end, _total, _self, _name, _shadowed in row
            if end > start
        ]
        colors = [
            _OTHER_COLOR if shadowed else highlight.get(name, _OTHER_COLOR)
            for _s, _e, _t, _sf, name, shadowed in row
            if _e > _s
        ]
        if not bars:
            continue
        ax.broken_barh(
            bars, (depth, 0.9), facecolors=colors, edgecolors="white", linewidth=0.15
        )
        for start, end, _total, _self, name, shadowed in row:
            width = end - start
            if width < min_label_ticks:
                continue
            is_highlighted = name in highlight and not shadowed
            if is_highlighted:
                label_kwargs: Dict[str, Any] = {
                    "fontsize": _HIGHLIGHT_FONTSIZE,
                    "fontweight": "bold",
                    "color": _INSIDE_TEXT_COLOR[highlight[name]],
                }
            else:
                label_kwargs = {"fontsize": _OTHER_FONTSIZE}
            label = ax.text(
                start + width / 2,
                depth + 0.45,
                name,
                ha="center",
                va="center",
                clip_on=True,
                **label_kwargs,
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
    ax.set_xlabel(f"CPU time ({scope} {total_ticks / rate:.2f}s)", fontsize=14)

    # Title and legend live in the fixed top margin, positioned in absolute
    # figure-fraction terms (derived from fig_height, which we control) so
    # they never collide regardless of how short the cropped graph is -- an
    # axes-fraction bbox_to_anchor (e.g. 1.06) shrinks to almost nothing in
    # physical terms once the axes itself is only ~2in tall.
    if show_title:
        fig.text(0.5, 1 - 0.32 / fig_height, title, ha="center", va="top", fontsize=18)

    legend_patches = [
        mpatches.Patch(color=_CRYPTO_COLOR, label="crypto (verify)"),
        mpatches.Patch(color=_DB_READ_COLOR, label="db read (mget)"),
        mpatches.Patch(color=_DB_WRITE_COLOR, label="db write (run_script)"),
        mpatches.Patch(color=_OTHER_COLOR, label="other"),
    ]
    fig.legend(
        handles=legend_patches,
        loc="center left",
        bbox_to_anchor=(left, 1 - 0.72 / fig_height),
        bbox_transform=fig.transFigure,
        ncol=4,
        fontsize=12,
        frameon=False,
    )

    with warnings.catch_warnings():
        # Expected: save_figure()'s tight_layout() call skips this add_axes
        # axes by design (see module docstring); the warning would otherwise
        # fire on every single flame graph rendered.
        warnings.filterwarnings("ignore", message="This figure includes Axes")
        save_figure(fig, output_path)
    print(f"Flame graph saved to: {output_path}")
