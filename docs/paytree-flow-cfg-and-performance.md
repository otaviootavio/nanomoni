# PayTree Flow Simulation: CFG and Performance Analysis

This document describes the control flow of **standard** vs **first-opt** PayTree (receive payment + settle) and a performance analysis based on that flow. No code—conceptual only.

---

## 1. Receive Payment — Standard Flow (CFG)

```
receive_paytree_std_payment
    │
    ├──────────────────────────► _receive_paytree_payment_std
    │
    │   get_paytree_pruned_channel_state(channel_id)
    │       │  [Repo: GET payment_channel:{id} → _deserialize_channel (json.loads + model_validate)]
    │       ▼
    │   channel == null?
    │       ├─ yes ──► _verify_paytree_channel (HTTP issuer) ; is_first_payment = true
    │       └─ no  ──► (channel already PaytreePaymentChannel)
    │   │
    │   closed? → raise
    │   duplicate check (i <= prev_i)? → [optional] verify proof, return 200 duplicate
    │   validate i, amount
    │   verify_paytree_proof_standard(leaf, siblings, root) → raise if invalid
    │   build new_state = PaytreeState(...)
    │   │
    │   _save_paytree_payment_with_retry
    │       │
    │       ├─ is_first_payment?
    │       │   yes ──► save_channel_and_initial_paytree_state(channel, new_state)
    │       │            [Repo: channel.model_dump_json(), initial_state.model_dump_json()
    │       │             run_script(KEYS: channel, proof; ARGV: channel_json, state_json, ts, id)]
    │       │            status==1 → return
    │       │            status==0 → get_by_channel_id; is_first_payment=false; fall through to save_paytree_payment
    │       │   no  ──► (skip)
    │       │
    │       save_paytree_payment(payment_channel, new_state)
    │            [Repo: new_state.model_dump_json(); run_script(save_paytree_payment)
    │             Lua: GET channel, validate max_i/last_i, SET channel, SET paytree_proof]
    │       │
    │       status==1 → return success
    │       status==0 → return race error
    │       status==3 → return max_i error
    │       status==2 → (attempt 0) _verify_paytree_channel, retry; (attempt 1) return error
    │   │
    │   return PaytreePaymentResponseDTO
```

**Standard receive — cost summary (happy path, non–first payment):**
- **DB:** 1 GET (channel) + 1 Lua (read channel + proof key, write channel + proof).
- **Serialization:** 1× channel deserialize (in repo), 1× PaytreeState `model_dump_json` (in repo before script).
- **Payload:** Full proof (leaf + all siblings) stored at `paytree_proof:{id}`; channel JSON includes last_leaf_*.

---

## 2. Receive Payment — First-Opt Flow (CFG)

```
receive_paytree_first_opt_payment
    │
    └──────────────────────────► _receive_paytree_payment_first_opt
        │
        compute depth, root_key, subroot_index
        │
        get_channel_and_nodes(channel_id, [root_key, subroot_index])
        │   [Repo: run_script → GET channel_key, GET node1, GET node2; return (channel_json, {root_key, subroot_index})]
        ▼
        channel_json == null?
            ├─ yes ──► _verify_paytree_channel (HTTP issuer); is_first_payment = true
            │          merge_nodes({root_key: paytree_root_b64}); root_b64 from channel; subroot_b64 from nodes
            └─ no  ──► payment_channel = PaytreePaymentChannel.model_validate_json(channel_json)
                       root_b64 = nodes.get(root_key); subroot_b64 = nodes.get(subroot_index)
        │
        closed? → raise
        duplicate check (i <= prev_i)? → [optional] verify_paytree_proof_first_opt(subroot), return 200
        validate i, amount
        subroot_b64 missing? → raise
        verify_paytree_proof_first_opt(i, leaf, siblings, subroot_b64, subroot_index, depth)
        │
        _build_first_opt_node_updates(i, leaf, siblings, depth)  → updates (node_key → hash_b64)
        │
        is_first_payment? → save_channel(payment_channel)  [Repo: 1 SET payment_channel]
        │
        save_nodes_and_save_payment_channel(channel_id, updates, payment_channel.model_dump_json(), ...)
        │   [Repo: run_script — MSET node keys, ZADD index, SET payment_channel, ZADD open/closed]
        ▼
        return PaytreePaymentResponseDTO
```

