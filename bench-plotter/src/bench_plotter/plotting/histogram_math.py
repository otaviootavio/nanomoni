"""Histogram bucket reconstruction and query detection (pure data transforms)."""

from __future__ import annotations

from typing import List

import numpy as np


def histogram_to_samples(
    edges: List[float],
    cumulative: List[float],
    max_total: int = 5000,
) -> List[float]:
    """Reconstruct approximate samples from a cumulative histogram.

    ``edges`` are ascending ``le`` upper bounds and ``cumulative`` the aligned
    cumulative counts (or fractions). Per-bucket weights are differenced, then
    each bucket contributes samples spread uniformly across its ``(lower, upper]``
    span, in proportion to its weight, capped at ``max_total`` total.

    The result approximates the *shape* of the distribution (for a violin/KDE); it
    is NOT the original per-observation data, so any density drawn from it is an
    interpolation of the bucket counts, not measured samples.
    """
    if not edges or len(edges) != len(cumulative):
        return []
    lowers: List[float] = []
    weights: List[float] = []
    prev_edge = 0.0
    prev_cum = 0.0
    for edge, cum in zip(edges, cumulative):
        weights.append(max(0.0, float(cum) - prev_cum))
        lowers.append(prev_edge)
        prev_edge = float(edge)
        prev_cum = float(cum)
    total = sum(weights)
    if total <= 0:
        return []
    samples: List[float] = []
    for lower, upper, weight in zip(lowers, edges, weights):
        n = int(round(max_total * weight / total))
        if n <= 0:
            continue
        if n == 1 or upper <= lower:
            samples.append((lower + float(upper)) / 2.0)
            continue
        # Evenly spread inside the bucket, avoiding the exact edges.
        samples.extend(np.linspace(lower, float(upper), n + 2)[1:-1].tolist())
    return samples
