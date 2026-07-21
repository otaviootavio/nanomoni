"""Plotting primitives: windowing math, figure builders, histogram helpers.

Orchestration lives in :mod:`bench_plotter.pipeline`; this package only exposes
the reusable drawing/transform primitives it (and the draw workers) build on.

Import from the submodules directly:

- :mod:`bench_plotter.plotting.windowing` — sampling / windowing / steady-state math
- :mod:`bench_plotter.plotting.histogram_math` — bucket reconstruction helpers
- :mod:`bench_plotter.plotting.timeseries_renderers` — windowed / mean-std figures
- :mod:`bench_plotter.plotting.distribution_renderers` — box / ECDF / violin figures
- :mod:`bench_plotter.plotting.common` — shared palette / save helpers
"""
