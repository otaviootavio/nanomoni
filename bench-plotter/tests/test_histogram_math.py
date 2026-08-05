"""Tests for the cumulative-histogram statistics helpers."""

from __future__ import annotations

import pytest

from bench_plotter.plotting.histogram_math import (
    histogram_moments,
    histogram_quantile,
    histogram_to_samples,
)


class TestHistogramMoments:
    def test_single_bucket_mean_is_its_midpoint_with_zero_spread(self) -> None:
        # Everything in (0, 10] -> midpoint 5, and one bucket has no spread.
        mean, stddev = histogram_moments([10.0], [1.0])
        assert mean == pytest.approx(5.0)
        assert stddev == pytest.approx(0.0)

    def test_two_equal_buckets(self) -> None:
        # Half in (0, 10] (midpoint 5), half in (10, 20] (midpoint 15).
        mean, stddev = histogram_moments([10.0, 20.0], [0.5, 1.0])
        assert mean == pytest.approx(10.0)
        assert stddev == pytest.approx(5.0)

    def test_weights_shift_the_mean_toward_the_heavier_bucket(self) -> None:
        mean, _ = histogram_moments([10.0, 20.0], [0.9, 1.0])
        assert mean == pytest.approx(0.9 * 5.0 + 0.1 * 15.0)

    def test_counts_need_not_be_normalized(self) -> None:
        # Raw cumulative counts must give the same answer as fractions.
        assert histogram_moments([10.0, 20.0], [50.0, 100.0]) == histogram_moments(
            [10.0, 20.0], [0.5, 1.0]
        )

    def test_misaligned_or_empty_input_returns_none(self) -> None:
        assert histogram_moments([], []) == (None, None)
        assert histogram_moments([10.0], [0.5, 1.0]) == (None, None)
        assert histogram_moments([10.0], [0.0]) == (None, None)


class TestHistogramQuantile:
    def test_interpolates_inside_the_containing_bucket(self) -> None:
        # p50 of a uniform (0, 10] bucket sits at 5.
        assert histogram_quantile([10.0], [1.0], 0.50) == pytest.approx(5.0)

    def test_median_lands_on_the_boundary_of_two_equal_buckets(self) -> None:
        assert histogram_quantile([10.0, 20.0], [0.5, 1.0], 0.50) == pytest.approx(10.0)

    def test_p95_falls_in_the_upper_bucket(self) -> None:
        # 90% below 10, so p95 is halfway through the (10, 20] bucket.
        assert histogram_quantile([10.0, 20.0], [0.9, 1.0], 0.95) == pytest.approx(15.0)

    def test_unnormalized_cumulative_counts(self) -> None:
        assert histogram_quantile([10.0, 20.0], [90.0, 100.0], 0.95) == pytest.approx(
            15.0
        )

    def test_no_weight_returns_none(self) -> None:
        assert histogram_quantile([10.0], [0.0], 0.5) is None
        assert histogram_quantile([], [], 0.5) is None


class TestHistogramToSamples:
    def test_reconstructed_samples_span_the_buckets(self) -> None:
        samples = histogram_to_samples([10.0, 20.0], [0.5, 1.0], max_total=100)
        assert samples
        assert min(samples) > 0.0
        assert max(samples) <= 20.0

    def test_misaligned_input_returns_empty(self) -> None:
        assert histogram_to_samples([10.0], [0.5, 1.0]) == []
