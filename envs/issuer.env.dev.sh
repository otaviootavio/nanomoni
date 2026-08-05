# Issuer environment variables — local development (hybrid: Poetry app + Docker Redis)
#
# Start Redis sidecar first:
#   docker compose up -d redis-issuer
#
# Then run the issuer:
#   source ./envs/issuer.env.dev.sh && poetry run python -m nanomoni.issuer_main

# Database settings (Redis on localhost, mapped by docker-compose ports: 6380:6379)
export ISSUER_DATABASE_URL="redis://localhost:6380/0"
export ISSUER_DATABASE_ECHO="false"

# API settings — debug enables uvicorn --reload
export ISSUER_API_HOST="0.0.0.0"
export ISSUER_API_PORT="8001"
export ISSUER_API_DEBUG="true"
export ISSUER_API_CORS_ORIGINS="*"

# Prometheus (dev throwaway path — metrics not collected locally)
export PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_issuer_dev"

# Application settings
export ISSUER_APP_NAME="Issuer NanoMoni"
export ISSUER_APP_VERSION="1.0.0"

# Issuer private key — generated fresh each shell session
export ISSUER_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)"
