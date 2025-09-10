#!/bin/bash
. ./envs/env.client.sh

sleep 10

for i in $(seq 1 10); do
    poetry run python -m src.nanomoni.client_main &
done

for job in $(jobs -p); do
    wait "$job"
done

echo "All 10 client runs completed." 