#!/bin/bash
set -euo pipefail

required_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

required_env "ISSUER_DATABASE_URL"
required_env "ISSUER_DATABASE_ECHO"
required_env "ISSUER_API_HOST"
required_env "ISSUER_API_PORT"
required_env "ISSUER_API_DEBUG"
required_env "ISSUER_API_CORS_ORIGINS"
required_env "PROMETHEUS_MULTIPROC_DIR"
required_env "ISSUER_APP_NAME"
required_env "ISSUER_APP_VERSION"
required_env "ISSUER_PRIVATE_KEY_PEM"

poetry run python -m src.nanomoni.issuer_main 