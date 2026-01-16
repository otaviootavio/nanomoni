sleep 30

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="signature"
docker compose up client

sleep 30

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="payword"
docker compose up client

sleep 30

source envs/client.env.sh
export CLIENT_PAYMENT_MODE="paytree"
docker compose up client