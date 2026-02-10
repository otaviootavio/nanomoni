#!/bin/bash
set -euo pipefail

required_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

required_env "VENDOR_DATABASE_URL"
#required_env "VENDOR_DATABASE_ECHO"
required_env "VENDOR_API_HOST"
required_env "VENDOR_API_PORT"
required_env "VENDOR_API_DEBUG"
required_env "VENDOR_API_CORS_ORIGINS"
required_env "VENDOR_API_WORKERS"
required_env "PROMETHEUS_MULTIPROC_DIR"
required_env "VENDOR_APP_NAME"
required_env "VENDOR_APP_VERSION"
required_env "VENDOR_PRIVATE_KEY_PEM"
required_env "ISSUER_BASE_URL"

poetry run python -m src.nanomoni.main 