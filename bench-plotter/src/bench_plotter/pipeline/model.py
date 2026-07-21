"""In-memory plan model for the plotting pipeline.

These dataclasses are the contract that flows through the four stages
(plan -> fetch -> transform -> draw). Everything here is a plain, **picklable**
value type: no closures, no matplotlib figures, no open connections. That is a
hard requirement -- ``DrawTask`` instances cross a process boundary into the
draw pool (see ``pipeline.draw``), so anything they reference must survive
``pickle``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class QuerySpec:
    """A single Prometheus range query over one time window.

    Frozen and hashable so it can be a dict key: the fetch stage dedups by the
    spec itself, so two jobs asking for the same ``(expr, window, step)``
    trigger exactly one round-trip.
    """

    expr: str
    start_unix: float
    end_unix: float
    step: Optional[str] = None


@dataclass
class PlotJob:
    """One logical output group: everything needed to turn queries into plot(s).

    A job may produce more than one ``DrawTask`` (e.g. a ``steady_state`` job
    emits box/ECDF/violin; the latency suite emits three figures), so the plan
    is a list of jobs and the transform stage expands each into one-or-more
    draw tasks.

    ``kind`` selects the transform+draw recipe:
        ``overlay``       - windowed multi-series line (resource + TPS panels)
        ``mean_std``      - mean +/- std across same-mode repeat runs
        ``steady_state``  - resource box/ECDF/violin companions
        ``latency_box``   - steady-state latency box plot (precomputed quantiles)
        ``latency_dist``  - steady-state latency ECDF + reconstructed violin

    ``specs`` are the queries this job needs; ``params`` carries per-kind extras
    (section, safe filename stems, legend, mode labels, num_points, window, ...).
    """

    kind: str
    title: str
    output_path: str
    section: str
    specs: List[QuerySpec] = field(default_factory=list)
    y_axis_label: str = "Value"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DrawTask:
    """A rendering unit executed in a draw-pool worker.

    ``fn_name`` indexes ``draw_worker.DRAW_REGISTRY`` rather than holding a
    function object, so the task pickles cleanly regardless of how the target
    draw function is defined. ``kwargs`` is plain data only. The worker creates
    and saves the figure entirely inside its own process.
    """

    fn_name: str
    output_path: str
    kwargs: Dict[str, Any] = field(default_factory=dict)


# A resolved fetch result cache: spec -> Prometheus JSON payload (or None on
# failure). Kept as a plain type alias so the stage signatures read clearly.
ResultCache = Dict[QuerySpec, Optional[Dict[str, Any]]]

# A fetch failure record, mirroring the shape the old code reported so the
# end-of-run summary is unchanged.
FetchFailure = Dict[str, Any]

FetchOutcome = Tuple[ResultCache, List[FetchFailure]]
