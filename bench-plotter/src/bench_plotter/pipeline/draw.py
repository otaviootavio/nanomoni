"""Stage 4: render draw tasks, in parallel across processes.

Drawing is the dominant cost (300-DPI rasterization, ~72% of a run), and it is
the only stage worth parallelizing. matplotlib's pyplot state is not
thread-safe, so parallelism is by **process**, using a ``fork`` context so each
worker inherits the parent's already-imported matplotlib at ~zero cost (a
``spawn`` context would re-pay the multi-second import per worker and erase the
win). Workers receive only plain data via :class:`DrawTask` and build+save the
figure entirely in their own process.

Worker exceptions are surfaced, not swallowed: a failed task becomes a reported
failure (and, if every task fails, a raised error) rather than a silently
missing PNG.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import List, Optional, Tuple

from bench_plotter.draw_worker import run_draw_task

from .model import DrawTask


def _run(task: DrawTask, show_title: bool) -> Optional[str]:
    """Render a task; returns the written path, or None if it no-op'd."""
    kwargs = {**task.kwargs, "show_title": show_title}
    return run_draw_task(task.fn_name, task.output_path, kwargs)


def draw_all(
    tasks: List[DrawTask],
    workers: int | None = None,
    parallel: bool = True,
    show_title: bool = True,
) -> Tuple[List[str], List[dict]]:
    """Render all tasks. Returns (written_paths, failures).

    ``parallel=False`` runs the tasks serially in-process (useful for debugging
    a rendering issue without the pool obscuring the traceback). Otherwise a
    fork-based process pool is used, sized to ``min(workers or cpu_count, n)``.
    ``show_title`` is forwarded to every draw function as a ``show_title``
    kwarg, overriding whatever the task's own ``kwargs`` carried -- the one
    place that decides whether rendered figures get a title at all.
    """
    if not tasks:
        return [], []

    if not parallel:
        written, failures = [], []
        for task in tasks:
            try:
                result = _run(task, show_title)
                if result:
                    written.append(result)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append({"output_path": task.output_path, "error": str(exc)})
        _report(failures, len(tasks))
        return written, failures

    max_workers = min(workers or os.cpu_count() or 1, len(tasks))
    written, failures = [], []
    with ProcessPoolExecutor(
        max_workers=max_workers, mp_context=get_context("fork")
    ) as pool:
        futures = {pool.submit(_run, task, show_title): task for task in tasks}
        for future, task in futures.items():
            try:
                result = future.result()
                if result:
                    written.append(result)
            except Exception as exc:  # noqa: BLE001 - collected below, re-raised if total
                failures.append({"output_path": task.output_path, "error": str(exc)})

    _report(failures, len(tasks))
    return written, failures


def _report(failures: List[dict], total: int) -> None:
    if failures and len(failures) == total:
        raise RuntimeError(
            f"All {total} draw tasks failed; first error: {failures[0]['error']}"
        )
    for failure in failures:
        print(f"Draw failed for {failure['output_path']}: {failure['error']}")