**First-opt receive — cost summary (happy path, non–first payment):**
- **DB:** 1 script (GET channel + 2 node keys) + 1 script (MSET nodes + SET channel + ZADD).
- **Serialization:** 1× `model_validate_json(channel_json)` in use case; 1× `model_dump_json()` (channel) in use case before save.
- **Payload:** No full proof stored; only channel JSON + sparse nodes (path from leaf to root for this payment). Smaller proof on the wire (pruned) and in store (nodes only).

---

## 3. Settle — Standard Flow (CFG)

```
settle_channel
    │
    get_by_channel_id(channel_id)     [Repo: GET payment_channel:{id} → _deserialize_channel]
    channel missing / not Paytree / closed? → raise / return
    │
    get_paytree_state(channel_id)     [Repo: GET paytree_proof:{id} → PaytreeState.model_validate_json(raw)]
    │
    latest_state != null  (standard path)
    │
    compute cumulative_owed; validate <= channel.amount
    build settlement payload; sign; call issuer (settle_paytree_payment_channel)
    mark_closed(channel_id, amount, balance)   [Repo: GET channel, update, SET]
    ▼
    return
```

**Standard settle — cost summary:**
- **DB:** 1 GET (channel) + 1 GET (proof) + 1 GET + 1 SET (mark_closed).
- **Serialization:** Channel deserialize once; PaytreeState `model_validate_json` once. No extra dump for settle.

---

## 4. Settle — First-Opt Flow (CFG)

```
settle_channel
    │
    get_by_channel_id(channel_id)     [Repo: GET payment_channel — may have stale last_leaf_*]
    channel missing / not Paytree / closed? → raise / return
    │
    get_paytree_state(channel_id)     [Repo: GET paytree_proof:{id} → null (first-opt does not store proof)]
    │
    latest_state == null && first_opt_repo?
    │   yes ──► get_channel_and_nodes(channel_id, [root_key, root_key])
    │             [Repo: GET channel + 2 node keys]
    │           if channel_json: channel = PaytreePaymentChannel.model_validate_json(channel_json)
    │           latest_state = _rebuild_full_paytree_state_from_first_opt(channel_id, channel)
    │
    _rebuild_full_paytree_state_from_first_opt:
    │   build full_sibling_indexes, dependency_indexes, node_keys
    │   get_nodes(channel_id, node_keys)   [Repo: MGET all node keys]
    │   build node_hashes; build_node_from_dependencies for each sibling
    │   return PaytreeState(leaf, siblings_b64)
    │
    latest_state == null? → raise
    compute cumulative_owed; validate; build payload; sign; issuer.settle_paytree_payment_channel
    mark_closed(...)
    ▼
    return
```

**First-opt settle — cost summary:**
- **DB:** 1 GET (channel) + 1 GET (proof → null) + 1 get_channel_and_nodes (GET channel + 2 nodes) + 1 get_nodes(MGET ~depth nodes) + mark_closed (GET + SET).
- **Serialization:** 1× `model_validate_json(channel_json)` in use case; no PaytreeState load from store; CPU to rebuild proof from nodes (hash tree ops). No proof JSON stored on receive, so settle pays the “rebuild” cost once.

---

## 5. Performance Analysis (Simulation-Based)

### 5.1 Receive Payment (per request, happy path)

| Aspect | Standard | First-opt |
|--------|----------|-----------|
| **DB round-trips** | 2 (GET channel; Lua save) | 2 (script get channel+nodes; script save nodes+channel) |
| **Keys read** | 1 (channel) | 1 channel + 2 node keys (batched) |
| **Keys written** | 2 (channel + proof) | 1 channel + N node keys (N = path length, ~depth) + index ZADD |
| **Proof stored** | Full (leaf + full sibling list) | Sparse nodes only (path nodes); no single “proof” blob |
| **Channel JSON** | Deserialized in repo (`_deserialize_channel`); state serialized in repo | Deserialized in use case (`model_validate_json`); serialized in use case (`model_dump_json`) |
| **Payload size (proof)** | O(depth) siblings in one value | O(depth) small key/values; total similar order but no big JSON blob |
| **Duplicate/race path** | May trigger extra GET proof (model_validate_json) or get_by_channel_id | No proof fetch; nodes already in first script |

