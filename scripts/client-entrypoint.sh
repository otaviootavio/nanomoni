#!/bin/bash
. ./envs/env.client.sh

# Run 8 instances of the client in parallel
for i in $(seq 1 16); do
  poetry run python -m src.nanomoni.client_pay_chan &
done

wait