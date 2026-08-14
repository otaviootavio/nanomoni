"""Render the expected-vs-real TPS chart and write the saturation summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bench_plotter.io_utils import load_timing_file, load_virtual_clients
from bench_plotter.plotting.sweep_renderers import (
    create_delta_table,
    create_identity_comparison_plot,
)
from bench_plotter.profiling.aggregate import generate_profile_outputs

from .aggregate import (
    build_delta_table,
    build_series,
    collect_points,
    saturation_tps,
    summarize,
)

_CHART_FILENAME = "expected_vs_real_tps.png"
_TABLE_FILENAME = "expected_vs_real_delta_table.png"
_SUMMARY_FILENAME = "tps_saturation.json"


def _client_config_label(virtual_clients: Optional[int]) -> str:
    """Describe the client concurrency behind a run, for chart titles.

    Each virtual client still runs its own sequential await loop (see
    ``run_tps_saturation_sweep.sh``); only their count varies, so the wording
    must stay accurate whether there is one or many.
    """
    if virtual_clients is None:
        return "sequential client(s), count unknown"
    if virtual_clients == 1:
        return "single sequential client"
    return f"{virtual_clients} virtual clients, each sequential"


def _format_point(point: Dict[str, Any]) -> str:
    achieved = point["achieved_tps"]
    if achieved is None:
        return f"  {point['mode']:>20} target {point['expected_tps']:>7.0f} -> no data"
    if point.get("rate_window_too_short"):
        verdict = "UNMEASURABLE (run too short)"
    else:
        verdict = "on target" if point["met_target"] else "SHORT"
    return (
        f"  {point['mode']:>20} target {point['expected_tps']:>7.0f} -> "
        f"real {achieved:>8.1f} ({point['ratio'] * 100:5.1f}%) {verdict}"
    )


def generate_saturation_report(
    timing_path: str,
    output_root: str = "plots",
    show_title: bool = True,
) -> Tuple[List[str], Dict[str, Any]]:
    """Read a sweep timing file, emit the chart + JSON summary.

    Returns ``(written_paths, summary)``. Output lands in
    ``<output_root>/<server_run_timestamp>/`` so a saturation run sits alongside
    the regular sweep plots for the same benchmark.
    """
    server_ts, runs = load_timing_file(timing_path)
    client_label = _client_config_label(load_virtual_clients(timing_path))
    # Include failed runs: a client that dies mid-sweep is exactly the kind of
    # result worth seeing next to the on-target points.
    if not runs:
        print(f"No runs found in {timing_path}")
        return [], {}

    print(f"Resolving achieved TPS for {len(runs)} run(s)...")
    points = collect_points(runs)
    if not points:
        print("No achieved-TPS points resolved; nothing to plot")
        return [], {}

    for point in points:
        print(_format_point(point))

    out_dir = Path(output_root) / server_ts
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []

    series = build_series(points)
    if series:
        chart_path = out_dir / _CHART_FILENAME
        create_identity_comparison_plot(
            series_list=series,
            title=f"Expected vs Real TPS ({client_label})",
            output_path=str(chart_path),
            x_axis_label="Expected TPS (client target)",
            y_axis_label="Real TPS (vendor, success)",
            identity_label="y = x (real = expected)",
            show_title=show_title,
        )
        written.append(str(chart_path))

    table = build_delta_table(points)
    if table["tps_values"] and table["modes"]:
        table_path = out_dir / _TABLE_FILENAME
        create_delta_table(
            tps_values=table["tps_values"],
            modes=table["modes"],
            achieved=table["achieved"],
            title=(
                "Real TPS by target and protocol "
                f"(% = of target achieved; {client_label})"
            ),
            output_path=str(table_path),
            show_title=show_title,
        )
        written.append(str(table_path))
        # create_delta_table writes a sibling CSV; record it so callers reporting
        # "files written" do not undercount the outputs.
        written.append(str(table_path.with_suffix(".csv")))

    # Same profiling stage the full sweep runs (sweep/runner.py): the flame graph
    # and the macro/micro split are what say *why* a mode stopped where the chart
    # above shows it stopping. Needs tps on the run, and swallows its own errors,
    # so an unreachable Pyroscope costs the profiles and not the report.
    written.extend(
        generate_profile_outputs(
            [run for run in runs if run.get("tps") is not None],
            output_dir=str(out_dir),
            show_title=show_title,
        )
    )

    summary = summarize(points)
    summary_path = out_dir / _SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    written.append(str(summary_path))
    print(f"Saturation summary saved to: {summary_path}")

    for mode in sorted({p["mode"] for p in points}):
        ceiling = saturation_tps(points, mode)
        mode_points = [p for p in points if p["mode"] == mode]
        if ceiling is not None:
            print(f"{mode}: max sustained target = {ceiling:.0f} TPS")
        elif all(p.get("rate_window_too_short") for p in mode_points):
            # Distinguish "cannot measure" from "client could not keep up": with
            # every run shorter than the rate window, nothing was learned.
            print(f"{mode}: no verdict -- every run was too short to measure")
        else:
            print(f"{mode}: fell short at every target tested")

    return written, summary