**Takeaway (receive):** Standard always persists a full proof blob and does one full proof deserialize on race (code 0/3). First-opt avoids proof blob and keeps one batched read + one batched write; serialization is one channel JSON in/out in the use case.

### 5.2 Settle (once per channel)

| Aspect | Standard | First-opt |
|--------|----------|-----------|
| **DB round-trips** | 3 (get channel, get proof, mark_closed read+write) | 4+ (get channel, get proof null, get_channel_and_nodes, get_nodes, mark_closed) |
| **Proof source** | Single GET + model_validate_json | Rebuild from get_nodes + build_node_from_dependencies (CPU + MGET) |
| **Serialization** | 1× PaytreeState.model_validate_json | 1× channel model_validate_json; no state from store; N hashes from get_nodes |

**Takeaway (settle):** Standard settle is cheaper (fewer round-trips, one proof read). First-opt settle pays for not storing the proof: extra round-trips and CPU to rebuild the full proof from the node store.

### 5.3 End-to-End (many payments, then one settle)

- **Standard:** Each payment: 1 channel read + 1 Lua (channel + full proof write). Settle: 1 channel read + 1 proof read + mark_closed. Proof size grows only by the fact that the latest proof is overwritten (same order per payment).
- **First-opt:** Each payment: 1 batched read (channel + 2 nodes), 1 batched write (nodes + channel). Node store grows with path nodes per payment (bounded by tree depth). Settle: one-time cost to rebuild proof from node store (MGET + Merkle rebuild).

So: **first-opt trades cheaper receive (no full proof blob, batched channel+nodes) for a more expensive settle (rebuild + extra reads).** The CFGs above are the exact flows used for this simulation.

---

## 6. CFG Summary Diagram (High-Level)

```
                    route selects std vs first-opt
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
   /channels/paytree/first-opt         /channels/paytree/std
              │                                   │
              ▼                                   ▼
   _receive_paytree_payment_first_opt    _receive_paytree_payment_std
   • get_channel_and_nodes (1 script)    • get_paytree_pruned_channel_state (1 GET)
   • [maybe] merge_nodes / save_channel  • [maybe] _verify_paytree_channel
   • verify proof (first-opt)            • verify proof (standard)
   • save_nodes_and_save_payment_channel • _save_paytree_payment_with_retry
     (1 script: nodes + channel)          (Lua: channel + paytree_proof)
              │                                   │
              └─────────────┬─────────────────────┘
                            ▼
                    PaytreePaymentResponseDTO

                    settle_channel
                            │
              get_by_channel_id → get_paytree_state
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
     latest_state != null          latest_state == null && first_opt?
     (standard)                    (first-opt)
              │                           │
              │                   get_channel_and_nodes
              │                   model_validate_json(channel_json)
              │                   _rebuild_full_paytree_state_from_first_opt
              │                     • get_nodes(node_keys)
              │                     • build PaytreeState in memory
              │                           │
              └─────────────┬─────────────┘
                            ▼
              issuer.settle_paytree_payment_channel
              mark_closed
```

---

## 7. Cross-Check: Flamegraph vs CFG (Receive Payment)

Cross-referencing the Pyroscope flamegraph with the receive-payment CFGs to pin bottlenecks to specific control-flow steps.

### 7.1 Standard flow: flamegraph → CFG

| Flamegraph frame | Approx. CPU | CFG step (Section 1) | Notes |
|-----------------|-------------|----------------------|--------|
| **`_receive_paytree_payment_std`** | ~5.98 min | Entire standard receive path | Root of standard flow. |
| **`get_paytree_pruned_channel_state`** + **`deseri_get`** | ~1.63 min (deseri_get) | **get_paytree_pruned_channel_state** → Repo: GET + _deserialize_channel | CFG: “GET payment_channel:{id} → _deserialize_channel (json.loads + model_validate)”. Flamegraph shows both the GET (execute_command/read) and deserialization; cost is I/O + `model_validate`/JSON parse. |
| **`verify_paytree_proof`** (hash_byt, b64_to, b64de, verify_proo, combine_c) | Large (visually dominant) | **verify_paytree_proof_standard(...)** | CFG: “verify_paytree_proof_standard(leaf, siblings, root) → raise if invalid”. Crypto (hashing, b64, combine) is the main **CPU bottleneck** in the standard path; not I/O. |
| **`_save_paytree_payment`** → **`mode_run_script`** | ~2.11 min (save), ~1.75 min (script) | **_save_paytree_payment_with_retry** → **save_paytree_payment** → Repo: model_dump_json + run_script | CFG: “save_paytree_payment … [Repo: new_state.model_dump_json(); run_script(save_paytree_payment)]”. Flamegraph confirms: serialization + Lua round-trip (execute_command, read) dominate this branch. |

