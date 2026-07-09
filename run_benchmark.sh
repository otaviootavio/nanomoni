#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# export BENCHMARK_COUNT_VAR=1048576
export BENCHMARK_COUNT_VAR=8192
export SLEEP_TIME=${SLEEP_TIME:-100}
export SLEEP_GAP=${SLEEP_GAP:-10}

# optional inter‑payment delay (seconds) used by benchmark client
export CLIENT_INTER_PAYMENT_DELAY_S=${CLIENT_INTER_PAYMENT_DELAY_S:-0}
# alternative: specify target TPS and the script will compute delay for you
if [ -n "${BENCHMARK_TARGET_TPS:-}" ]; then
  CLIENT_INTER_PAYMENT_DELAY_S=$(awk "BEGIN{printf \"%.6f\", 1/${BENCHMARK_TARGET_TPS}}")
  export CLIENT_INTER_PAYMENT_DELAY_S
fi

docker compose build client

# Timing JSON
TIMING_JSON=""

# Signature
source envs/client.env.sh
export CLIENT_PAYMENT_MODE="signature"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR

START=$(date +%s%3N)
sleep $SLEEP_GAP
# Capture the client exit status without letting `set -e` abort the script,
# so the cleanup below always runs and timing JSON is always recorded.
STATUS=0
docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || STATUS=$?
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true
sleep $SLEEP_GAP
END=$(date +%s%3N)

if [ $STATUS -eq 0 ]; then
  TIMING_JSON="$TIMING_JSON{\"mode\":\"signature\",\"status\":\"success\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
else
  TIMING_JSON="$TIMING_JSON{\"mode\":\"signature\",\"status\":\"failed\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
fi

sleep $SLEEP_TIME
source envs/client.env.sh
export CLIENT_PAYMENT_MODE="paytree"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
export CLIENT_PAYTREE_MAX_I=$BENCHMARK_COUNT_VAR
# Ensure channel_amount >= (max_i * unit_value) with some headroom for remainder
# With unit_value=1 and max_i=500000, we need at least 500000, but use 10000000 for safety
export CLIENT_CHANNEL_AMOUNT=10000000

START=$(date +%s%3N)
sleep $SLEEP_GAP
# Capture the client exit status without letting `set -e` abort the script,
# so the cleanup below always runs and timing JSON is always recorded.
STATUS=0
docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || STATUS=$?
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true
sleep $SLEEP_GAP
END=$(date +%s%3N)

if [ $STATUS -eq 0 ]; then
  TIMING_JSON="$TIMING_JSON,{\"mode\":\"paytree\",\"status\":\"success\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
else
  TIMING_JSON="$TIMING_JSON,{\"mode\":\"paytree\",\"status\":\"failed\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
fi

sleep $SLEEP_TIME
source envs/client.env.sh
export CLIENT_PAYMENT_MODE="payword"
export CLIENT_PAYMENT_COUNT=$BENCHMARK_COUNT_VAR
export CLIENT_PAYWORD_MAX_K=$BENCHMARK_COUNT_VAR
# Ensure channel_amount >= (max_k * unit_value) with some headroom for remainder
# With unit_value=1 and max_k=500000, we need at least 500000, but use 10000000 for safety
export CLIENT_CHANNEL_AMOUNT=10000000

START=$(date +%s%3N)
sleep $SLEEP_GAP
# Capture the client exit status without letting `set -e` abort the script,
# so the cleanup below always runs and timing JSON is always recorded.
STATUS=0
docker compose up --no-deps --abort-on-container-exit --exit-code-from client client || STATUS=$?
docker compose stop client >/dev/null 2>&1 || true
docker compose rm -fsv client >/dev/null 2>&1 || true
sleep $SLEEP_GAP
END=$(date +%s%3N)

if [ $STATUS -eq 0 ]; then
  TIMING_JSON="$TIMING_JSON,{\"mode\":\"payword\",\"status\":\"success\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
else
  TIMING_JSON="$TIMING_JSON,{\"mode\":\"payword\",\"status\":\"failed\",\"prometheus_timestamps\":{\"start_ms\":$START,\"finish_ms\":$END}}"
fi

TIMING_JSON="[$TIMING_JSON]"
echo "$TIMING_JSON" | jq '.' > benchmark_timing.json