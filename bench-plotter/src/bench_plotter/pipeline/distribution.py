"""Plan stage for frequency-distribution histogram jobs.

Owns only the plan-side job construction: each series is the cumulative bucket
state at the end of a mode's window, read via an instant query with a
range-query fallback. Transform-side math lives in :mod:`.distribution_transform`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .model import PlotJob, QuerySpec
from .naming import extract_payment_mode_from_expr, sanitize_filename


def build_distribution_jobs(
    dist_by_title: Dict[str, List[Dict[str, Any]]],
    intervals: List[Dict[str, Any]],
    output_dir: str,
) -> List[PlotJob]:
    """Jobs for frequency-distribution histogram panels (overlaid per mode).

    Each histogram series needs the cumulative buckets at the end of a mode's
    window: an instant query at ``end`` with a range-query fallback. Both specs
    are attached; the transform picks the instant result when present.
    """
    jobs: List[PlotJob] = []
    for title, panels in dist_by_title.items():
        section = panels[0].get("section", "general")
        section_dir = Path(output_dir) / section
        safe_title = sanitize_filename(title)
        multi = len(panels) > 1

        entries: List[Dict[str, Any]] = []
        specs: List[QuerySpec] = []
        for panel in panels:
            for target in panel.get("targets", []):
                expr = target.get("expr")
                if not expr:
                    continue
                mode = extract_payment_mode_from_expr(expr)
                use = [iv for iv in intervals if iv.get("mode") == mode] or intervals
                for iv in use:
                    ts = iv.get("prometheus_timestamps", {}) or {}
                    start_ms, finish_ms = ts.get("start_ms"), ts.get("finish_ms")
                    if not start_ms or not finish_ms:
                        continue
                    start, end = start_ms / 1000, finish_ms / 1000
                    inst = QuerySpec(expr, start, end, kind="instant", instant_time=end)
                    rng = QuerySpec(expr, start, end, step="60s")
                    specs += [inst, rng]
                    entries.append(
                        {
                            "mode": mode if multi else iv.get("mode", mode),
                            "instant": inst,
                            "range": rng,
                        }
                    )

        if not entries:
            continue
        out = (
            section_dir / f"{safe_title}.png"
            if multi
            else section_dir / f"{safe_title}_{sanitize_filename(title)}.png"
        )
        jobs.append(
            PlotJob(
                kind="distribution",
                title=title,
                output_path=str(out),
                section=section,
                specs=specs,
                params={"entries": entries},
            )
        )
    return jobs
