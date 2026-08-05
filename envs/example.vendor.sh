# Vendor environment variables

# Database settings (Redis)
# For docker compose
export VENDOR_DATABASE_URL="redis://redis-vendor:6379/0"

# For local development, without docker compose
# export VENDOR_DATABASE_URL="redis://localhost:6379/0"

export VENDOR_DATABASE_ECHO="false"

# API settings
export VENDOR_API_HOST="0.0.0.0"
export VENDOR_API_PORT="8000"
export VENDOR_API_DEBUG="false"
export VENDOR_API_CORS_ORIGINS="*"
# Each worker is its own single-worker server on its own port, counting up from
# VENDOR_API_PORT (N workers occupy PORT..PORT+N-1). Keep this at 1 outside the
# benchmark: on the host, 8001 and 8002 already belong to the issuer and to the
# client's metrics. The client's CLIENT_VENDOR_PORT_COUNT must match this value.
export VENDOR_API_WORKERS="1"

# Pin each Uvicorn worker to a single core of the container's cpuset, so the
# kernel cannot migrate it mid-run. Needs a cpuset with at least
# VENDOR_API_WORKERS cores; leave "false" outside benchmarks.
export VENDOR_PIN_WORKERS_TO_CORES="false"

# Prometheus multiprocess metrics directory (must be writable by the app)
export PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_vendor"

# Application settings
export VENDOR_APP_NAME="Vendor NanoMoni"
export VENDOR_APP_VERSION="1.0.0" 

# Issuer base URL
# export ISSUER_BASE_URL="http://127.0.0.1:8001/api/v1" 
export ISSUER_BASE_URL="http://issuer:8001/api/v1" 

# Vendor private key (PEM format) dinamically generated
export VENDOR_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)" 