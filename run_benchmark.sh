#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# Target TPS sweep. For each TPS the client sends (TPS * RUN_DURATION_SEC)
# payments paced at 1/TPS, yielding ~RUN_DURATION_SEC seconds of traffic.
TPS_VALUES=(8 16 32 64 128 256 512 1024 2048 4096)
RUN_DURATION_SEC=600

# One virtual client per this many target TPS (own keypair + channel + payment
# loop each, see CLIENT_VIRTUAL_CLIENTS in envs/client.env.sh). A single
# sequential client's ceiling is 1/round_trip_latency (see
# run_tps_saturation_sweep.sh), so without fanning out, high-TPS iterations
# would silently fall short of their target instead of measuring it. Floored
# at 1 client when TPS < TPS_PER_CLIENT. TPS_VALUES at/above TPS_PER_CLIENT
# should stay multiples of this so fan-out divides evenly.
TPS_PER_CLIENT=256

export SLEEP_TIME=30
export SLEEP_GAP=30
# In-window drain: time (s) after the client stops, before the window closes, so the
# vendor/issuer returning to baseline is captured inside the plotted window.
export DRAIN_TIME=180

# Timestamp of this server-side benchmark execution (root folder for plots).
RUN_TS="$(date '+%Y%m%d_%H%M%S')"

# Current TPS/count/client-fanout for the active sweep iteration (set inside
# the loop).
BENCHMARK_TARGET_TPS=0
BENCHMARK_COUNT_VAR=0
BENCHMARK_VIRTUAL_CLIENTS=0

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

run_mode() {
  local mode="$1"
  local start end status=0

  # The run_<mode> callers source envs/client.env.sh just before calling this,
  # and that file may define CLIENT_TARGET_TPS. Exporting it here (after that
  # source) makes this benchmark's target win over the env file's value.
  export CLIENT_TARGET_TPS=$BENCHMARK_TARGET_TPS

  log "=== [$mode] starting benchmark run (tps=$BENCHMARK_TARGET_TPS, count=$BENCHMARK_COUNT_VAR, clients=$BENCHMARK_VIRTUAL_CLIENTS) ==="

  log "[$mode] pre-run gap: sleeping ${SLEEP_GAP}s"
  sleep "$SLEEP_GAP"

  log "[$mode] launching client container"
  # start_ms/finish_ms recorded here become the Prometheus query window the
  # plotter reads. Take start after the pre-run sleep, when traffic actually
  # begins, so the window covers the run itself and not SLEEP_GAP seconds of idle.
  start=$(date +%s%3N)
  # Capture the client exit status without letting `set -e` abort the script,
  # so cleanup always runs and the timing entry is always recorded.
  docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || status=$?
  log "[$mode] client container exited with status $status"

  docker compose stop client >/dev/null 2>&1 || true
  docker compose rm -fsv client >/dev/null 2>&1 || true

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
  docker compose exec -T redis-vendor redis-cli flushall >/dev/null || true

  local result="success"
  if [ "$status" -ne 0 ]; then
    result="failed"
    OVERALL_STATUS=1
  fi
  log "=== [$mode] finished: $result (window ${start}ms -> ${end}ms) ==="
  TIMING_ENTRIES+=("{\"mode\":\"$mode\",\"tps\":$BENCHMARK_TARGET_TPS,\"total_requests\":$BENCHMARK_COUNT_VAR,\"virtual_clients\":$BENCHMARK_VIRTUAL_CLIENTS,\"status\":\"$result\",\"prometheus_timestamps\":{\"start_ms\":$start,\"finish_ms\":$end}}")
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

log "Building client image (tps_values=${TPS_VALUES[*]}, duration=${RUN_DURATION_SEC}s)"
# Build the client image so the run uses current code (incl. the TPS delay plumbing).
docker compose build client

log "Server run timestamp: $RUN_TS"

for tps in "${TPS_VALUES[@]}"; do
  BENCHMARK_TARGET_TPS=$tps
  BENCHMARK_COUNT_VAR=$((tps * RUN_DURATION_SEC))
  # Floor at 1 so TPS below TPS_PER_CLIENT still generates a keypair instead of
  # an empty CLIENT_PRIVATE_KEY_PEMS (which the client rejects at startup).
  BENCHMARK_VIRTUAL_CLIENTS=$((tps / TPS_PER_CLIENT))
  if [ "$BENCHMARK_VIRTUAL_CLIENTS" -lt 1 ]; then
    BENCHMARK_VIRTUAL_CLIENTS=1
  fi
  # Read by envs/client.env.sh (sourced inside each run_<mode> below) to size
  # CLIENT_PRIVATE_KEY_PEMS -- must be exported before that source call.
  export CLIENT_VIRTUAL_CLIENTS=$BENCHMARK_VIRTUAL_CLIENTS
  log "=== Sweep iteration: tps=$BENCHMARK_TARGET_TPS count=$BENCHMARK_COUNT_VAR clients=$BENCHMARK_VIRTUAL_CLIENTS ==="

  run_signature
  sleep "$SLEEP_TIME"
  run_paytree
  sleep "$SLEEP_TIME"
  run_paytree_first_opt
  sleep "$SLEEP_TIME"
  run_paytree_child_pair
  sleep "$SLEEP_TIME"
  run_payword
  sleep "$SLEEP_TIME"
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
if poetry run python -m bench_plotter.sweep benchmark_timing.json; then
  log "Sweep plots generated successfully"
else
  log "Sweep plot generation failed (benchmark exit status unchanged)"
fi

# Propagate a non-zero exit code if any benchmark mode failed.
exit $OVERALL_STATUS
