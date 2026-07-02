# bench-plotter

Post-benchmark analysis tool for nanomoni. Queries Prometheus for metric data over the time windows recorded by a benchmark run, then generates matplotlib plots organized by payment mode (signature, payword, paytree).

## Role in nanomoni

`bench-plotter` lives inside the nanomoni repo and reads `benchmark_timing.json` from the nanomoni root (auto-detected). Run it after `run_benchmark.sh` finishes to produce plots of the results.

## Installation

Requires Python >=3.10. Uses its own venv separate from nanomoni (different Python version constraint).

```bash
cd bench-plotter
poetry install
```

## Usage

From the nanomoni root:

```bash
bench-plotter/.venv/bin/python bench-plotter/src/bench_plotter/generate_plots.py
```

Or from inside `bench-plotter/`:

```bash
.venv/bin/python src/bench_plotter/generate_plots.py
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `intervals` | auto-detect | Path to timing JSON (finds `benchmark_timing.json` or `*interval*.json` in nanomoni root) |
| `--output` | `plots/` | Output directory for PNGs |
| `--interpol` | `100` | Interpolation points for time-series normalization |

## Configuration

Copy `.env.example` to `.env` and set `PROMETHEUS_URL` to the Prometheus instance used during the benchmark:

```
PROMETHEUS_URL=http://127.0.0.1:9090
```

`settings.py` walks up parent directories, so a `.env` at the nanomoni root is also picked up automatically.

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
│   ├── generate_plots.py          # CLI entry point
│   ├── generate_plots/            # Per-mode plot orchestration
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
│   └── settings.py                # Reads PROMETHEUS_URL from .env
├── benchmark_timing.json          # Latest timing snapshot (committed)
├── .env.example
├── pyproject.toml
└── tests/
```

## Dependencies

`pandas`, `numpy`, `matplotlib`, `httpx`, `python-dotenv`
