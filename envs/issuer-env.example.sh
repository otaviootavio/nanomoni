# Issuer environment variables

# Database settings
export ISSUER_DATABASE_URL="sqlite:///issuer-nanomoni.db"
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
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
-----END PRIVATE KEY-----"