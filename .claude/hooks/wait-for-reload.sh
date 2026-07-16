#!/bin/bash
# PostToolUse hook: after editing a Python source file, wait for uvicorn to
# finish reloading before returning context to the model.
# Only activates when the vendor service is already running (dev mode).

file_path=$(jq -r '.tool_input.file_path // ""' 2>/dev/null)

# Only care about Python files inside src/nanomoni/
if ! echo "$file_path" | grep -qE 'src/nanomoni/.*\.py$'; then
    exit 0
fi

# If vendor is not running, nothing to wait for (unit-test workflow)
if ! curl -sf --max-time 1 http://localhost:8000/docs > /dev/null 2>&1; then
    exit 0
fi

# Give uvicorn a moment to detect the change and start restarting
sleep 0.4

# Poll until the vendor comes back (up to 12 seconds, 0.5s intervals)
for i in $(seq 1 24); do
    if curl -sf --max-time 1 http://localhost:8000/docs > /dev/null 2>&1; then
        printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"uvicorn reloaded after editing $(basename "$file_path"). Services are ready — safe to run tests.\"}}"
        exit 0
    fi
    sleep 0.5
done

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"Warning: vendor did not respond within 12s after editing $(basename "$file_path"). Check the service logs before running tests.\"}}"
exit 0
