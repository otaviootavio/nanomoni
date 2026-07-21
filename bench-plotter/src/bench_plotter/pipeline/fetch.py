"""Stage 2: resolve every query the plan needs, concurrently and once each.

All jobs declare their queries up front as :class:`QuerySpec`s, so the whole
plan's queries can be gathered, de-duplicated, and issued together on a single
event loop with a bounded number of in-flight requests. De-duplication matters
because the grouped-TPS and latency paths otherwise re-issue identical
``(expr, window)`` queries; here an identical spec is fetched exactly once.

Returns a ``(cache, failures)`` pair. The cache maps each spec to its Prometheus
payload (or ``None`` on error); failures mirror the record shape the old code
reported so the end-of-run summary is unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, List

from bench_plotter.prometheus_fetch import query_range

from .model import FetchFailure, FetchOutcome, PlotJob, QuerySpec, ResultCache

# Cap concurrent Prometheus round-trips. Fetch is I/O-bound and the local
# Prometheus handles this comfortably; the bound just avoids opening dozens of
# sockets at once for large multi-mode plans.
_MAX_CONCURRENCY = 8


def _unique_specs(jobs: Iterable[PlotJob]) -> List[QuerySpec]:
    """Distinct specs across all jobs, order-stable for deterministic logging."""
    seen: dict[QuerySpec, None] = {}
    for job in jobs:
        for spec in job.specs:
            seen.setdefault(spec, None)
    return list(seen)


async def _fetch_one(spec: QuerySpec, sem: asyncio.Semaphore) -> Dict[str, Any]:
    async with sem:
        return await query_range(
            query=spec.expr,
            start_unix=spec.start_unix,
            end_unix=spec.end_unix,
            step=spec.step,
        )


async def _fetch_all_async(specs: List[QuerySpec]) -> FetchOutcome:
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    results = await asyncio.gather(
        *(_fetch_one(spec, sem) for spec in specs),
        return_exceptions=True,
    )
    cache: ResultCache = {}
    failures: List[FetchFailure] = []
    for spec, result in zip(specs, results):
        if isinstance(result, BaseException):
            cache[spec] = None
            failures.append(
                {
                    "panel": spec.expr[:60],
                    "legend": spec.step or "auto",
                    "query": spec.expr,
                    "interval": f"{spec.start_unix}-{spec.end_unix}",
                    "error": str(result),
                }
            )
        else:
            cache[spec] = result
    return cache, failures


def fetch_all(jobs: Iterable[PlotJob]) -> FetchOutcome:
    """Fetch every unique query the plan needs on one concurrent event loop."""
    specs = _unique_specs(jobs)
    if not specs:
        return {}, []
    return asyncio.run(_fetch_all_async(specs))
