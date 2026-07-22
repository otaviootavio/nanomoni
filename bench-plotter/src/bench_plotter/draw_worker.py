"""Draw-pool worker: renders a single :class:`DrawTask` to a PNG.

This module is the process boundary for the draw stage. It pins the
non-interactive ``Agg`` backend **before** any ``matplotlib.pyplot`` import so
that fork-based workers never touch an interactive backend (the dev machine
defaults to ``tkagg``, which is not safe to drive from multiple forked
processes). Importing this module is therefore the one place allowed to decide
the backend; the rest of the package must import plotting code only after this
pin is in effect.

``run_draw_task`` is a module-level function so a ``ProcessPoolExecutor`` can
call it by reference; it dispatches through ``DRAW_REGISTRY`` (name -> draw fn)
so :class:`DrawTask` never has to pickle a function object.
"""

from __future__ import annotations

import matplotlib

# Must precede any pyplot import (including the transitive one via plotting.*).
matplotlib.use("Agg")

import os
from typing import Any, Callable, Dict, Optional

from bench_plotter.plotting.timeseries_renderers import (
    create_windowed_plot_multi,
    create_mean_std_plot,
)
from bench_plotter.plotting.distribution_renderers import (
    create_steady_state_boxplot,
    create_ecdf_plot,
    create_violin_plot,
    create_precomputed_boxplot,
    create_bucket_ecdf,
)

# Stable string names -> existing draw functions. The names are the contract
# stored in ``DrawTask.fn_name``; the plan/transform stages emit these and the
# worker resolves them here. Reusing the functions verbatim keeps rendering
# behaviour identical to the pre-refactor code.
DRAW_REGISTRY: Dict[str, Callable[..., None]] = {
    "windowed_multi": create_windowed_plot_multi,
    "steady_state_box": create_steady_state_boxplot,
    "ecdf": create_ecdf_plot,
    "violin": create_violin_plot,
    "mean_std": create_mean_std_plot,
    "precomputed_box": create_precomputed_boxplot,
    "bucket_ecdf": create_bucket_ecdf,
}


def run_draw_task(
    fn_name: str, output_path: str, kwargs: Dict[str, Any]
) -> Optional[str]:
    """Render one draw task; return the path if a file was written, else ``None``.

    Runs inside a draw-pool worker. Resolves ``fn_name`` in ``DRAW_REGISTRY``
    and calls it with ``kwargs`` plus the injected ``output_path``. Some draw
    functions legitimately no-op (e.g. steady-state plots when a plateau is too
    short to yield samples); those write nothing, so ``None`` is returned and the
    task is not counted as a written plot. Any exception propagates to the pool
    so the orchestrator can report a failed figure rather than silently dropping it.
    """
    fn = DRAW_REGISTRY.get(fn_name)
    if fn is None:
        raise KeyError(f"Unknown draw function '{fn_name}'")
    # The written-or-None contract below is decided purely by whether the file
    # exists after fn runs, and some renderers deliberately write nothing (a
    # valid no-op). Delete any existing file first so an earlier render left at
    # this path is never reported as freshly written.
    if os.path.exists(output_path):
        os.remove(output_path)
    fn(output_path=output_path, **kwargs)
    return output_path if os.path.exists(output_path) else None
