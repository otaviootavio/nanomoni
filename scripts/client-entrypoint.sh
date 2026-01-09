#!/bin/bash
set -euo pipefail

required_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

required_env "VENDOR_BASE_URL"
required_env "ISSUER_BASE_URL"
required_env "CLIENT_PRIVATE_KEY_PEM"
required_env "CLIENT_PAYMENT_COUNT"
required_env "CLIENT_CHANNEL_AMOUNT"

poetry run python -m src.nanomoni.client_pay_chan