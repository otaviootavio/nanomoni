# Issuer environment variables

# Database settings (Redis)
# For docker compose
export ISSUER_DATABASE_URL="redis://redis-issuer:6379/0"

# For local development, without docker compose
# export ISSUER_DATABASE_URL="redis://localhost:6380/0"
export ISSUER_DATABASE_ECHO="false"

# API settings
export ISSUER_API_HOST="0.0.0.0"
export ISSUER_API_PORT="8001"
export ISSUER_API_DEBUG="false"
export ISSUER_API_CORS_ORIGINS='["*"]'

# Application settings
export ISSUER_APP_NAME="Issuer NanoMoni"
export ISSUER_APP_VERSION="1.0.0"

# Issuer private key (PEM format)
export ISSUER_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----
CCCcccCCCcccCCCcccCCCcccCCCcccCCCcccCCCcccCCCcccCCCcccCCCcccCCCT
XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
-----END PRIVATE KEY-----"

# Alternatively, you can generate the private key dynamically using: 
# export ISSUER_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)" 