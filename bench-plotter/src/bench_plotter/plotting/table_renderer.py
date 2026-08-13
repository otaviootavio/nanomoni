"""Tabular output: a rendered table PNG plus a sibling CSV of the same data.

Every "chart + the numbers behind it" pair in the package goes through here, so
the matplotlib table styling (stretched bbox, coloured header row, autosized
columns) and the ``<name>.png`` -> ``<name>.csv`` convention are defined once.

Callers pass *raw* row values: the CSV keeps them verbatim (so it stays
machine-readable at full precision) while the PNG shows them formatted for
reading.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, List, Sequence

import matplotlib.pyplot as plt

from .common import save_figure

_HEADER_COLOR = "#2a78d6"
_MISSING_CELL = "-"


def write_table_csv(
    col_labels: Sequence[str],
    rows: Sequence[Sequence[Any]],
    output_path: str,
) -> str:
    """Write ``rows`` as a CSV beside ``output_path``; return the CSV path."""
    csv_path = str(Path(output_path).with_suffix(".csv"))
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(col_labels))
        writer.writerows([list(row) for row in rows])
    return csv_path


def render_table_figure(
    col_labels: Sequence[str],
    cell_text: Sequence[Sequence[str]],
    title: str,
    output_path: str,
    *,
    bold_first_column: bool = False,
    show_title: bool = True,
) -> None:
    """Render already-formatted cell strings as a table PNG."""
    fig_height = 0.4 * (len(cell_text) + 1) + 0.9
    # A table with few columns but long names/values (e.g. "redis_memory_delta_mib")
    # needs more than the per-column floor below, or the longest cell clips against
    # its neighbor -- so width also scales with the longest cell seen anywhere.
    all_cells = [str(c) for c in col_labels] + [
        str(v) for row in cell_text for v in row
    ]
    max_cell_len = max((len(s) for s in all_cells), default=0)
    fig_width = max(8, 1.9 * len(col_labels), 0.5 * max_cell_len)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")
    # bbox stretches the table to fill the axes; the default loc="center" keeps it
    # at its intrinsic (small) size and leaves the rest of the figure blank.
    table = ax.table(
        cellText=[list(row) for row in cell_text],
        colLabels=list(col_labels),
        bbox=(0, 0, 1, 1),  # type: ignore[arg-type]  # matplotlib accepts a 4-tuple; stub only types Bbox
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.auto_set_column_width(list(range(len(col_labels))))
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold", color="white")
            cell.set_facecolor(_HEADER_COLOR)
        elif col == 0 and bold_first_column:
            cell.set_text_props(weight="bold")
    if show_title:
        ax.set_title(title, fontsize=17, pad=14)

    save_figure(fig, output_path)


def format_cell(value: Any) -> str:
    """Format one raw value for display: 3 significant figures, ``-`` for missing.

    Magnitudes of 1000 and up print in full rather than in the scientific notation
    ``%g`` switches to, because these are CPU seconds and payment counts that a
    reader compares digit-for-digit against the neighbouring cells and against the
    run's configured request count -- ``1.74e+03`` beside ``938`` defeats that.
    """
    if value is None:
        return _MISSING_CELL
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    numeric = float(value)
    if abs(numeric) >= 1000:
        return f"{numeric:.0f}"
    return f"{numeric:.3g}"


def create_stats_table(
    col_labels: Sequence[str],
    rows: Sequence[Sequence[Any]],
    title: str = "Statistics",
    output_path: str = "table.png",
    show_title: bool = True,
) -> None:
    """Write ``rows`` as both a CSV (raw values) and a table PNG (formatted)."""
    if not rows:
        print(f"No rows for table: {title}")
        return
    csv_path = write_table_csv(col_labels, rows, output_path)
    cell_text: List[List[str]] = [[format_cell(v) for v in row] for row in rows]
    render_table_figure(
        col_labels,
        cell_text,
        title,
        output_path,
        bold_first_column=True,
        show_title=show_title,
    )
    print(f"Table saved to: {output_path} (data: {csv_path})")
