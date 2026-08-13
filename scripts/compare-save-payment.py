"""Isolate the vendor's repository-call cost from everything around it.

The profiler comparisons in the plotter (``profile_macro_micro.png``) show
``signature``'s ``db`` bucket (``get_by_channel_id`` + ``save_channel_and_initial_payment``
+ ``save_payment``) running higher than ``paytree``/``payword``'s
(``get_channel_and_state`` + ``save_payment``). This script removes every other
layer (HTTP, ASGI, FastAPI DI,
crypto) and calls each repository's read and write methods directly, back-to-back,
against the same local Redis the vendor uses, timing each call with
``time.process_time()`` (CPU time only -- excludes the idle wait while the event
loop is blocked on the socket).

Result: once the harness builds each mode's write payload with comparable,
precomputed fixtures, ``signature``'s ``save_payment`` is NOT more expensive
than ``paytree``/``payword``'s -- all three land in the same ~0.17-0.23ms band,
with ``signature`` often the cheapest. An earlier version of this script showed
a real-looking 2x gap that turned out to be a harness bug: it generated a fresh
ECDSA keypair and signature *inside* the timed region to build a "realistic"
``client_signature_b64`` for signature-mode writes, while the unified path's
proof fixture was cheap string formatting -- so it was timing key generation,
not the repository. ``save_payment`` never signs anything (the client signs;
the vendor only persists an already-signed statement), so this build precomputes
the signature once, outside every timed loop. This means the elevated ``db``
bucket seen in Pyroscope for ``signature`` is not explained by its repository
code being inherently slower -- it points elsewhere (profiler sampling/attribution,
or CPU contention from ECDSA verification saturating the core harder under load).

Usage:

    poetry run python scripts/compare-save-payment.py [iterations] [order]

``order`` is a string of "s"/"p"/"q" (signature/payword/paytree) controlling
which mode runs first, to check results aren't an artifact of warmup/cache
ordering (default "spq").

Requires ``redis-vendor`` reachable at ``redis://localhost:6379/0`` (published
by docker-compose) and its Lua scripts registerable (any redis-vendor works,
scripts are loaded fresh here).
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Coroutine, List

from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.crypto.certificates import sign_bytes, json_to_bytes
from nanomoni.domain.shared.crypto_proof import CryptoProof
from nanomoni.domain.shared.proof_reference import PaymentScheme
from nanomoni.domain.vendor.entities import (
    PaymentChannel,
    PaymentState,
    SignaturePaymentChannel,
    SignatureState,
)
from nanomoni.infrastructure.database import DatabaseClient
from nanomoni.infrastructure.scripts import VENDOR_SCRIPTS
from nanomoni.infrastructure.storage import RedisKeyValueStore
from nanomoni.infrastructure.vendor.payment_repository_impl import (
    PaymentRepositoryImpl,
)
from nanomoni.infrastructure.vendor.signature_repository_impl import (
    SignatureRepositoryImpl,
)

DATABASE_URL = "redis://localhost:6379/0"
WARMUP_ITERS = 50


@dataclass
class Settings:
    database_url: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _register_scripts(store: RedisKeyValueStore) -> None:
    for name, script in VENDOR_SCRIPTS.items():
        await store.register_script(name, script)


async def _time_calls(fn: Callable[[], Coroutine], iterations: int) -> List[float]:
    """Run ``fn`` ``iterations`` times, returning per-call CPU seconds.

    ``time.process_time()`` only advances while this process is actually on
    CPU -- awaiting the Redis socket doesn't count -- so it isolates the same
    thing the Pyroscope ``process_cpu`` profile was measuring, without the
    profiler's own sampling quantization.
    """
    for _ in range(WARMUP_ITERS):
        await fn()
    samples: List[float] = []
    for _ in range(iterations):
        start = time.process_time()
        await fn()
        samples.append(time.process_time() - start)
    return samples


def _report(label: str, samples: List[float]) -> None:
    ms = [s * 1000.0 for s in samples]
    ms_sorted = sorted(ms)
    n = len(ms_sorted)
    p50 = ms_sorted[n // 2]
    p95 = ms_sorted[min(n - 1, int(n * 0.95))]
    print(
        f"  {label:34s} mean={statistics.mean(ms):7.4f}ms  "
        f"median={p50:7.4f}ms  p95={p95:7.4f}ms  "
        f"stdev={statistics.pstdev(ms):7.4f}ms  total={sum(ms):8.2f}ms  n={n}"
    )


def _make_ecdsa_signature_b64() -> str:
    """A real ECDSA P-256 signature over a realistic payload, for a realistic length.

    Computed once, outside any timed loop: ``save_payment`` never signs anything
    (the client signs; the vendor only persists an already-signed statement), so
    generating a fresh signature per write would be timing the harness's own
    fixture setup, not the repository call under test.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    payload = json_to_bytes({"channel_id": str(uuid.uuid4()), "cumulative_owed_amount": 12345})
    return sign_bytes(key, payload)


