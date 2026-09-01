#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# Two sweep axes, each one plain array, used directly wherever needed below --
# no derived/aliased copies of either.
#
# TPS_VALUES: target TPS per run. DURATION_VALUES: run length in seconds per
# run (DURATION_VALUES[0] is the baseline every TPS_VALUES entry runs at;
# the rest are extra points the duration sweep below adds, at every TPS_VALUES
# entry, to isolate the amortization confound explained next).
#
# Every run is paced at 1/TPS for BENCHMARK_COUNT_VAR = tps * duration
# payments (set in run_sweep_point below), so payment count scales with both
# TPS and duration instead of staying fixed. That means a fixed one-time cost
# (process warm-up, first-call cache misses, connection-pool init) gets
# diluted over more payments the higher tps*duration is, so a *_per_payment
# curve that flattens as TPS grows is ambiguous between "no real concurrency
# effect" and "just more payments to amortize the same fixed cost over". The
# duration sweep (varying payment count at fixed TPS, cost = a + b*count
# regression) exists to isolate that.
#
# The payment-count swing is real and by design: at the lowest TPS_VALUES
# entry, the baseline duration only buys a few hundred payments -- too few
# raw eBPF ticks (see sample_rate in alloy.config) for a single run's
# crypto/db/other split to be trustworthy on its own. REPEATS below exists to
# cover exactly that: averaging N independent runs of the same (mode, tps,
# total_requests) approximates the variance reduction of one N-times-longer
# run, without reintroducing the bucket-boundary sensitivity a longer window
# would (every repeat's window is still exactly the same duration long).
TPS_VALUES=(500 250 100)
DURATION_VALUES=(300 150 75)

# How many independent repeats to run at each (mode, tps, total_requests)
# point, for both sweeps below. bench_plotter (bench_plotter/repeats.py)
# averages repeats sharing that key and its vs-TPS charts draw the resulting
# mean +/- sample std dev as error bars, so a curve's remaining wiggle vs its
# own error bars is what tells a real trend apart from run-to-run noise,
# instead of eyeballing a single noisy line. Total sweep run time scales
# linearly with this.
REPEATS=3

# One virtual client per this many target TPS (own keypair + channel + payment
# loop each, see CLIENT_VIRTUAL_CLIENTS in envs/client.env.sh). A single
# sequential client's ceiling is 1/round_trip_latency (see
# run_tps_saturation_sweep.sh), so without fanning out, high-TPS iterations
# would silently fall short of their target instead of measuring it. Floored
# at 1 client when TPS < TPS_PER_CLIENT. TPS_VALUES at/above TPS_PER_CLIENT
# should stay multiples of this so fan-out divides evenly.
TPS_PER_CLIENT=1000

export SLEEP_TIME=15
export SLEEP_GAP=15
# In-window drain: time (s) after the client stops, before the window closes, so the
# vendor/issuer returning to baseline is captured inside the plotted window.
export DRAIN_TIME=15

# Timestamp of this server-side benchmark execution (root folder for plots).
RUN_TS="$(date '+%Y%m%d_%H%M%S')"

# Current TPS/count/client-fanout/repeat for the active sweep iteration (set
# inside the loop).
BENCHMARK_TARGET_TPS=0
BENCHMARK_COUNT_VAR=0
BENCHMARK_VIRTUAL_CLIENTS=0
BENCHMARK_REPEAT=0

# Per-mode timing entries, joined into the timing JSON at the end.
TIMING_ENTRIES=()

# Aggregate exit status: becomes non-zero if any benchmark mode fails, while
# still allowing subsequent modes to run.
OVERALL_STATUS=0

# run_mode <mode>: run the already-configured client once and record its window.
# The caller must have exported CLIENT_PAYMENT_MODE and any mode-specific vars.
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# docker-compose.yml interpolates every ${VAR} it references on ANY compose
# command, including vendor/issuer vars this script never sources (those
# services are started separately) -- so even a client-only command warns
# about each one. That warning is legitimate wherever those vars are truly
# meant to be set; here it never applies, so filter it out of this script's
# own compose calls only, leaving `docker compose` unaffected everywhere else.
dc() {
  docker compose "$@" 2> >(grep -Fv 'variable is not set. Defaulting to a blank string.' >&2)
}

