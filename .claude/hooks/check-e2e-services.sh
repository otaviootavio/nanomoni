#!/bin/bash
# PreToolUse hook: block E2E pytest runs when required services are not up.
# Reads the Bash tool input from stdin and checks Redis + API health.

cmd=$(jq -r '.tool_input.command // ""' 2>/dev/null)

# Only gate commands that look like e2e pytest invocations
if ! echo "$cmd" | grep -qE 'pytest' ; then
    exit 0
fi
if ! echo "$cmd" | grep -qE '(e2e|-m[[:space:]]+e2e|e2e[[:space:]]+-m)'; then
    exit 0
fi

missing=""

# Redis vendor (:6379)
if ! redis-cli -p 6379 ping > /dev/null 2>&1; then
    missing="${missing}\n  • redis-vendor on :6379  →  docker compose up -d redis-vendor"
fi

# Redis issuer (:6380)
if ! redis-cli -p 6380 ping > /dev/null 2>&1; then
    missing="${missing}\n  • redis-issuer on :6380  →  docker compose up -d redis-issuer"
fi

# Vendor API (:8000)
if ! curl -sf --max-time 2 http://localhost:8000/docs > /dev/null 2>&1; then
    missing="${missing}\n  • vendor on :8000  →  source envs/vendor.env.dev.sh && poetry run python -m nanomoni.main"
fi

# Issuer API (:8001)
if ! curl -sf --max-time 2 http://localhost:8001/docs > /dev/null 2>&1; then
    missing="${missing}\n  • issuer on :8001  →  source envs/issuer.env.dev.sh && poetry run python -m nanomoni.issuer_main"
fi

if [ -n "$missing" ]; then
    reason="E2E prerequisites not running. Start before testing:$(printf '%b' "$missing")"
    printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$reason\"}}"
    exit 0
fi

exit 0
