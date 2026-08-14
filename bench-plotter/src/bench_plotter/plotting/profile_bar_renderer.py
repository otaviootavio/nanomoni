"""Per-mode vendor CPU time comparison: one stacked-bar PNG per TPS, plus a
combined CSV + rendered table image across every (tps, mode) cell.

x-axis = mode, sorted descending by total CPU time per payment so the
costliest mode reads first. Stacked bar segments = crypto / db read / db
write / other (unaccounted) CPU time per payment within that mode's endpoint
handler, in microseconds. The CSV keeps the underlying absolute seconds and
per-payment milliseconds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import matplotlib.pyplot as plt

from .common import save_figure
from .table_renderer import format_cell, render_table_figure, write_table_csv

_CRYPTO_COLOR = "#eda100"
# Two shades of the same blue: the split into read/write is a subdivision of
# what used to be one db segment, and the shared hue keeps that readable.
_DB_READ_COLOR = "#7db8ef"
_DB_WRITE_COLOR = "#1f5fae"
_OTHER_COLOR = "#b0b0b0"

# Label colour per segment fill: on top of the fill, chosen for contrast against
# it; beside the bar, a darkened version of the fill so a label sitting outside
# still says which segment it belongs to.
_INSIDE_TEXT_COLOR = {
    _CRYPTO_COLOR: "black",
    _DB_READ_COLOR: "black",
    _DB_WRITE_COLOR: "white",
    _OTHER_COLOR: "black",
}
_OUTSIDE_TEXT_COLOR = {
    _CRYPTO_COLOR: "#8a5e00",
    _DB_READ_COLOR: "#2a78d6",
    _DB_WRITE_COLOR: _DB_WRITE_COLOR,
    _OTHER_COLOR: "#5f5f5f",
}

# A segment thinner than this fraction of the tallest bar cannot hold its digits
# without them spilling into its neighbours, so its label goes beside the bar
# instead. The crypto segment is routinely this thin for the cheaper modes, and
# it is the one the chart exists to compare, so dropping the label is not an
# option.
_MIN_INSIDE_LABEL_FRACTION = 0.045

# Bar geometry, in x-axis units (one unit per mode). Narrower than matplotlib's
# 0.8 default to leave room for the labels of thin segments beside each bar.
_BAR_WIDTH = 0.62
_LABEL_GAP = 0.04

# Records carry per-payment CPU time in milliseconds, but a payment costs tens
# to hundreds of microseconds, so the chart plots microseconds: the segment
# labels then read 20.8 and 268 instead of 0.0208 and 0.268.
_MS_TO_US = 1000.0

# Stack order (bottom to top): legend label, record field, fill colour.
_BAR_SEGMENTS = (
    ("crypto (verify)", "crypto_ms_per_payment", _CRYPTO_COLOR),
    ("db read (mget)", "db_read_ms_per_payment", _DB_READ_COLOR),
    ("db write (run_script)", "db_write_ms_per_payment", _DB_WRITE_COLOR),
    ("other", "other_ms_per_payment", _OTHER_COLOR),
)

_CSV_FIELDS = [
    "tps",
    "mode",
    "total_time_s",
    "run_endpoint_time_s",
    "macro_time_s",
    "crypto_time_s",
    "db_read_time_s",
    "db_write_time_s",
    "other_time_s",
    "profile_payments",
    "crypto_ms_per_payment",
    "db_read_ms_per_payment",
    "db_write_ms_per_payment",
    "other_ms_per_payment",
]


def _label_segments(
    ax: Any,
    x: Sequence[int],
    bottoms: Sequence[float],
    values: Sequence[float],
    color: str,
    threshold: float,
) -> None:
    """Label every segment at its vertical centre, inside it or beside the bar."""
    for xi, bottom, value in zip(x, bottoms, values):
        if value <= 0:
            continue
        centre = bottom + value / 2
        if value >= threshold:
            ax.text(
                xi,
                centre,
                format_cell(value),
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                color=_INSIDE_TEXT_COLOR[color],
            )
            continue
        ax.text(
            xi + _BAR_WIDTH / 2 + _LABEL_GAP,
            centre,
            format_cell(value),
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=_OUTSIDE_TEXT_COLOR[color],
        )


def create_macro_micro_bar(
    records: List[Dict[str, Any]],
    title: str = "Vendor CPU time per payment: macro vs micro by mode",
    output_path: str = "profile_macro_micro.png",
) -> None:
    """Stacked bar per mode (crypto/db read/db write/other) for one TPS
    level.

    Bars are CPU microseconds **per payment** rather than the run's absolute
    seconds. A mode's absolute total scales with however many payments its
    window covered, so bar heights are only comparable across modes when every
    mode served the same count -- normalizing removes that dependency and is
    the like-for-like question anyway ("what does one payment cost").

    Each entry in ``records`` must provide ``mode`` and the
    ``*_ms_per_payment`` fields; records whose payment count was unavailable
    (leaving those fields ``None``) are dropped, since there is nothing to
    normalize by. Callers pass one TPS's worth of records per call (one PNG per
    TPS) rather than faceting multiple TPS into a single image, so each chart
    is legible on its own.

    Every segment is labelled with its own value and every bar with its total,
    so the chart is readable without opening the companion table.
    """
    usable = [
        r
        for r in records
        if all(r.get(field) is not None for _, field, _ in _BAR_SEGMENTS)
    ]
    if not usable:
        print(f"No profile records with a payment count for chart: {title}")
        return

    rows = {r["mode"]: r for r in usable}
    totals_by_mode = {
        m: sum(float(r[field]) for _, field, _ in _BAR_SEGMENTS) for m, r in rows.items()
    }
    # Descending by total CPU time per payment, so the costliest mode -- the one
    # this chart exists to flag -- reads first, left to right.
    modes = sorted(rows.keys(), key=lambda m: totals_by_mode[m], reverse=True)
    x = list(range(len(modes)))
    values = [
        [float(rows[m][field]) * _MS_TO_US for m in modes]
        for _, field, _ in _BAR_SEGMENTS
    ]
    bottoms: List[List[float]] = []
    running = [0.0] * len(modes)
    for segment_values in values:
        bottoms.append(list(running))
        running = [b + v for b, v in zip(running, segment_values)]
    totals = running

    fig, ax = plt.subplots(figsize=(max(7, 1.8 * len(modes)), 6.5))
    for (label, _, color), segment_values, bottom in zip(
        _BAR_SEGMENTS, values, bottoms
    ):
        ax.bar(
            x,
            segment_values,
            width=_BAR_WIDTH,
            bottom=bottom,
            color=color,
            label=label,
        )

    tallest = max(totals) if totals else 0.0
    threshold = tallest * _MIN_INSIDE_LABEL_FRACTION
    for (_, _, color), segment_values, bottom in zip(_BAR_SEGMENTS, values, bottoms):
        _label_segments(ax, x, bottom, segment_values, color, threshold)
    for xi, total in zip(x, totals):
        ax.text(
            xi,
            total + tallest * 0.015,
            format_cell(total),
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(modes, rotation=30, ha="right")
    ax.set_ylabel("CPU time per payment (µs)", fontsize=14)
    # Margin wide enough for a beside-the-bar label on the last mode too.
    ax.set_xlim(-0.5 - _BAR_WIDTH / 2, len(modes) - 0.5 + _BAR_WIDTH)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="both", which="major", labelsize=11)
    # Headroom for the per-bar totals, which sit just above the tallest bar.
    if tallest > 0:
        ax.set_ylim(bottom=0, top=tallest * 1.1)
    # The legend goes above the axes, between them and the title: inside the
    # axes it covers the tallest bar, which is the one the chart is about.
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=len(_BAR_SEGMENTS),
        frameon=False,
        fontsize=10,
    )
    ax.set_title(title, fontsize=15, pad=32)

    save_figure(fig, output_path)
    print(f"Macro/micro bar chart saved to: {output_path}")


def create_macro_micro_table(
    records: List[Dict[str, Any]],
    title: str = "Vendor CPU time by mode and TPS",
    output_path: str = "profile_macro_micro_table.png",
) -> None:
    """Write the combined (tps, mode) data as both a CSV and a rendered table PNG."""
    if not records:
        print(f"No profile records for macro/micro table: {title}")
        return

    sorted_rows = sorted(records, key=lambda r: (r["tps"], r["mode"]))
    raw_rows = [[row.get(field) for field in _CSV_FIELDS] for row in sorted_rows]
    csv_path = write_table_csv(_CSV_FIELDS, raw_rows, output_path)

    cell_text = [
        [str(int(row["tps"])), row["mode"]]
        + [format_cell(row.get(field)) for field in _CSV_FIELDS[2:]]
        for row in sorted_rows
    ]
    render_table_figure(_CSV_FIELDS, cell_text, title, output_path)
    print(f"Macro/micro table saved to: {output_path} (data: {csv_path})")