run_mode() {
  local mode="$1"
  local start end status=0

  # The run_<mode> callers source envs/client.env.sh just before calling this,
  # and that file may define CLIENT_TARGET_TPS. Exporting it here (after that
  # source) makes this benchmark's target win over the env file's value.
  export CLIENT_TARGET_TPS=$BENCHMARK_TARGET_TPS

  log "=== [$mode] starting benchmark run (tps=$BENCHMARK_TARGET_TPS, count=$BENCHMARK_COUNT_VAR, clients=$BENCHMARK_VIRTUAL_CLIENTS, repeat=$BENCHMARK_REPEAT) ==="

  log "[$mode] pre-run gap: sleeping ${SLEEP_GAP}s"
  sleep "$SLEEP_GAP"

  log "[$mode] launching client container"
  # start_ms/finish_ms recorded here become the Prometheus query window the
  # plotter reads. Take start after the pre-run sleep, when traffic actually
  # begins, so the window covers the run itself and not SLEEP_GAP seconds of idle.
  start=$(date +%s%3N)
  # Capture the client exit status without letting `set -e` abort the script,
  # so cleanup always runs and the timing entry is always recorded.
  # Compose's own status lines (Attaching to/Created/Started/exited) plus the
  # client's log lines are captured to a file instead of streamed live: at
  # REPEATS * len(TPS_VALUES) * modes runs, that noise would otherwise repeat
  # hundreds of times over one sweep. Surfaced only on failure, where it is
  # the only record of what the client actually did.
  local up_log
  up_log="$(mktemp)"
  dc up --no-deps --abort-on-container-exit --exit-code-from client client >"$up_log" 2>&1 || status=$?
  log "[$mode] client container exited with status $status"
  if [ "$status" -ne 0 ]; then
    log "[$mode] client container output (status $status):"
    cat "$up_log"
  fi
  rm -f "$up_log"

  dc stop client >/dev/null 2>&1 || true
  dc rm -fsv client >/dev/null 2>&1 || true

  log "[$mode] drain gap: sleeping ${DRAIN_TIME}s"
  sleep "$DRAIN_TIME"
  end=$(date +%s%3N)

  # Nothing deletes channels, states or merkle nodes during a run, so without
  # this every later run inherits every earlier one: more memory, and an AOF
  # whose rewrites grow with the accumulated dataset while traffic is in flight.
  # That penalty lands on whichever mode happens to run last, which is not a
  # property of the mode. Done after the window closes so the reclaim (and the
  # rewrite it triggers) is not measured as part of this run.
  log "[$mode] flushing vendor datastore"
  dc exec -T redis-vendor redis-cli flushall >/dev/null || true

  local result="success"
  if [ "$status" -ne 0 ]; then
    result="failed"
    OVERALL_STATUS=1
  fi
  log "=== [$mode] finished: $result (window ${start}ms -> ${end}ms) ==="
  # drain_sec is recorded because the plotter cannot recover it from the window
  # alone: it reads back the *settled* Redis footprint as the median over these
  # trailing seconds. Reducing with the peak instead would score whatever
  # transient the run's teardown happened to produce (see _settled_value in
  # bench_plotter/sweep/aggregate.py).
  TIMING_ENTRIES+=("{\"mode\":\"$mode\",\"tps\":$BENCHMARK_TARGET_TPS,\"total_requests\":$BENCHMARK_COUNT_VAR,\"virtual_clients\":$BENCHMARK_VIRTUAL_CLIENTS,\"repeat\":$BENCHMARK_REPEAT,\"status\":\"$result\",\"drain_sec\":$DRAIN_TIME,\"prometheus_timestamps\":{\"start_ms\":$start,\"finish_ms\":$end}}")
}

run_signature() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="signature"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  run_mode "signature"
}

run_paytree() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="paytree"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  # Each virtual client opens its own channel, so the cap sizes ONE client's
  # tree, not the sweep-wide count (see run_tps_saturation_sweep.sh).
  export CLIENT_PAYTREE_MAX_I=$((BENCHMARK_COUNT_VAR / BENCHMARK_VIRTUAL_CLIENTS))
  # Ensure channel_amount >= (max_i * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "paytree"
}

run_paytree_first_opt() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="paytree_first_opt"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  export CLIENT_PAYTREE_MAX_I=$((BENCHMARK_COUNT_VAR / BENCHMARK_VIRTUAL_CLIENTS))
  # Ensure channel_amount >= (max_i * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "paytree_first_opt"
}

run_paytree_second_opt() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="paytree_second_opt"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  export CLIENT_PAYTREE_MAX_I=$((BENCHMARK_COUNT_VAR / BENCHMARK_VIRTUAL_CLIENTS))
  # Ensure channel_amount >= (max_i * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "paytree_second_opt"
}

run_paytree_child_pair() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="paytree_child_pair"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  export CLIENT_PAYTREE_MAX_I=$((BENCHMARK_COUNT_VAR / BENCHMARK_VIRTUAL_CLIENTS))
  # Ensure channel_amount >= (max_i * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "paytree_child_pair"
}

run_payword() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="payword"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  export CLIENT_PAYWORD_MAX_K=$((BENCHMARK_COUNT_VAR / BENCHMARK_VIRTUAL_CLIENTS))
  # Ensure channel_amount >= (max_k * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "payword"
}

