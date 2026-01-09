# Client environment variables

# Base URLs for docker compose environment
export VENDOR_BASE_URL="http://vendor:8000/api/v1"
export ISSUER_BASE_URL="http://issuer:8001/api/v1"

# Base URLs for local development
# export VENDOR_BASE_URL="http://localhost:8000/api/v1"
# export ISSUER_BASE_URL="http://localhost:8001/api/v1"

# Client private key (PEM format) dynamically generated (unless already provided)
export CLIENT_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)"

export CLIENT_PAYMENT_COUNT=100000

export CLIENT_CHANNEL_AMOUNT=10000000

export CLIENT_RAMP_DELAY_SEC=5