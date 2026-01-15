# Client environment variables

# Base URLs for docker compose environment
export VENDOR_BASE_URL="http://vendor:8000/api/v1"
export ISSUER_BASE_URL="http://issuer:8001/api/v1"

# Base URLs for local development
# export VENDOR_BASE_URL="http://localhost:8000/api/v1"
# export ISSUER_BASE_URL="http://localhost:8001/api/v1"

# Client private key (PEM format) dynamically generated (unless already provided)
export CLIENT_PRIVATE_KEY_PEM="$(openssl ecparam -genkey -name secp256k1 | openssl pkcs8 -topk8 -nocrypt)"

export CLIENT_PAYMENT_COUNT=5000

export CLIENT_CHANNEL_AMOUNT=10000000

# Client payment mode:
# - "signature": send signed owed_amount updates (existing behavior)
# - "payword": send PayWord hash-chain tokens (k, token_b64)
export CLIENT_PAYMENT_MODE="payword"

# PayWord mode mental model:
# - You lock funds in the channel with CLIENT_CHANNEL_AMOUNT (money cap).
# - You send a monotonic counter k; owed_amount = k * CLIENT_PAYWORD_UNIT_VALUE (step value).
# - Constraints enforced by vendor/issuer:
#   1) k must be increasing
#   2) k <= CLIENT_PAYWORD_MAX_K (step cap committed when opening the channel)
#   3) k * unit_value <= CLIENT_CHANNEL_AMOUNT (money cap)
#
# Good default if you're just running once:
# - set CLIENT_PAYWORD_MAX_K = CLIENT_PAYMENT_COUNT
# - pick CLIENT_PAYWORD_UNIT_VALUE as "price per step"
# - keep CLIENT_CHANNEL_AMOUNT > (CLIENT_PAYMENT_COUNT * CLIENT_PAYWORD_UNIT_VALUE) if you want remainder refunded
#
# Note: CLIENT_PAYWORD_UNIT_VALUE = CLIENT_CHANNEL_AMOUNT / CLIENT_PAYMENT_COUNT is only true if you WANT
# the last payment to exactly reach the channel cap (and it divides evenly). It is not required.
export CLIENT_PAYWORD_UNIT_VALUE=1

# PayWord step cap (channel commitment). Optional convenience:
# - if unset, the client runner defaults it to CLIENT_PAYMENT_COUNT for this run
# - set explicitly if you want a channel with capacity beyond this run
export CLIENT_PAYWORD_MAX_K="$CLIENT_PAYMENT_COUNT"

export CLIENT_RAMP_DELAY_SEC=5