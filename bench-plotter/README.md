# bench-plotter

Post-benchmark analysis tool for nanomoni. Queries Prometheus for metric data over the time windows recorded by a benchmark run, then generates matplotlib plots organized by payment mode (signature, payword, paytree).

## Role in nanomoni

`bench-plotter` lives inside the nanomoni repo and reads `benchmark_timing.json` from the nanomoni root (auto-detected). Run it after `run_benchmark.sh` finishes to produce plots of the results.

## Installation

Requires Python >=3.9. Uses its own venv separate from nanomoni.

```bash
cd bench-plotter
poetry install
```

## Usage

`generate_plots` is a package; run it as a module (`bench_plotter.generate_plots`)
so its `__main__` entry point is used.

From the nanomoni root:

```bash
PYTHONPATH=bench-plotter/src bench-plotter/.venv/bin/python -m bench_plotter.generate_plots
```

Or from inside `bench-plotter/`:

```bash
PYTHONPATH=src .venv/bin/python -m bench_plotter.generate_plots
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `intervals` | auto-detect | Path to timing JSON (finds `benchmark_timing.json` or `*interval*.json` in nanomoni root) |
| `--output` | `plots/` | Output directory for PNGs |
| `--interpol` | `100` | Interpolation points for time-series normalization |

## Configuration

The Prometheus URL is hardcoded to `http://127.0.0.1:9090` in `settings.py` — the
benchmark always runs against a local Prometheus on the default port. To target a
different instance, edit `prometheus_base_url()` in `src/bench_plotter/settings.py`.

## Plotting modes

The tool chooses the plot type based on the intervals in the timing file:

| Intervals | Mode | Output |
|-----------|------|--------|
| 1 interval | Windowed averaging (window = 2× sampling interval) | One PNG per metric |
| N intervals, same mode | Mean ± std band across runs | One PNG per metric |
| N intervals, mixed modes | Individual windowed plot per mode | `metric_signature.png`, `metric_paytree.png`, `metric_payword.png` |

## Output structure

```
plots/
├── client_resources/
├── issuer_resources/
├── vendor_resources/
├── tps_metrics/
└── logs/
```

Each subfolder mirrors a Grafana dashboard section. PNGs are 300 DPI.

## Project structure

```
bench-plotter/
├── src/bench_plotter/
│   ├── generate_plots/            # CLI entry point + per-mode plot orchestration
│   │   ├── __main__.py            # `python -m bench_plotter.generate_plots`
│   │   ├── signature.py
│   │   ├── payword.py
│   │   └── paytree.py
│   ├── plotting/                  # Matplotlib rendering
│   │   ├── time_series.py
│   │   ├── histograms.py
│   │   ├── dashboard_processor.py
│   │   └── query_utils.py
│   ├── dashboard_queries/         # Prometheus query definitions per mode
│   │   ├── signature.py
│   │   ├── payword.py
│   │   └── paytree.py
│   ├── prometheus_fetch.py        # Prometheus HTTP API client
│   └── settings.py                # Hardcoded Prometheus URL
├── benchmark_timing.json          # Latest timing snapshot (committed)
├── pyproject.toml
└── tests/
```

## Dependencies

`pandas`, `numpy`, `matplotlib`, `httpx`
