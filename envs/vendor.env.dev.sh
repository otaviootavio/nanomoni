# Vendor environment variables — local development (hybrid: Poetry app + Docker Redis)
#
# Start Redis sidecar first:
#   docker compose up -d redis-vendor
#
# Then run the vendor:
#   source ./envs/vendor.env.dev.sh && poetry run python -m nanomoni.main
#
# The issuer must also be running locally on port 8001 (see issuer.env.dev.sh).

# Database settings (Redis on localhost, mapped by docker-compose ports: 6379:6379)
export VENDOR_DATABASE_URL="redis://localhost:6379/0"
export VENDOR_DATABASE_ECHO="false"

# API settings — debug enables uvicorn --reload (forces single worker)
export VENDOR_API_HOST="0.0.0.0"
export VENDOR_API_PORT="8000"
export VENDOR_API_DEBUG="true"
export VENDOR_API_CORS_ORIGINS="*"
export VENDOR_API_WORKERS="1"

# Off for local dev: with no cpuset the single worker would be pinned to an
# arbitrary core of the whole machine.
export VENDOR_PIN_WORKERS_TO_CORES="false"

# Prometheus (dev throwaway path — metrics not collected locally)
export PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_vendor_dev"

# Application settings
export VENDOR_APP_NAME="Vendor NanoMoni"
export VENDOR_APP_VERSION="1.0.0"

# Issuer base URL — local issuer running on localhost
export ISSUER_BASE_URL="http://127.0.0.1:8001/api/v1"

# Vendor private key — generated fresh each shell session
export VENDOR_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)"