**Standard bottlenecks (confirmed by CFG):**

1. **Crypto: `verify_paytree_proof_standard`** — Single CFG step, but it’s the widest CPU consumer. Full proof verification (full path to root) every request. Target: reduce work per proof (e.g. pruned verification) or optimize hash/b64.
2. **I/O + deserialize: `get_paytree_pruned_channel_state`** — One GET plus `_deserialize_channel` in the CFG; matches `deseri_get` + GET. Target: smaller channel payload or fewer GETs (e.g. cache).
3. **I/O + serialize: `save_paytree_payment`** — One Lua script in the CFG; matches `run_script`/execute_command. Target: script efficiency, smaller ARGV (e.g. avoid sending full proof if Lua can derive), or batching.

---

### 7.2 First-opt flow: flamegraph → CFG

| Flamegraph frame | Approx. CPU | CFG step (Section 2) | Notes |
|-----------------|-------------|----------------------|--------|
| **`_receive_paytree_payment_first_opt`** | ~5.93 min | Entire first-opt receive path | Root of first-opt flow. |
| **`get_channel_and_nodes`** → run_script, execute_command, read | ~2.38 min | **get_channel_and_nodes(channel_id, [root_key, subroot_index])** | CFG: “[Repo: run_script → GET channel_key, GET node1, GET node2]”. Flamegraph shows this single script is a major cost; I/O (read/parse) dominates, not the use-case logic. |
| **`model_mode_save_nodes_and_save_payment_verify`** (run_script 1.63 min) | Significant | **save_nodes_and_save_payment_channel** (and possibly **verify_paytree_proof_first_opt** if label is merged) | CFG: “save_nodes_and_save_payment_channel … [Repo: run_script — MSET node keys, ZADD index, SET payment_channel]”. The run_script subtree matches the CFG write step; serialization (model_dump_json) happens in use case just before this. |

**First-opt bottlenecks (confirmed by CFG):**

1. **I/O: `get_channel_and_nodes`** — First CFG step after “compute depth, root_key, subroot_index”. One script = GET channel + 2 GETs for nodes. Flamegraph shows this script (run_script → execute_command → read) is the largest single cost in first-opt. Target: reduce round-trips (e.g. pipeline with later write), smaller values, or faster store.
2. **I/O: `save_nodes_and_save_payment_channel`** — Second script in the CFG (MSET + ZADD + SET channel). Flamegraph shows another heavy run_script/execute_command/read block. Target: script design (fewer keys, smaller channel JSON), or batching with other ops.

First-opt does **not** show a dominant crypto block like standard’s `verify_paytree_proof`; CFG has **verify_paytree_proof_first_opt** (pruned proof to subroot only), which is cheaper and appears as a smaller part of the first-opt bar.

---

### 7.3 CFG vs flamegraph alignment

- **Standard:** CFG’s three main cost centres (get pruned state, verify proof, save payment) each have a clear flamegraph counterpart. Order of cost: verify (crypto) and save (I/O) dominate; get + deseri next.
- **First-opt:** CFG’s two script steps (get_channel_and_nodes, save_nodes_and_save_payment_channel) match the two big run_script-heavy blocks. No separate large “deseri” frame because channel is deserialized once in the use case (`model_validate_json`) and is cheap relative to the scripts.
- **Both flows:** Total CPU time is similar (~6 min each). Standard spends more in **crypto** (verify_paytree_proof); first-opt spends more in **script I/O** (get_channel_and_nodes + save_nodes_and_save_payment_channel). The CFG makes clear: standard does one GET + one Lua save but pays for full proof verification; first-opt does two scripts (read then write) but only pruned verification.

