"""Tests for spreading virtual clients across the vendor's per-worker ports."""

from __future__ import annotations

from collections import Counter

from nanomoni.client.common import vendor_url_for_worker


BASE = "http://vendor:8000/api/v1"


def test_index_selects_a_consecutive_port() -> None:
    assert vendor_url_for_worker(BASE, 0, 10) == "http://vendor:8000/api/v1"
    assert vendor_url_for_worker(BASE, 3, 10) == "http://vendor:8003/api/v1"
    assert vendor_url_for_worker(BASE, 9, 10) == "http://vendor:8009/api/v1"


def test_indexes_wrap_around_the_worker_count() -> None:
    assert vendor_url_for_worker(BASE, 10, 10) == vendor_url_for_worker(BASE, 0, 10)
    assert vendor_url_for_worker(BASE, 23, 10) == "http://vendor:8003/api/v1"


def test_a_multiple_of_the_worker_count_spreads_evenly() -> None:
    """The whole point: every worker ends up with the same number of clients."""
    counts = Counter(vendor_url_for_worker(BASE, i, 10) for i in range(40))
    assert len(counts) == 10
    assert set(counts.values()) == {4}


def test_single_port_leaves_the_url_untouched() -> None:
    assert vendor_url_for_worker(BASE, 7, 1) == BASE


def test_url_without_an_explicit_port_is_left_untouched() -> None:
    assert (
        vendor_url_for_worker("http://vendor/api/v1", 7, 10) == "http://vendor/api/v1"
    )


def test_credentials_survive_the_port_change() -> None:
    url = vendor_url_for_worker("http://user:pw@vendor:8000/api/v1", 2, 10)
    assert url == "http://user:pw@vendor:8002/api/v1"


def test_ipv6_host_keeps_its_brackets() -> None:
    """urlsplit strips IPv6 brackets from .hostname; the netloc needs them back."""
    url = vendor_url_for_worker("http://[::1]:8000/api/v1", 3, 10)
    assert url == "http://[::1]:8003/api/v1"
