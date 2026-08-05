from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from multiprocessing import get_context

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
)
from nanomoni.client import (
    common,
    paytree,
    payword,
    signature,
)
from nanomoni.cpu_affinity import pin_to_own_core
from nanomoni.crypto.certificates import load_private_key_from_pem
from nanomoni.crypto.key_utils import compute_public_key_der_b64_from_private_pem
from nanomoni.crypto.paytree import Paytree
from nanomoni.crypto.payword import Payword
from nanomoni.envs.client_env import Settings, get_settings
from nanomoni.infrastructure.http.http_client import HttpError
from nanomoni.infrastructure.issuer.issuer_client import AsyncIssuerClient
from nanomoni.infrastructure.vendor.vendor_client_async import VendorClientAsync


PAYWORD_NOT_INITIALIZED = "PayWord object should be initialized"
PAYTREE_NOT_INITIALIZED = "PayTree object should be initialized"


async def _run_virtual_client(
    issuer: AsyncIssuerClient,
    vendor: VendorClientAsync,
    vendor_public_key_der_b64: str,
    settings: Settings,
    client_mode: common.ClientMode,
    client_private_key_pem: str,
    payment_count: int,
    channel_amount: int,
    target_tps: float,
) -> None:
    """Drive one virtual client's full lifecycle: register, open a channel,
    send its share of payments, settle, and verify its own balance.

    Every piece of per-identity state (private key, payment count, channel
    amount, target TPS) is an explicit argument so that N of these can run
    concurrently via ``asyncio.gather`` in ``run_client_flow`` without sharing
    identity/channel/counter state.
    """
    client_private_key = load_private_key_from_pem(client_private_key_pem)
    client_public_key_der_b64 = compute_public_key_der_b64_from_private_pem(
        client_private_key_pem
    )

    # Generate monotonic sequence:
    # - signature mode: these are cumulative_owed_amount values
    # - payword mode: these are k counters (cumulative_owed_amount = k * unit_value)
    payments: list[int] = list(range(1, payment_count + 1))

    # 3) Register client and capture starting balance (issuer returns existing balance).
    initial = await issuer.register(
        RegistrationRequestDTO(client_public_key_der_b64=client_public_key_der_b64)
    )
    initial_balance = initial.balance

    # 4) Open channel (client-signed envelope)
    # Initialize mode-specific commitments and compute final owed amount.
    # Commitment construction is tens of thousands of synchronous hashes. Run it
    # in a worker thread so the other virtual clients sharing this event loop
    # keep servicing their sockets; a multi-second stall here lets the server
    # close their idle keep-alive connections mid-flight.
    final_cumulative_owed_amount: int
    payword_obj: Payword | None = None
    paytree_obj: Paytree | None = None

    if client_mode == "payword":
        (
            payword_obj,
            payword_root_b64,
            payword_unit_value,
            payword_max_k,
        ) = await asyncio.to_thread(payword.init_commitment, settings, payment_count)
        final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
            client_mode, payments, payword_unit_value
        )
    elif client_mode in ("paytree", "paytree_first_opt"):
        (
            paytree_obj,
            paytree_root_b64,
            paytree_unit_value,
            paytree_max_i,
        ) = await asyncio.to_thread(paytree.init_commitment, settings, payment_count)
        final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
            client_mode, payments, paytree_unit_value
        )
    elif client_mode == "paytree_child_pair":
        (
            child_pair_tree,
            paytree_root_b64,
            paytree_unit_value,
            paytree_max_i,
        ) = await asyncio.to_thread(
            paytree.init_commitment_child_pair, settings, payment_count
        )
        paytree_obj = child_pair_tree
        # Child-pair payments are indexed by Eytzinger node k (1..max_k),
        # not by leaf index; clip the requested payment count to max_k.
        payments = list(range(1, min(payment_count, child_pair_tree.max_k) + 1))
        final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
            client_mode, payments, paytree_unit_value
        )
    else:
        final_cumulative_owed_amount = common.compute_final_cumulative_owed_amount(
            client_mode, payments
        )

    # Sign and send open channel request
    if client_mode == "payword":
        open_dto = payword.build_open_channel_request(
            client_private_key,
            client_public_key_der_b64,
            vendor_public_key_der_b64,
            channel_amount,
            payword_root_b64,
            payword_unit_value,
            payword_max_k,
        )
    elif client_mode in ("paytree", "paytree_first_opt", "paytree_child_pair"):
        open_dto = paytree.build_open_channel_request(
            client_private_key,
            client_public_key_der_b64,
            vendor_public_key_der_b64,
            channel_amount,
            paytree_root_b64,
            paytree_unit_value,
            paytree_max_i,
        )
    else:
        open_dto = signature.build_open_channel_request(
            client_private_key,
            client_public_key_der_b64,
            vendor_public_key_der_b64,
            channel_amount,
        )
    channel_id = await common.open_channel_for_mode(issuer, client_mode, open_dto)

    # Read balance after lock (issuer register is idempotent; using it as a "get balance").
    after_open = await issuer.register(
        RegistrationRequestDTO(client_public_key_der_b64=client_public_key_der_b64)
    )
    balance_after_open = after_open.balance

    # 5) Payments
    delay = 1.0 / target_tps if target_tps > 0 else 0.0

    if client_mode == "signature":
        # One ECDSA signature per payment, so this blocks for seconds at
        # benchmark payment counts; keep it off the shared event loop.
        payment_dtos = await asyncio.to_thread(
            signature.prepare_payments,
            channel_id,
            client_public_key_der_b64,
            vendor_public_key_der_b64,
            client_private_key,
            payments,
        )
        await signature.send_payments(
            vendor, channel_id, payment_dtos, inter_payment_delay=delay
        )
    elif client_mode == "payword":
        if payword_obj is None:
            raise RuntimeError(PAYWORD_NOT_INITIALIZED)
        # Type narrowing: mypy now knows payword_obj is not None after the check
        payword_for_payments: Payword = payword_obj
        await payword.send_payments(
            vendor,
            channel_id,
            payword_for_payments,
            payments,
            inter_payment_delay=delay,
        )
    elif client_mode == "paytree":
        if paytree_obj is None:
            raise RuntimeError(PAYTREE_NOT_INITIALIZED)
        paytree_for_payments = paytree_obj
        await paytree.send_std_payments(
            vendor,
            channel_id,
            paytree_for_payments,
            payments,
            inter_payment_delay=delay,
        )
    elif client_mode == "paytree_first_opt":
        if paytree_obj is None:
            raise RuntimeError(PAYTREE_NOT_INITIALIZED)
        paytree_for_payments = paytree_obj
        await paytree.send_first_opt_payments(
            vendor,
            channel_id,
            paytree_for_payments,
            payments,
            inter_payment_delay=delay,
        )
    elif client_mode == "paytree_child_pair":
        if paytree_obj is None:
            raise RuntimeError(PAYTREE_NOT_INITIALIZED)
        paytree_for_payments = paytree_obj
        await paytree.send_child_pair_payments(
            vendor,
            channel_id,
            paytree_for_payments,
            payments,
            inter_payment_delay=delay,
        )
    else:
        raise RuntimeError(f"Unsupported client mode: {client_mode}")

    # 6) Closure request (vendor will call issuer settlement)
    await common.request_settle_for_mode(vendor, client_mode, channel_id)

    # Wait until issuer marks the channel closed.
    await common.wait_until_closed(issuer, client_mode, channel_id)

    # 7) Assertion: client received remainder back on settlement.
    # Expected:
    # - After open: initial - channel_amount
    # - After close: initial - final_cumulative_owed_amount
    final = await issuer.register(
        RegistrationRequestDTO(client_public_key_der_b64=client_public_key_der_b64)
    )
    final_balance = final.balance

    expected_after_open = initial_balance - channel_amount
    expected_final = initial_balance - final_cumulative_owed_amount
    expected_remainder = channel_amount - final_cumulative_owed_amount

    assert balance_after_open == expected_after_open, (
        f"Unexpected balance after open. got={balance_after_open}, "
        f"expected={expected_after_open}"
    )
    assert expected_remainder > 0, "Channel amount must exceed final owed amount"
    assert final_balance == expected_final, (
        f"Unexpected final client balance. got={final_balance}, expected={expected_final}"
    )
    assert final_balance - balance_after_open == expected_remainder, (
        "Client did not receive remainder back as expected. "
        f"got_delta={final_balance - balance_after_open}, expected_delta={expected_remainder}"
    )