async def bench_signature(iterations: int) -> None:
    db_client = DatabaseClient(Settings(database_url=DATABASE_URL))
    store = RedisKeyValueStore(db_client)
    await _register_scripts(store)
    repo = SignatureRepositoryImpl(store)

    channel_id = f"bench-signature-{uuid.uuid4()}"
    channel = SignaturePaymentChannel(
        channel_id=channel_id,
        client_public_key_der_b64="X" * 120,
        vendor_public_key_der_b64="Y" * 120,
        salt_b64="Z" * 24,
        amount=10_000_000,
        balance=0,
        created_at=_now(),
    )
    # Real signature length, computed once: see _make_ecdsa_signature_b64 docstring.
    signature_b64 = _make_ecdsa_signature_b64()

    initial_state = SignatureState(
        channel_id=channel_id,
        cumulative_owed_amount=1,
        client_signature_b64=signature_b64,
        created_at=_now(),
    )
    status, _ = await repo.save_channel_and_initial_payment(channel, initial_state)
    assert status == 1, f"seed failed: status={status}"

    counter = {"k": 1}

    async def do_read() -> None:
        result = await repo.get_by_channel_id(channel_id)
        assert result is not None

    async def do_write() -> None:
        counter["k"] += 1
        new_state = SignatureState(
            channel_id=channel_id,
            cumulative_owed_amount=counter["k"],
            client_signature_b64=signature_b64,
            created_at=_now(),
        )
        status, _ = await repo.save_payment(channel, new_state)
        assert status == 1, f"write failed: status={status}"

    read_samples = await _time_calls(do_read, iterations)
    write_samples = await _time_calls(do_write, iterations)
    print("signature (SignatureRepositoryImpl):")
    _report("get_by_channel_id", read_samples)
    _report("save_payment", write_samples)


async def bench_unified(mode_label: str, scheme: PaymentScheme, proof_data_fn, iterations: int) -> None:
    db_client = DatabaseClient(Settings(database_url=DATABASE_URL))
    store = RedisKeyValueStore(db_client)
    await _register_scripts(store)
    repo = PaymentRepositoryImpl(store)

    channel_id = f"bench-{mode_label}-{uuid.uuid4()}"
    channel = PaymentChannel(
        channel_id=channel_id,
        client_public_key_der_b64="X" * 120,
        vendor_public_key_der_b64="Y" * 120,
        salt_b64="Z" * 24,
        amount=10_000_000,
        balance=0,
        created_at=_now(),
        commitment="C" * 44,
        scheme=scheme,
        max_steps=1_000_000,
        unit_value=1,
    )
    initial_state = PaymentState(
        channel_id=channel_id,
        proof_reference=1,
        cumulative_owed=1,
        proof_fingerprint="F" * 44,
        created_at=_now(),
    )
    initial_proof = CryptoProof(scheme=scheme, data=proof_data_fn(1))
    status, _ = await repo.save_channel_and_initial_state(channel, initial_state, initial_proof)
    assert status == 1, f"seed failed: status={status}"

    counter = {"k": 1}

    async def do_read() -> None:
        c, s = await repo.get_channel_and_state(channel_id)
        assert c is not None and s is not None

    async def do_write() -> None:
        counter["k"] += 1
        new_state = PaymentState(
            channel_id=channel_id,
            proof_reference=counter["k"],
            cumulative_owed=counter["k"],
            proof_fingerprint="F" * 44,
            created_at=_now(),
        )
        proof = CryptoProof(scheme=scheme, data=proof_data_fn(counter["k"]))
        status, _ = await repo.save_payment(channel, new_state, proof)
        assert status == 1, f"write failed: status={status}"

    read_samples = await _time_calls(do_read, iterations)
    write_samples = await _time_calls(do_write, iterations)
    print(f"{mode_label} (PaymentRepositoryImpl):")
    _report("get_channel_and_state", read_samples)
    _report("save_payment", write_samples)


def _payword_proof(_: int) -> dict:
    return {"token_b64": "T" * 44}


def _paytree_proof(_: int) -> dict:
    # ~15 siblings is what a ~30k-leaf tree (2**15) needs -- matches the depth
    # a real paytree_std run in this benchmark's size range would carry.
    return {"leaf_b64": "L" * 44, "siblings_b64": ["S" * 44 for _ in range(15)]}


async def main() -> None:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    print(f"iterations per call = {iterations} (+{WARMUP_ITERS} warmup, discarded)\n")

    # Order is deliberately varied run-to-run by the caller (or here) to rule out
    # warmup/JIT/cache artifacts biasing whichever mode runs first.
    order = sys.argv[2] if len(sys.argv) > 2 else "spq"
    benches = {
        "s": lambda: bench_signature(iterations),
        "p": lambda: bench_unified("payword", PaymentScheme.PAYWORD, _payword_proof, iterations),
        "q": lambda: bench_unified("paytree", PaymentScheme.PAYTREE, _paytree_proof, iterations),
    }
    for key in order:
        await benches[key]()
        print()


if __name__ == "__main__":
    asyncio.run(main())