---

### 7.4 Bottleneck summary (for optimization)

| Bottleneck | Flow | CFG step | Suggested focus |
|------------|------|----------|------------------|
| **verify_paytree_proof** (crypto) | Standard | verify_paytree_proof_standard | Pruned verification, faster hash/b64, or fewer siblings. |
| **get_channel_and_nodes** (script + read) | First-opt | get_channel_and_nodes | Fewer round-trips, pipeline, or smaller channel/node payloads. |
| **save_paytree_payment** / **save_nodes_and_save_payment_channel** (script) | Both | save_paytree_payment (std); save_nodes_and_save_payment_channel (first-opt) | Lua script efficiency; smaller ARGV; avoid redundant SETs. |
| **deseri_get** (GET + deserialize) | Standard | get_paytree_pruned_channel_state → _deserialize_channel | Smaller channel representation; or cache so this path is cold. |

---

## 8. Low-Hanging Fruits for Performance (Systematic)

Prioritized by **effort (low first)** and **impact**, aligned with the CFG + flamegraph bottlenecks.

### 8.1 High impact, low effort

| # | Bottleneck (flow) | CFG step | Change | Why it helps |
|---|-------------------|----------|--------|--------------|
| **1** | `get_channel_and_nodes` (first-opt) | get_channel_and_nodes | **Replace Lua script with a single MGET.** The script only does `GET KEYS[1]`, `GET KEYS[3]`, `GET KEYS[4]` and returns the three values. Use `store.mget([channel_key, node_key_1, node_key_2])` and map results to `(channel_json, {read_keys[0]: v1, read_keys[1]: v2})`. Remove the script call and the need to pass 4 KEYS (script currently receives index_key but does not use it). | Removes script dispatch and one full round-trip’s worth of Lua overhead; MGET is a single Redis command. Directly targets the ~2.38 min `get_channel_and_nodes` hotspot. |
| **2** | `verify_paytree_proof` (standard) | verify_paytree_proof_standard | **Decode b64 once and pass bytes through.** In `verify_paytree_proof_standard` (and shared `verify_proof_with_leaf_hash`), decode `leaf_b64`, `siblings_b64[]`, and `root_b64` once at the boundary; pass `leaf_hash`, `siblings: list[bytes]`, `known_node` into the protocol/crypto layer. Avoid re-decoding or building extra lists in the hot loop. | Cuts repeated b64 decode and list allocations in the widest CPU hotspot (crypto). |
| **3** | `deseri_get` (standard) | get_paytree_pruned_channel_state → _deserialize_channel | **Use a faster JSON parser for channel deserialize.** In `PaymentChannelRepositoryBaseImpl._deserialize_channel`, replace `json.loads(raw)` with `orjson.loads(raw)` (add `orjson` if not present), then keep `PaywordPaymentChannel.model_validate(data)` etc. so the rest of the pipeline is unchanged. | Reduces CPU in the 1.63 min deserialize path; orjson is typically 2–5× faster than stdlib json for parse. |

### 8.2 Medium impact, low effort

| # | Bottleneck (flow) | CFG step | Change | Why it helps |
|---|-------------------|----------|--------|--------------|
| **4** | Save scripts (both) | save_paytree_payment; save_nodes_and_save_payment_channel | **Shrink payloads sent to Redis.** (a) Standard: when building `payload_json` for `save_paytree_payment`, ensure no redundant or debug-only fields in `PaytreeState` (already minimal). (b) First-opt: when calling `save_nodes_and_save_payment_channel`, use `model_dump_json(exclude=...)` to drop any field not needed for later reads (e.g. optional metadata). Reduces ARGV size and network. | Smaller ARGV → less network and less Lua string handling; helps both script-heavy paths. |
| **5** | Verify (standard) | verify_paytree_proof_standard | **Reuse a single hasher in the verify loop.** In `merkle_tree.verify_proof_to_known_node`, instead of `hash_bytes(left+right)` (new hashlib each call), use one `hashlib.sha256()` and call `h.update(left); h.update(right); current = h.digest()` (and reset for next level). Reduces allocation in the tight loop. | Fewer allocations in the crypto hot path; small but easy win. |
| **6** | Channel JSON (standard) | get_paytree_pruned_channel_state; save_paytree_payment Lua | **Avoid double channel read in Lua when possible.** The app does GET channel (get_paytree_pruned_channel_state) and later the save script does GET channel again inside Lua. We cannot remove the app GET (needed for root_b64 and verification). We can ensure the Lua script does not do redundant work: e.g. it already uses the in-memory decoded channel for validation and only writes back the updated channel; no change needed unless you introduce a “conditional GET” script. Document that the two GETs are intentional (app for business logic, Lua for atomicity). Alternatively, if the vendor could pass channel_json as ARGV and script only does SET proof + SET channel from ARGV (no GET), that would be one GET in app and one EVALSHA with no GET in Lua—but then the script must trust ARGV and duplicate-check would need to be in app or script would need to accept overwrite semantics. Mark as “review only” unless you refactor. | Clarifies cost; a refactor to “single GET + script with channel in ARGV” could remove one GET but is higher effort. |

