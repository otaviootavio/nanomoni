"""Statistical reduction of repeated benchmark runs sharing a (mode, tps,
total_requests).

``run_benchmark.sh`` can run each (mode, tps) point ``REPEATS`` times to
distinguish a real trend from single-run noise (GC pauses, scheduler jitter,
which side of a Pyroscope bucket boundary a window happened to land on).
Every per-run aggregate stage (``profiling/aggregate.py``, ``sweep/
aggregate.py``) still produces one row per run; :func:`reduce_repeats`
collapses those rows into one row per group, replacing each numeric field
with its mean across repeats and adding ``<field>_low`` / ``<field>_high``
(mean -/+ sample std dev). Callers can then feed the result straight into
``mode_style.series_by_mode``, which draws those bounds as error bars when
present, without needing to know whether repeats even happened -- a group of
one becomes a zero-width band around that single value.

``total_requests`` is part of the default group key alongside ``mode`` and
``tps``, not just ``(mode, tps)``: a duration sweep (same target TPS, several
``RUN_DURATION_SEC`` values) produces runs that share ``(mode, tps)`` but
carry different ``total_requests`` (= tps * duration), since payment count is
what actually drives amortization effects, not the rate traffic arrived at.
Grouping on ``(mode, tps)`` alone would treat those as repeats of the same
point and average them together, hiding exactly the amortization trend such
a sweep exists to measure -- with no error, just a silently blended
``total_requests`` and per-payment numbers. Genuine repeats always share all
three fields, so this widening changes nothing for a TPS-only sweep.

For raw Prometheus timeseries (per-config resource overlays),
:func:`reduce_repeat_timeseries` does the analogous collapse: align repeats
of the same mode onto a shared elapsed-time grid, then replace each point
with its mean +/- sample std across repeats. It is always called already
scoped to one ``(tps, total_requests)`` config (see
``sweep/runner.py:group_runs_by_config``), so a mode-only group key is safe
there and does not need widening.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_GROUP_KEYS: Tuple[str, str, str] = ("mode", "tps", "total_requests")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def reduce_repeats(
    rows: List[Dict[str, Any]],
    group_keys: Tuple[str, ...] = _GROUP_KEYS,
) -> List[Dict[str, Any]]:
    """Collapse rows sharing the same ``group_keys`` into one row per group.

    Every numeric field present on at least one row of a group is replaced by
    its mean across the group; ``<field>_low``, ``<field>_high`` (that mean
    -/+ the sample std dev) and ``<field>_n`` (how many repeats contributed)
    are added alongside it. A group's non-numeric fields (e.g. a flamebearer
    ``payload``) come from whichever of its rows happened to be first --
    those are inherently per-run and are not meant to be read off the
    reduced row.

    Rows missing any ``group_keys`` value are dropped (nothing to group
    them by). Row order in the input controls the output order: a group's
    position is set by its first row's position.
    """
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    order: List[Tuple[Any, ...]] = []
    for row in rows:
        key = tuple(row.get(k) for k in group_keys)
        if any(v is None for v in key):
            continue
        if key not in groups:
            order.append(key)
        groups.setdefault(key, []).append(row)

    reduced: List[Dict[str, Any]] = []
    for key in order:
        group = groups[key]
        base = dict(group[0])
        numeric_fields = {
            field
            for row in group
            for field, value in row.items()
            if field not in group_keys and _is_number(value)
        }
        for field in numeric_fields:
            values = [float(row[field]) for row in group if _is_number(row.get(field))]
            if not values:
                continue
            arr = np.asarray(values)
            mean = float(arr.mean())
            std = float(arr.std(ddof=1)) if len(values) > 1 else 0.0
            base[field] = mean
            base[f"{field}_low"] = mean - std
            base[f"{field}_high"] = mean + std
            base[f"{field}_n"] = len(values)
        reduced.append(base)
    return reduced


def _elapsed_pairs(
    timestamps: List[Any], values: List[Any]
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Return (elapsed_s, values) arrays, dropping None samples. ``None`` if empty."""
    if not timestamps or not values or len(timestamps) != len(values):
        return None
    start = float(timestamps[0])
    elapsed: List[float] = []
    nums: List[float] = []
    for ts, v in zip(timestamps, values):
        if v is None:
            continue
        elapsed.append(float(ts) - start)
        nums.append(float(v))
    if not elapsed:
        return None
    return np.asarray(elapsed), np.asarray(nums)


def _merge_timeseries_group(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Align one mode's repeats onto a shared elapsed grid; mean +/- sample std."""
    first = group[0]
    if len(group) == 1:
        return dict(first)

    prepared: List[Tuple[np.ndarray, np.ndarray]] = []
    for run in group:
        pairs = _elapsed_pairs(run.get("timestamps", []), run.get("values", []))
        if pairs is not None:
            prepared.append(pairs)
    if not prepared:
        return dict(first)
    if len(prepared) == 1:
        elapsed, vals = prepared[0]
        start = float(first.get("timestamps", [0.0])[0])
        return {
            "interval_mode": first.get("interval_mode"),
            "timestamps": [start + float(t) for t in elapsed],
            "values": [float(v) for v in vals],
        }

    # Clip to the shortest repeat so we never extrapolate past a run that ended early.
    min_duration = min(float(elapsed[-1]) for elapsed, _ in prepared)
    grid_src = prepared[0][0]
    grid = grid_src[grid_src <= min_duration + 1e-9]
    if grid.size == 0:
        return dict(first)

    stacked = np.vstack([np.interp(grid, elapsed, vals) for elapsed, vals in prepared])
    mean = stacked.mean(axis=0)
    std = stacked.std(axis=0, ddof=1)
    start = float(first.get("timestamps", [0.0])[0])
    return {
        "interval_mode": first.get("interval_mode"),
        "timestamps": [start + float(t) for t in grid],
        "values": [float(v) for v in mean],
        "values_low": [float(m - s) for m, s in zip(mean, std)],
        "values_high": [float(m + s) for m, s in zip(mean, std)],
    }


def reduce_repeat_timeseries(
    runs: List[Dict[str, Any]],
    label_key: str = "interval_mode",
) -> List[Dict[str, Any]]:
    """Collapse timeseries runs sharing the same mode into one series per mode.

    Each run is expected to carry ``timestamps``, ``values``, and ``label_key``
    (default ``interval_mode``). Groups of size one pass through unchanged;
    larger groups are resampled onto a shared elapsed-time grid (clipped to
    the shortest repeat) and replaced by pointwise mean with
    ``values_low`` / ``values_high`` (mean -/+ sample std, ddof=1).

    Runs missing ``label_key`` are dropped. Output order follows first-seen
    mode order in ``runs``.
    """
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for run in runs:
        mode = run.get(label_key)
        if mode is None:
            continue
        if mode not in groups:
            order.append(mode)
        groups.setdefault(mode, []).append(run)

    return [_merge_timeseries_group(groups[mode]) for mode in order]