# run_sweep_point <tps> <duration_sec> <repeats>: run every active mode
# <repeats> times at one (tps, duration) point -- one cell of the
# TPS_VALUES x DURATION_VALUES grid swept below.
run_sweep_point() {
  local tps="$1" duration_sec="$2" repeats="$3"
  BENCHMARK_TARGET_TPS=$tps
  BENCHMARK_COUNT_VAR=$((tps * duration_sec))
  # Floor at 1 so TPS below TPS_PER_CLIENT still generates a keypair instead of
  # an empty CLIENT_PRIVATE_KEY_PEMS (which the client rejects at startup).
  BENCHMARK_VIRTUAL_CLIENTS=$((tps / TPS_PER_CLIENT))
  if [ "$BENCHMARK_VIRTUAL_CLIENTS" -lt 1 ]; then
    BENCHMARK_VIRTUAL_CLIENTS=1
  fi
  # Read by envs/client.env.sh (sourced inside each run_<mode> below) to size
  # CLIENT_PRIVATE_KEY_PEMS -- must be exported before that source call.
  export CLIENT_VIRTUAL_CLIENTS=$BENCHMARK_VIRTUAL_CLIENTS

  # Repeats are the outer loop (not nested per-mode) so a full pass over
  # every mode completes before the next repeat starts: any drift over the
  # sweep's total run time (e.g. host thermal/scheduling state) then lands on
  # every mode's repeat N alike, instead of piling onto whichever mode
  # happens to run its repeats last.
  local repeat
  for ((repeat = 0; repeat < repeats; repeat++)); do
    BENCHMARK_REPEAT=$repeat
    log "=== Sweep iteration: tps=$BENCHMARK_TARGET_TPS duration=${duration_sec}s count=$BENCHMARK_COUNT_VAR clients=$BENCHMARK_VIRTUAL_CLIENTS repeat=$((repeat + 1))/$repeats ==="

    run_signature
    sleep "$SLEEP_TIME"
    run_paytree
    sleep "$SLEEP_TIME"
    run_paytree_second_opt
    sleep "$SLEEP_TIME"
    run_paytree_first_opt
    sleep "$SLEEP_TIME"
    run_paytree_child_pair
    sleep "$SLEEP_TIME"
    run_payword
    sleep "$SLEEP_TIME"
  done
}

# IFS is set to $'\n\t' above, so "${ARRAY[*]}" would join elements with a
# newline instead of a space -- force a space join here regardless.
log "Building client image (tps_values=$(IFS=' '; echo "${TPS_VALUES[*]}"), duration_values=$(IFS=' '; echo "${DURATION_VALUES[*]}"), repeats=${REPEATS})"
# Build the client image so the run uses current code (incl. the TPS delay plumbing).
# Output captured and only shown on failure -- see the same rationale in run_mode.
BUILD_LOG="$(mktemp)"
if ! dc build client >"$BUILD_LOG" 2>&1; then
  log "Client image build failed, output:"
  cat "$BUILD_LOG"
  rm -f "$BUILD_LOG"
  exit 1
fi
rm -f "$BUILD_LOG"

# Guarantee a clean starting keyspace even if a prior run was interrupted before
# its post-run flush (e.g. killed mid-drain), so the first mode of this sweep
# never inherits leftover channels/states/merkle nodes from an earlier run.
log "Pre-sweep flush: clearing vendor and issuer datastores"
dc exec -T redis-vendor redis-cli flushall >/dev/null || true
dc exec -T redis-issuer redis-cli flushall >/dev/null || true

log "Server run timestamp: $RUN_TS"

log "=== Sweep: tps_values=$(IFS=' '; echo "${TPS_VALUES[*]}") durations=$(IFS=' '; echo "${DURATION_VALUES[*]}") repeats=${REPEATS} ==="
for tps in "${TPS_VALUES[@]}"; do
  for duration in "${DURATION_VALUES[@]}"; do
    run_sweep_point "$tps" "$duration" "$REPEATS"
  done
done

log "All modes complete, writing benchmark_timing.json"
# Join the entries with commas and write the timing JSON as an object with
# server_run_timestamp + runs (the plotter sweep module consumes this shape).
RUNS_JSON="[$(IFS=,; echo "${TIMING_ENTRIES[*]}")]"
jq -n --arg ts "$RUN_TS" --argjson runs "$RUNS_JSON" \
  '{server_run_timestamp: $ts, runs: $runs}' > benchmark_timing.json

if [ "$OVERALL_STATUS" -eq 0 ]; then
  log "Benchmark run finished successfully"
else
  log "Benchmark run finished with failures"
fi

# Best-effort plot generation: do not override the benchmark exit status.
log "Generating sweep plots from benchmark_timing.json"
if poetry run python -m bench_plotter.sweep benchmark_timing.json --title false; then
  log "Sweep plots generated successfully"
else
  log "Sweep plot generation failed (benchmark exit status unchanged)"
fi

# Propagate a non-zero exit code if any benchmark mode failed.
exit $OVERALL_STATUS
