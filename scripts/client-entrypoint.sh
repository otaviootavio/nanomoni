#!/bin/bash
. ./envs/env.client.sh

sleep 10

poetry run python -m src.nanomoni.client_main

echo "All 10 client runs completed." 