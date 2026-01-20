"""Stress story: open+max-pay+close PayWord channels at scale.

Objective:
  Send many unique clients that:
    - register with issuer
    - open a PayWord channel
    - make the maximum payment (k = max_k)
    - close the channel (vendor -> issuer settlement)

This forces vendor/issuer to verify PayWord tokens, which is O(k) hashing per channel.

Run (example):
  NANOMONI_STRESS_CLIENTS=5000 NANOMONI_STRESS_CONCURRENCY=50 pytest -m stress -k payword_attack
"""

from __future__ import annotations

import asyncio
import os
import time
import hashlib

import pytest

from nanomoni.crypto.payword import bytes_to_b64, hash_n
from tests.e2e.helpers.client_actor import ClientActor
from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return int(val)


@pytest.mark.asyncio
@pytest.mark.stress
async def test_open_close_payword_attack_5000_clients_max_k_1_000_000(
    require_services: None,  # pytest fixture - ensures services are available
    issuer_client: IssuerTestClient,
    vendor_client: VendorTestClient,
) -> None:
    clients_n = _env_int("NANOMONI_STRESS_CLIENTS", 5000)
    concurrency = _env_int("NANOMONI_STRESS_CONCURRENCY", 4)
    max_k = _env_int("NANOMONI_STRESS_MAX_K", 10_000_00)

    if clients_n <= 0:
        raise ValueError("NANOMONI_STRESS_CLIENTS must be > 0")
    if concurrency <= 0:
        raise ValueError("NANOMONI_STRESS_CONCURRENCY must be > 0")
    if max_k <= 0:
        raise ValueError("NANOMONI_STRESS_MAX_K must be > 0")

    # Shared commitment: computing H^max_k(seed) is O(max_k) once.
    # Token for k=max_k is the seed itself, so clients don't need to hash locally.
    seed = hashlib.sha256(b"nanomoni-stress-payword-seed").digest()
    payword_root_b64 = bytes_to_b64(hash_n(seed, max_k))
    token_b64 = bytes_to_b64(seed)

    # Vendor public key + registration (once).
    vendor_pk_response = await vendor_client.get_public_key()
    vendor_public_key_der_b64 = vendor_pk_response.public_key_der_b64
    await issuer_client.register_account(vendor_public_key_der_b64)

    # Amount must cover max payment owed = max_k * unit_value.
    unit_value = 1
    channel_amount = max_k * unit_value

    sem = asyncio.Semaphore(concurrency)
    started = time.perf_counter()

    async def run_one() -> None:
        async with sem:
            client = ClientActor()
            await issuer_client.register_account(client.public_key_der_b64)

            open_request = client.create_open_channel_request_payword_with_root(
                vendor_public_key_der_b64,
                amount=channel_amount,
                unit_value=unit_value,
                max_k=max_k,
                payword_root_b64=payword_root_b64,
            )
            channel_response = await issuer_client.open_payword_channel(open_request)
            computed_id = channel_response.computed_id

            # Max payment (forces vendor verification ~ max_k hashes).
            await vendor_client.receive_payword_payment(
                computed_id, k=max_k, token_b64=token_b64
            )

            # Close channel (forces issuer verification again during settlement).
            await vendor_client.request_channel_closure_payword(computed_id)

    # IMPORTANT:
    # If any single client flow fails, we still need to await all in-flight tasks.
    # Otherwise pytest will tear down fixtures (closing the shared HTTP client/session)
    # while background tasks are still running, causing:
    #   RuntimeError: Cannot send a request, as the client has been closed.
    results = await asyncio.gather(
        *(run_one() for _ in range(clients_n)),
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        # Surface a useful failure while ensuring all tasks finished first.
        first = errors[0]
        raise AssertionError(
            f"{len(errors)}/{clients_n} client flows failed; first error: {first!r}"
        ) from first

    elapsed = time.perf_counter() - started
    # Minimal sanity check: the run completed; details validated by smaller e2e tests.
    assert elapsed >= 0.0
