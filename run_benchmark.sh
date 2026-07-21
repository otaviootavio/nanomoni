#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

export BENCHMARK_COUNT_VAR=1048576
# export BENCHMARK_COUNT_VAR=8192

export SLEEP_TIME=30
export SLEEP_GAP=30
# In-window drain: time (s) after the client stops, before the window closes, so the
# vendor/issuer returning to baseline is captured inside the plotted window.
export DRAIN_TIME=180

# Target TPS ceiling (edit here). Set to 0 for no limit (max throughput).
# The client derives the per-payment delay (1/TPS) itself
BENCHMARK_TARGET_TPS=250

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

  # Exported here (after the caller sources envs/client.env.sh) so the target
  # TPS always wins over anything the env file might set.
  export CLIENT_TARGET_TPS=$BENCHMARK_TARGET_TPS

  log "=== [$mode] starting benchmark run ==="

  start=$(date +%s%3N)
  log "[$mode] pre-run gap: sleeping ${SLEEP_GAP}s"
  sleep "$SLEEP_GAP"

  log "[$mode] launching client container"
  # Capture the client exit status without letting `set -e` abort the script,
  # so cleanup always runs and the timing entry is always recorded.
  docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || status=$?
  log "[$mode] client container exited with status $status"

  docker compose stop client >/dev/null 2>&1 || true
  docker compose rm -fsv client >/dev/null 2>&1 || true

  log "[$mode] drain gap: sleeping ${DRAIN_TIME}s"
  sleep "$DRAIN_TIME"
  end=$(date +%s%3N)

  local result="success"
  if [ "$status" -ne 0 ]; then
    result="failed"
    OVERALL_STATUS=1
  fi
  log "=== [$mode] finished: $result (window ${start}ms -> ${end}ms) ==="
  TIMING_ENTRIES+=("{\"mode\":\"$mode\",\"status\":\"$result\",\"prometheus_timestamps\":{\"start_ms\":$start,\"finish_ms\":$end}}")
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
  export CLIENT_PAYTREE_MAX_I=$BENCHMARK_COUNT_VAR
  # Ensure channel_amount >= (max_i * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "paytree"
}

run_payword() {
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="payword"
  export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
  export CLIENT_PAYWORD_MAX_K=$BENCHMARK_COUNT_VAR
  # Ensure channel_amount >= (max_k * unit_value) with headroom for remainder.
  export CLIENT_CHANNEL_AMOUNT=10000000
  run_mode "payword"
}

log "Building client image (count=$BENCHMARK_COUNT_VAR, target_tps=$BENCHMARK_TARGET_TPS)"
# Build the client image so the run uses current code (incl. the TPS delay plumbing).
docker compose build client

run_signature
sleep "$SLEEP_TIME"
run_paytree
sleep "$SLEEP_TIME"
run_payword

log "All modes complete, writing benchmark_timing.json"
# Join the entries with commas and write the timing JSON.
TIMING_JSON="[$(IFS=,; echo "${TIMING_ENTRIES[*]}")]"
echo "$TIMING_JSON" | jq '.' > benchmark_timing.json

if [ "$OVERALL_STATUS" -eq 0 ]; then
  log "Benchmark run finished successfully"
else
  log "Benchmark run finished with failures"
fi

# Propagate a non-zero exit code if any benchmark mode failed.
exit $OVERALL_STATUS
