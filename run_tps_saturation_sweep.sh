#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# Find the throughput ceiling of ONE sequential client.
#
# A NanoMoni client sends payments in a single sequential await loop, so its
# ceiling is 1/round_trip_latency. Its pacer only ever *delays* a payment -- once
# the loop is running late the sleep is simply skipped, and nothing reports the
# shortfall. So a run asking for 4000 TPS that can only manage 1000 still exits 0
# and looks exactly like a run that hit its target.
#
# This sweep makes that visible: it doubles the target TPS past the ceiling, then
# has the plotter read back the rate the vendor actually served and chart expected
# vs real. Where the curve leaves the diagonal is the saturation point.
#
# Unlike run_benchmark.sh this measures only throughput fidelity, so the runs and
# gaps are short and no resource/latency plots are produced.

# Doubling sweep: each step is compared against the ideal diagonal, so the knee
# is bracketed within a factor of 2 no matter where it falls. The top two rungs
# give headroom for CLIENT_VIRTUAL_CLIENTS > 1 runs to show a ceiling above what
# a single virtual client could reach; harmless (just extra runtime) otherwise.
TPS_VALUES=(16384)

# Virtual-client fan-out for this sweep (own keypair + channel + payment loop
# each, plus its own vendor connection). Kept a multiple of VENDOR_API_WORKERS:
# each virtual client stays on the worker that accepted its connection, so a
# count that does not divide by the worker count leaves some workers carrying an
# extra client and capping the measured ceiling.
CLIENT_VIRTUAL_CLIENTS=96

# Every mode: the ceiling is a property of per-payment cost, so each has its own,
# and the chart draws one line per mode. Same order as run_benchmark.sh.
MODES=(signature paytree paytree_first_opt paytree_child_pair payword)

# Seconds of traffic per run. Each run sends (TPS * RUN_DURATION_SEC) payments, so
# a run that cannot keep up takes proportionally LONGER -- that overshoot is the
# signal we are measuring. Must stay well above the plotter's rate() window
# (_RATE_WINDOW in bench_plotter/saturation/aggregate.py), because traffic shorter
# than that window reads low by (span / window) no matter how the client did; the
# report flags such runs as UNMEASURABLE.
RUN_DURATION_SEC=90

# Idle gap before a run (lets the vendor return to baseline, and the previous
# run's container finish being removed) and after it (lets Prometheus scrape the
# final counter increments before the window closes).
SLEEP_GAP=10
DRAIN_TIME=5

TIMING_FILE=tps_saturation_timing.json

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
TIMING_ENTRIES=()
OVERALL_STATUS=0

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# configure_mode <mode> <count>: export the client env for one run.
configure_mode() {
  local mode="$1" count="$2"

  # Sourced first because it may define CLIENT_TARGET_TPS; the caller's target is
  # exported after this so it wins. It also generates CLIENT_PRIVATE_KEY_PEMS
  # (one key per CLIENT_VIRTUAL_CLIENTS, set above).
  source envs/client.env.sh
  export CLIENT_PAYMENT_MODE="$mode"
  export CLIENT_PAYMENT_COUNT="$count"

  # The runner splits CLIENT_PAYMENT_COUNT across CLIENT_VIRTUAL_CLIENTS, and each
  # virtual client opens its own channel, so the commitment caps below size ONE
  # client's tree/chain. Passing the sweep-wide count here would make every client
  # build a commitment CLIENT_VIRTUAL_CLIENTS times larger than it can spend.
  local per_client_count=$((count / CLIENT_VIRTUAL_CLIENTS))

  case "$mode" in
    paytree | paytree_first_opt | paytree_child_pair)
      export CLIENT_PAYTREE_MAX_I="$per_client_count"
      # channel_amount must cover (max_i * unit_value) with headroom.
      export CLIENT_CHANNEL_AMOUNT=10000000
      ;;
    payword)
      export CLIENT_PAYWORD_MAX_K="$per_client_count"
      export CLIENT_CHANNEL_AMOUNT=10000000
      ;;
    signature) ;;
    *)
      log "unknown mode '$mode'"
      return 1
      ;;
  esac
}

# run_one <mode> <tps> <count>: run the client once and record its window.
run_one() {
  local mode="$1" tps="$2" count="$3"
  local start end status=0

  configure_mode "$mode" "$count"
  export CLIENT_TARGET_TPS="$tps"

  log "=== [$mode] target=${tps} TPS, count=${count}, clients=${CLIENT_VIRTUAL_CLIENTS} (ideal ${RUN_DURATION_SEC}s of traffic) ==="

  # Every mode starts from an empty keyspace. Nothing deletes channels, states or
  # merkle nodes after a run, so without this each mode inherits every earlier
  # one: more memory, and an AOF whose rewrites grow with the accumulated dataset
  # while the run is in flight. That penalty lands on whichever mode happens to
  # run last, which is not a property of the mode. Done before the gap so the
  # reclaim and the rewrite it triggers settle before traffic starts.
  log "[$mode] flushing both datastores"
  docker compose exec -T redis-vendor redis-cli flushall >/dev/null || true
  docker compose exec -T redis-issuer redis-cli flushall >/dev/null || true

  log "[$mode] pre-run gap: sleeping ${SLEEP_GAP}s"
  sleep "$SLEEP_GAP"

  # start/end bound the Prometheus query window the plotter reads back.
  start=$(date +%s%3N)
  docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || status=$?
  log "[$mode] client exited with status $status"

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
  local elapsed=$(((end - start) / 1000))
  log "=== [$mode] target=${tps} finished: $result in ${elapsed}s, clients=${CLIENT_VIRTUAL_CLIENTS} ==="
  TIMING_ENTRIES+=("{\"mode\":\"$mode\",\"tps\":$tps,\"total_requests\":$count,\"status\":\"$result\",\"prometheus_timestamps\":{\"start_ms\":$start,\"finish_ms\":$end}}")
}

log "Building client image so the run uses current code"
docker compose build client

log "Sweep: modes=[${MODES[*]}] targets=[${TPS_VALUES[*]}] duration=${RUN_DURATION_SEC}s clients=${CLIENT_VIRTUAL_CLIENTS} run_ts=$RUN_TS"

for mode in "${MODES[@]}"; do
  for tps in "${TPS_VALUES[@]}"; do
    run_one "$mode" "$tps" "$((tps * RUN_DURATION_SEC))"
  done
done

log "Writing $TIMING_FILE"
RUNS_JSON="[$(IFS=,; echo "${TIMING_ENTRIES[*]}")]"
jq -n --arg ts "$RUN_TS" --argjson runs "$RUNS_JSON" \
  --argjson virtual_clients "$CLIENT_VIRTUAL_CLIENTS" \
  '{server_run_timestamp: $ts, runs: $runs, virtual_clients: $virtual_clients}' > "$TIMING_FILE"

if [ "$OVERALL_STATUS" -eq 0 ]; then
  log "All runs completed"
else
  log "Some runs failed (see above)"
fi

# Best-effort report: do not override the benchmark exit status.
log "Generating expected-vs-real TPS chart"
if poetry run python -m bench_plotter.saturation "$TIMING_FILE" --title true; then
  log "Saturation report generated"
else
  log "Saturation report failed (benchmark exit status unchanged)"
fi

exit $OVERALL_STATUS
