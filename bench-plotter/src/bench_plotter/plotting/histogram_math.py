"""Histogram bucket reconstruction and query detection (pure data transforms)."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


def _bucket_weights(
    edges: List[float], cumulative: List[float]
) -> Tuple[List[float], List[float]]:
    """Difference a cumulative histogram into per-bucket (lower edge, weight).

    The first bucket's lower edge is 0: these histograms measure durations and
    byte counts, so nothing falls below zero.
    """
    lowers: List[float] = []
    weights: List[float] = []
    prev_edge = 0.0
    prev_cum = 0.0
    for edge, cum in zip(edges, cumulative):
        weights.append(max(0.0, float(cum) - prev_cum))
        lowers.append(prev_edge)
        prev_edge = float(edge)
        prev_cum = float(cum)
    return lowers, weights


def histogram_moments(
    edges: List[float], cumulative: List[float]
) -> Tuple[Optional[float], Optional[float]]:
    """Return ``(mean, population stddev)`` of a cumulative histogram.

    Each bucket contributes its midpoint, weighted by its share of the total, so
    both moments are bucket-resolution estimates rather than measured values: the
    spread *within* a bucket is invisible, which biases the stddev low. Callers
    exclude Prometheus' ``+Inf`` bucket (it has no upper bound to take a midpoint
    of), so observations past the largest finite edge are not represented either.

    Returns ``(None, None)`` when the inputs are misaligned or carry no weight.
    """
    if not edges or len(edges) != len(cumulative):
        return None, None
    lowers, weights = _bucket_weights(edges, cumulative)
    total = sum(weights)
    if total <= 0:
        return None, None
    midpoints = np.array(
        [(lower + float(upper)) / 2.0 for lower, upper in zip(lowers, edges)]
    )
    shares = np.array(weights) / total
    mean = float(np.sum(shares * midpoints))
    variance = float(np.sum(shares * (midpoints - mean) ** 2))
    return mean, float(np.sqrt(max(0.0, variance)))


def histogram_quantile(
    edges: List[float], cumulative: List[float], quantile: float
) -> Optional[float]:
    """Interpolate a quantile from a cumulative histogram.

    Locates the bucket the quantile falls in and interpolates linearly across it,
    the same approximation Prometheus' ``histogram_quantile`` makes. ``cumulative``
    is normalized by its last (largest) entry, so it may be either counts or
    fractions, and need not reach 1 when the ``+Inf`` bucket was excluded.
    """
    if not edges or len(edges) != len(cumulative):
        return None
    total = float(cumulative[-1])
    if total <= 0:
        return None
    target = quantile * total
    prev_edge = 0.0
    prev_cum = 0.0
    for edge, cum in zip(edges, cumulative):
        current = float(cum)
        if current >= target:
            if current <= prev_cum:
                return float(edge)
            fraction = (target - prev_cum) / (current - prev_cum)
            return prev_edge + fraction * (float(edge) - prev_edge)
        prev_edge, prev_cum = float(edge), current
    return float(edges[-1])


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
    lowers, weights = _bucket_weights(edges, cumulative)
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
