# Vendor environment variables

# Database settings
export VENDOR_DATABASE_URL="sqlite:///vendor-nanomoni.db"
export VENDOR_DATABASE_ECHO="false"

# API settings
export VENDOR_API_HOST="0.0.0.0"
export VENDOR_API_PORT="8000"
export VENDOR_API_DEBUG="false"
export VENDOR_API_CORS_ORIGINS="*"

# Application settings
export VENDOR_APP_NAME="Vendor NanoMoni"
export VENDOR_APP_VERSION="1.0.0"

# Issuer base URL (used by middleware to fetch issuer public key)
# Default issuer example: http://127.0.0.1:8001/api/v1
export ISSUER_BASE_URL="http://127.0.0.1:8001/api/v1" 