"""Per-mode CPU-time taxonomy: which flamebearer function names constitute the
"endpoint" (macro, whole-request) span vs. the "crypto"/"db read"/"db
write"/"serialize" (micro) spans for each payment mode.

Datastore time is measured at the ``KeyValueStore`` primitives rather than at
the repository entry points, so it contains only the datastore work itself
(connection checkout, redis-py command encoding, socket I/O, reply parsing).
That makes the buckets identical across modes by construction and removes any
need to subtract nested marshalling from them: ``infrastructure/storage.py``
imports no ``json``, so no ``serialize`` name can ever be a descendant of a
primitive, and the buckets are disjoint. The repository's own Python (key
f-strings, result dicts, reference parsing) lands in ``other``.

The read/write split falls out of the primitives themselves, with no name
overlap to resolve: every payment-path read is an ``mget`` (channel + state,
or the merkle nodes), and every payment-path write is a Lua script run through
``run_script`` (``save_payment``, ``merkle_merge_nodes``,
``save_channel_and_initial_state``), because writes must be atomic against a
concurrent payment on the same channel. Reads and writes cost differently --
a write ships the serialized payload up and executes Lua server-side, a read
ships keys up and parses the reply -- so charging them to one bucket hid which
half of the datastore cost a scheme actually moves.

``get`` is deliberately *not* a primitive here: the bare name collides with
``httpx.AsyncClient.get``, which the issuer-fetch path calls inside the same
endpoint span, and the two repository reads that use ``store.get`` (the
duplicate/race branches) draw zero samples in a steady-state run.

Function names are verified verbatim against a live Pyroscope trace of the
vendor service (see profiling/aggregate.py docstring). ``verify`` is reused
across the three paytree variants and payword: each mode's crypto scheme class
defines its own ``verify`` method, but since extraction is scoped to one run's
time window (one mode exercised per run), the bare name is unambiguous.
``mget`` names both our store method and redis-py's; only the outermost
occurrence is counted, so the inner frame is not double-counted.

Serialize lists use leaf-level names only (no ancestor/descendant pairs in the
same list) so ``sum_ticks_within`` does not double-count. Pydantic v2 marshals
in its Rust core, so ``model_*`` frames never call Python ``json.dumps``/
``json.loads``.
"""

from __future__ import annotations

from typing import Dict, List, TypedDict


class ModeFunctions(TypedDict):
    endpoint: str
    crypto: List[str]
    db_read: List[str]
    db_write: List[str]
    serialize: List[str]


# Every datastore round trip on every payment path goes through one of these
# two KeyValueStore methods, so both db buckets are mode-independent.
STORE_READS: List[str] = ["mget"]
STORE_WRITES: List[str] = ["run_script"]


# "paytree" is the paytree-std mode name, matching sweep/aggregate.py's
# _KNOWN_MODES convention.
MODE_FUNCTIONS: Dict[str, ModeFunctions] = {
    "signature": {
        "endpoint": "receive_payment",
        "crypto": ["verify_signature_bytes"],
        "db_read": STORE_READS,
        "db_write": STORE_WRITES,
        "serialize": [
            "model_dump_json",
            "model_validate_json",
            "model_validate",
            "loads",
        ],
    },
    "paytree": {
        "endpoint": "receive_paytree_std_payment",
        "crypto": ["verify"],
        "db_read": STORE_READS,
        "db_write": STORE_WRITES,
        "serialize": [
            "model_dump_json",
            "model_validate_json",
            "model_validate",
            "loads",
            "dumps",
        ],
    },
    "paytree_first_opt": {
        "endpoint": "receive_paytree_first_opt_payment",
        "crypto": ["verify"],
        "db_read": STORE_READS,
        "db_write": STORE_WRITES,
        "serialize": ["model_dump_json", "model_validate_json", "dumps"],
    },
    "paytree_child_pair": {
        "endpoint": "receive_paytree_child_pair_payment",
        "crypto": ["verify"],
        "db_read": STORE_READS,
        "db_write": STORE_WRITES,
        "serialize": ["model_dump_json", "model_validate_json", "dumps"],
    },
    "payword": {
        "endpoint": "receive_payword_payment",
        "crypto": ["verify"],
        "db_read": STORE_READS,
        "db_write": STORE_WRITES,
        "serialize": [
            "model_dump_json",
            "model_validate_json",
            "model_validate",
            "loads",
            "dumps",
        ],
    },
}

RUN_ENDPOINT_FUNCTION = "run_endpoint_function"

VENDOR_PROFILE_QUERY = (
    'process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="/nanomoni-vendor-1"}'
)
