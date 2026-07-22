"""Time-series statistics (pure data transforms)."""

from __future__ import annotations

from typing import Any, List, Dict

import pandas as pd


def steady_state_samples(values: List[Any]) -> List[float]:
    """Return only the stabilized (plateau) samples of a series.

    The warm-up ramp and the cool-down drain are dropped by keeping the samples
    within +/-20% of the series median. This works when the plateau dominates the
    window (as for the vendor under sustained load): the median lands on the
    plateau, and the ramp/drain samples fall outside the band. Returns ``[]`` when
    there is too little data.
    """
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 4:
        return []
    ordered = sorted(vals)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return []
    return [v for v in vals if abs(v - median) <= 0.2 * median]


def steady_state_long_frame(
    series_list: List[Dict[str, Any]],
    trim: bool = True,
) -> tuple[pd.DataFrame, List[str]]:
    """Build a long-form (``mode``, ``value``) frame of samples per mode.

    Shared by the ECDF and violin plots. Returns the frame plus the mode order
    (first-seen). With ``trim`` (the default) warm-up/cool-down are dropped via
    ``steady_state_samples``, exactly like the box plot. Pass ``trim=False`` when
    the values are already a distribution (e.g. reconstructed from a histogram),
    where the tails must be kept rather than clipped to +/-20% of the median.
    """
    rows: List[Dict[str, Any]] = []
    order: List[str] = []
    for idx, series in enumerate(series_list):
        if trim:
            samples = steady_state_samples(series.get("values", []))
        else:
            samples = [float(v) for v in series.get("values", []) if v is not None]
        if len(samples) < 3:
            continue
        label = (
            series.get("interval_mode") or series.get("label") or f"Series {idx + 1}"
        )
        order.append(label)
        rows.extend({"mode": label, "value": v} for v in samples)
    return pd.DataFrame(rows), order