async def run_client_flow(shard_index: int = 0, shard_count: int = 1) -> None:
    """
    Minimal client runner.

    This is intended to be executed inside Docker (or locally) to:
    - Register the client into the issuer
    - Open a payment channel to the vendor
    - Send a configurable sequence of off-chain payments to the vendor
    - Optionally request channel closure from the vendor

    Fans out across one virtual client per entry in
    ``settings.client_private_key_pems`` (own keypair + channel + payment loop
    each), driven concurrently in-process via ``asyncio.gather``. With a
    single key, this reproduces the single-identity behavior exactly.

    ``shard_index``/``shard_count`` take only every Nth key, so several processes
    can split the same key list (see ``main``). Per-key payment count and target
    TPS stay derived from the *full* list, which keeps the totals a run delivers
    identical no matter how many processes it is spread over.
    """
    settings = get_settings()
    client_mode = common.validate_mode(settings.client_payment_mode)
    all_client_keys = settings.client_private_key_pems
    n = len(all_client_keys)
    # Position in the full key list, not in this shard: it decides which vendor
    # worker the client talks to, and only a global index spreads clients evenly
    # across workers when several processes each take a slice.
    client_entries = list(enumerate(all_client_keys))[shard_index::shard_count]
    if not client_entries:
        return

    if settings.client_payment_count % n != 0:
        raise RuntimeError(
            "CLIENT_PAYMENT_COUNT must be evenly divisible by the number of "
            "keys in CLIENT_PRIVATE_KEY_PEMS"
        )
    per_client_count = settings.client_payment_count // n
    per_client_target_tps = (
        settings.client_target_tps / n if settings.client_target_tps > 0 else 0.0
    )

    async with (
        AsyncIssuerClient(settings.issuer_base_url) as issuer,
        VendorClientAsync(settings.vendor_base_url) as bootstrap_vendor,
    ):
        # 1) Fetch vendor public key (required for opening channel + addressing payments)
        vendor_pk = await bootstrap_vendor.get_vendor_public_key()

        # 2) Ensure vendor is registered (idempotent in practice)
        try:
            await issuer.register(
                RegistrationRequestDTO(
                    client_public_key_der_b64=vendor_pk.public_key_der_b64
                )
            )
        except HttpError:
            # Vendor may already be registered; ignore 4xx/5xx here to keep runner minimal.
            pass

        # One dedicated vendor connection per virtual client, aimed at the port of
        # the worker this client belongs to. A keep-alive connection is served end
        # to end by the worker that accepted it, so a pool capped at one
        # connection keeps every payment of a channel on that worker; sharing one
        # pool would instead hand consecutive payments to whichever connection
        # happened to be free.
        async with AsyncExitStack() as stack:
            vendors = [
                await stack.enter_async_context(
                    VendorClientAsync(
                        common.vendor_url_for_worker(
                            settings.vendor_base_url,
                            index,
                            settings.client_vendor_port_count,
                        ),
                        connection_limit=1,
                    )
                )
                for index, _ in client_entries
            ]
            await asyncio.gather(
                *(
                    _run_virtual_client(
                        issuer,
                        own_vendor,
                        vendor_pk.public_key_der_b64,
                        settings,
                        client_mode,
                        key_pem,
                        per_client_count,
                        settings.client_channel_amount,
                        per_client_target_tps,
                    )
                    for own_vendor, (_, key_pem) in zip(vendors, client_entries)
                )
            )


def _run_shard(shard_index: int, shard_count: int) -> None:
    settings = get_settings()
    if settings.client_pin_processes_to_cores:
        pin_to_own_core(label=f"client shard {shard_index}")
    asyncio.run(run_client_flow(shard_index, shard_count))


def main() -> None:
    shard_count = get_settings().client_processes
    if shard_count == 1:
        _run_shard(0, 1)
        return

    # Virtual clients share one event loop and one GIL, so a client asked to
    # drive more TPS than a single core can produce needs more processes, not
    # more virtual clients. Keys are dealt round-robin, so shards differ by at
    # most one client when the count does not divide evenly.
    ctx = get_context("fork")
    procs = [
        ctx.Process(target=_run_shard, args=(i, shard_count), name=f"client-shard-{i}")
        for i in range(shard_count)
    ]
    for proc in procs:
        proc.start()

    failures = []
    for proc in procs:
        proc.join()
        if proc.exitcode != 0:
            failures.append(f"{proc.name} exited with {proc.exitcode}")
    if failures:
        raise SystemExit("; ".join(failures))


if __name__ == "__main__":
    main()
