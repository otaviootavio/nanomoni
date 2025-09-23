# Client environment variables

# Base URLs for docker compose environment
export VENDOR_BASE_URL="http://vendor:8000/api/v1"
export ISSUER_BASE_URL="http://issuer:8001/api/v1"

# For local development, without docker compose
# export VENDOR_BASE_URL="http://localhost:8000/api/v1"
# export ISSUER_BASE_URL="http://localhost:8001/api/v1"

# Client private key (PEM format) dinamically generated
export CLIENT_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)" 