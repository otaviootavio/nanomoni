# bench-plotter

Post-benchmark analysis tool for nanomoni. Queries Prometheus for metric data over the time windows recorded by a benchmark run, then generates matplotlib plots organized by payment mode (signature, payword, paytree).

## Role in nanomoni

`bench-plotter` lives inside the nanomoni repo and plots the results of a benchmark run. `run_benchmark.sh` writes `benchmark_timing.json` (per-mode start/finish timestamps and status) to the nanomoni root; the plotter reads that file, queries Prometheus for each window, and renders the charts.

## Installation

Requires Python >=3.9. `bench_plotter` is a second package inside the nanomoni Poetry project (registered under `packages` in the root `pyproject.toml`), so it installs together with nanomoni — there is no separate venv:

```bash
poetry install
```

## Usage

After a run has produced `benchmark_timing.json` in the nanomoni root, the simplest path is the wrapper script (run from the root):

```bash
scripts/plot.sh
```

To run the module directly with options — the timing file is a **required** argument:

```bash
poetry run python -m bench_plotter.generate_plots benchmark_timing.json --output plots
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `intervals` (positional, required) | — | Path to the benchmark timing JSON |
| `--output` | `plots/` | Output directory for PNGs |
| `--interpol` | `100` | Interpolation points for mean/std normalization |
| `--workers` | all CPUs | Max parallel draw workers |
| `--no-parallel` | off | Render figures serially (for debugging) |

## Configuration

The Prometheus URL is hardcoded to `http://127.0.0.1:9090` in `settings.py` — the
benchmark always runs against a local Prometheus on the default port. To target a
different instance, edit `prometheus_base_url()` in `src/bench_plotter/settings.py`.

## What gets plotted

For each metric the plotter picks a representation from the intervals in the timing file:

| Intervals | Representation |
|-----------|----------------|
| 1 interval, or several of *different* modes | Windowed line chart, one series per mode overlaid |
| Several intervals of the *same* mode | Mean ± std band across the runs |

On top of that: resource metrics (vendor/client CPU and network) get steady-state box / ECDF / violin companions; TPS and latency-quantile charts are overlaid across modes; and vendor latency gets a steady-state box plot plus an ECDF and a histogram-reconstructed violin.

## Output structure

```
plots/
├── client_resources/
├── issuer_resources/
├── vendor_resources/
└── tps_metrics/
```

Each subfolder is a metric `section`. PNGs are 300 DPI.

## Project structure

```
bench-plotter/src/bench_plotter/
├── generate_plots/          # CLI wrapper
│   ├── __main__.py          #   `python -m bench_plotter.generate_plots`
│   ├── cli.py               #   argument parsing -> pipeline
│   └── common.py            #   output-dir cleanup, arg validators
├── pipeline/                # staged pipeline: plan -> fetch -> transform -> draw
│   ├── orchestrator.py      #   entry point: generate_plots_from_benchmark()
│   ├── plan.py              #   classify charts into typed PlotJobs
│   ├── resource.py / tps.py / latency.py     #   per-kind job builders
│   ├── fetch.py             #   concurrent, de-duplicated Prometheus queries
│   ├── transform.py + *_transform.py         #   PlotJobs -> DrawTasks
│   ├── draw.py              #   render DrawTasks in a process pool
│   └── model.py             #   QuerySpec / PlotJob / DrawTask contracts
├── metric_queries/          # PromQL query definitions per mode
│   ├── common.py            #   shared resource charts
│   └── signature.py / payword.py / paytree.py
├── plotting/                # matplotlib figure builders + windowing math
│   ├── windowing.py, histogram_math.py       #   pure data transforms
│   └── timeseries_renderers.py, distribution_renderers.py
├── draw_worker.py           # process-pool worker (pins the Agg backend)
├── prometheus_fetch.py      # Prometheus HTTP client
├── prometheus_matrix.py     # decode Prometheus matrix payloads
├── io_utils.py              # JSON loading
└── settings.py              # hardcoded Prometheus URL
```

`benchmark_timing.json` is written to the nanomoni root by `run_benchmark.sh` and is gitignored.

## Dependencies

`pandas`, `numpy`, `matplotlib`, `httpx`
