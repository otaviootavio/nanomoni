"""Transform stage for frequency-distribution histogram jobs.

Builds the overlaid-histogram draw task from cached bucket queries. Prefers the
instant query's result and falls back to the last value of each range series.
Plan-side job construction lives in :mod:`.distribution`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from bench_plotter.plotting.histogram_math import cumulative_to_per_bucket

from .model import DrawTask, PlotJob, ResultCache


def _le_sort_key(kv: Tuple[str, float]) -> float:
    try:
        return float(kv[0])
    except (ValueError, TypeError):
        return float("inf")


def transform_distribution(job: PlotJob, cache: ResultCache) -> List[DrawTask]:
    """Build one overlaid-histogram draw task from cached bucket queries.

    Prefers the instant query's result; falls back to the last value of each
    range series when the instant query returned nothing.
    """
    histogram_data: Dict[str, Any] = {}
    for entry in job.params["entries"]:
        vector = []
        inst = cache.get(entry["instant"])
        if inst:
            vector = inst.get("data", {}).get("result", [])
        if not vector:
            rng = cache.get(entry["range"])
            if rng:
                for item in rng.get("data", {}).get("result", []):
                    vals = item.get("values", [])
                    if vals and len(vals[-1]) >= 2 and vals[-1][1] != "NaN":
                        vector.append(
                            {"metric": item.get("metric", {}), "value": vals[-1]}
                        )

        bucket_data: Dict[str, float] = {}
        for item in vector:
            le = (item.get("metric") or {}).get("le", "unknown")
            value = item.get("value", [])
            if value and len(value) >= 2 and value[1] != "NaN":
                bucket_data[le] = float(value[1])
        if not bucket_data:
            continue

        ordered = sorted(bucket_data.items(), key=_le_sort_key)
        labels, values = cumulative_to_per_bucket(
            [k for k, _ in ordered], [v for _, v in ordered]
        )
        histogram_data[entry["mode"]] = (labels, values)

    if not histogram_data:
        return []
    return [
        DrawTask(
            fn_name="overlaid_histogram",
            output_path=job.output_path,
            kwargs={"histogram_data": histogram_data, "title": job.title},
        )
    ]