### 8.3 Lower impact or medium effort

| # | Area | Change | Why it helps |
|---|------|--------|--------------|
| **7** | Redis connections (both) | **Reuse one connection per request for the receive path.** Today each `get`/`mget`/`run_script` does `async with self._db_client.get_connection() as conn`. For a single receive we do 1–2 operations. Using a request-scoped connection (e.g. dependency that yields one conn for the whole request and repositories use it) avoids multiple pool acquisitions. | Slight reduction in pool contention and connection churn; effect depends on pool size and load. |
| **8** | Serialization (standard) | **Use orjson for PaytreeState in the repo.** Where the repo does `PaytreeState.model_validate_json(raw)` and `new_state.model_dump_json()`, Pydantic v2 can use a custom serializer; or use `orjson.loads(raw)` + `PaytreeState.model_validate(data)` and `orjson.dumps(new_state.model_dump(mode='json'))` (with datetime handling) so proof (de)serialization is faster. | Targets the proof blob size and decode cost on read/race path; medium effort due to datetime and mode. |
| **9** | First-opt save script | **Keep first-opt save script but ensure minimal KEYS/ARGV.** Script already does MSET + ZADD + SET channel; avoid adding more keys or large temporary structures in Lua. No code change if already minimal; add a one-line comment that this script is hot. | Prevents future bloat; no immediate gain. |

### 8.4 Checklist (implementation order)

1. **[ ] First-opt: MGET instead of script for get_channel_and_nodes** — Implement in `PaytreeFirstOptNodeRepositoryImpl.get_channel_and_nodes`: build `keys = [channel_key, _node_key(channel_id, read_keys[0]), _node_key(channel_id, read_keys[1])]` (pad if needed), call `values = await self._store.mget(keys)`, return `(values[0] or None, {read_keys[0]: values[1] or '', read_keys[1]: values[2] or ''})`. Remove or stop using the `paytree_first_opt_get_channel_and_nodes` script for this path.
2. **[ ] Standard: orjson in _deserialize_channel** — In `payment_channel_repository_base_impl.py`, use `orjson.loads(raw)` and handle errors; keep `model_validate(data)`.
3. **[ ] Standard: bytes-through in verify** — In `paytree_proof.verify_paytree_proof_standard` and the protocol layer, decode b64 once at entry and pass bytes into `verify_proof_with_leaf_hash` / `verify_proof_to_known_node`.
4. **[ ] Merkle: reuse hasher in verify_proof_to_known_node** — In `merkle_tree.verify_proof_to_known_node`, use one SHA-256 instance per verification and update/digest per level.
5. **[ ] Payload: exclude optional fields in first-opt channel dump** — In the use case, when calling `save_nodes_and_save_payment_channel`, pass `payment_channel.model_dump_json(exclude=...)` after identifying any field not required for settlement or later reads.

### 8.5 Out of scope (not low-hanging)

- **Switching standard to “store nodes only” (like first-opt)** — Architectural change; avoids full proof blob but requires rebuild on settle and more complex code paths.
- **Moving verification to Lua** — Would require passing hashes and logic into Redis; high effort and not typical.
- **Compressing proof/channel in Redis** — Would need app and possibly Lua changes; medium effort for uncertain gain unless payloads are very large.

This completes the flow simulation and performance analysis driven by the CFGs above.
