# Standard vs First-Opt: Query and Performance Analysis

This document analyses how the **standard** and **first-optimization** PayTree payment flows work, whether they are equivalent, what changes, and why their performance differs (with reference to the flame graph).

---

## 1. Entry point (shared)

Both flows use the same entry:

- **`receive_paytree_payment(channel_id, dto)`** in `src/nanomoni/application/vendor/use_cases/paytree_payment.py`.

Steps shared by both:

1. **`get_paytree_pruned_channel_state(channel_id)`**  
   - **Query:** single `GET payment_channel:{channel_id}`.  
   - **Code:** `PaytreeRepositoryImpl.get_paytree_pruned_channel_state` → `store.get(channel_key)` then `_deserialize_channel(channel_json)`.  
   - **Flame graph:** appears as a large cost (~5 s) in both paths (`get_paytree_pruned_channel_state` → `_deseri get` + `execute_command` + read/parse). Same cost for standard and first-opt.

2. If channel is missing → **`_verify_paytree_channel(channel_id)`** (HTTP to issuer).

3. Duplicate check (same logic): `prev_i`, `prev_leaf` from channel; `check_duplicate_paytree_payment_by_leaf(i, leaf, prev_i, prev_leaf)` (in-memory).

4. Branch on **`payment_channel.paytree_optimization_type`**:
   - **1** → first-opt flow (`_receive_paytree_payment_first_opt`).
   - **0** (or else) → standard flow (full proof + `PaytreeState`).

So the **first store access is the same** in both: one pruned channel fetch. The difference is what happens after the branch.

---

## 2. Standard flow (optimization_type = 0)

**Goal:** Persist **full proof** as `PaytreeState` and keep channel metadata in sync, with atomic scripts.

### Queries and operations

| Step | Operation | What runs |
|------|------------|-----------|
| 1 | (already done) | `get_paytree_pruned_channel_state` → 1× `GET` |
| 2 | Duplicate / verify | In-memory: `verify_paytree_proof_standard(i, leaf_b64, siblings_b64, root_b64, max_i)`. |
| 3 | Save | **`_save_paytree_payment_with_retry`** → either: |
| 3a | First payment | **`save_channel_and_initial_paytree_state(channel, initial_state)`** → **`run_script("save_channel_and_initial_paytree_pruned_state", …)`** (Lua). Writes `payment_channel:{id}` and `paytree_proof:{id}` atomically. |
| 3b | Subsequent payment | **`save_paytree_payment(channel, new_state)`** → **`run_script("save_paytree_payment", …)`** (Lua). Atomically updates channel metadata and full proof key. |
| 4 | On status 0 or 3 | May call **`get_paytree_state(channel_id)`** → 1× `GET paytree_proof:{id}`. |
| 5 | On status 2 | `_verify_paytree_channel` then retry from step 3. |

So in the standard path, the **heavy work** after the initial channel fetch is:

- **Lua scripts** that read/write both `payment_channel:{id}` and `paytree_proof:{id}` (full proof JSON).
- Possible extra **GET** for current proof on reject/race.

**Flame graph (standard):**  
Wide red blocks for `save_paytree_pay` / `save_paytree_payme` (the script-driven save) and for `get_paytree_pruned_channel_state` (~5 s). So: **one expensive channel GET + heavy script-based save (and possibly proof GET)**.

---

## 3. First-optimization flow (optimization_type = 1)

**Goal:** Persist only **sparse Merkle nodes** and channel metadata; no full `PaytreeState`; verify using root + subroot from the node store.

### Queries and operations

| Step | Operation | What runs |
|------|------------|-----------|
| 1 | (already done) | `get_paytree_pruned_channel_state` → same 1× `GET` as standard. |
| 2 | Node read | **`get_nodes(channel_id, [root_key, subroot_index])`** → **1× `MGET`** over `paytree_first_opt_node:{channel_id}:*` for 2 keys. |
| 3 | Root backfill | If root missing → **`merge_nodes(channel_id, {root_key: paytree_root_b64})`** → `MSET` + `ZADD` (index). |
| 4 | Duplicate / verify | In-memory: `verify_paytree_proof_first_opt(i, leaf_b64, siblings_b64, subroot_b64, subroot_index, depth)` (no proof fetch). |
| 5 | Node write | **`merge_nodes(channel_id, updates)`** with `updates = _build_first_opt_node_updates(...)` → **1× `MSET`** (all new nodes) + **1× `ZADD`** (index). |
| 6 | First payment only | **`save_channel(payment_channel)`** → `SET payment_channel:{id}` + `ZADD` for global/open sets (no Lua). |
| 7 | Metadata update | **`payment_channel_repository.update(payment_channel)`** → 1× `GET` (existing channel) + `SET` + optional `ZADD`/`ZREM` for open/closed sets. |

So in the first-opt path:

- **Reads:** 1× GET (pruned channel) + 1× MGET (2 node keys). No Lua for reads.
- **Writes:** MSET + ZADD for nodes; SET + ZADD for channel (and update). **No `run_script`** for proof or channel+proof atomics.

**Flame graph (first-opt):**  
`get_nodes` (~1.58 s, MGET), `merge_nodes` (~5.32 s, MSET + ZADD), and the same `get_paytree_pruned_channel_state` (~5 s). The large **save_paytree_pay** / **save_paytree_payme** blocks from the standard path are **absent** here; any smaller `save_paytree_payr`/`run_script` in the profile is not part of the core first-opt persist path (first-opt does not call `save_paytree_payment` or `save_channel_and_initial_paytree_state`).

---

## 4. Equivalence

- **API:** Same `receive_paytree_payment(channel_id, dto)` and same response DTO (`PaytreePaymentResponseDTO`).
- **Semantics:** Both verify the proof, enforce duplicate detection (by `i` + leaf), validate `i` and amount, and persist enough for idempotent responses and settlement.
- **Difference in what is stored:**
  - **Standard:** Full `PaytreeState` (leaf, siblings, created_at) in `paytree_proof:{id}` plus channel metadata; atomicity via Lua.
  - **First-opt:** Sparse Merkle nodes in `paytree_first_opt_node:{id}:*` and index; channel metadata only (no full proof blob).

So they are **functionally equivalent** from the API and business-rule perspective; they differ in **storage layout and how persistence is implemented** (Lua scripts vs batched GET/MGET + SET/MSET + ZADD).

---

## 5. What changes (summary)

| Aspect | Standard | First-opt |
|--------|----------|-----------|
| Pruned channel fetch | 1× GET | Same 1× GET |
| Proof storage | Full state in `paytree_proof:{id}` via **Lua** | Sparse nodes via **MGET + MSET + ZADD** (no Lua for proof) |
| Channel + proof atomicity | Lua script updates channel + proof together | Separate: `save_channel` or `update` (SET + ZADD), nodes via `merge_nodes` |
| Extra reads on save | Possible `get_paytree_state` on reject | None for proof |
| Verification | `verify_paytree_proof_standard` (root + full path) | `verify_paytree_proof_first_opt` (subroot + pruned path) |

---

## 6. Why performance differs (in practice: standard can be better)

**Diff-graph / real metrics:** When comparing Baseline (first-opt) vs Comparison (standard) in real runs:

- **Vendor payment duration:** First-opt (e.g. green line) shows **higher average delay** (e.g. ~4–7.5 ms in the first segment) than standard (e.g. blue line, ~0.9–1.2 ms).
- **CPU time consumed:** Baseline (first-opt) averages **~3.28 cores** vs Comparison (standard) **~1.35 cores** — so first-opt uses more CPU and can contribute to higher latency.

So in these measurements **the standard performs better** (lower delay, lower CPU) than the first optimization.

**Why first-opt can be worse despite “fewer” high-level ops:**

1. **More round-trips in first-opt:** The first-opt path does **get_paytree_pruned_channel_state** (1 GET), then **get_nodes** (1 MGET), then **merge_nodes** (1 MSET + 1 ZADD), then **update** (1 GET + 1 SET + ZADD). That’s several sequential store round-trips per request. Standard does one GET (pruned channel) then one **Lua script** that does channel+proof read/write in a single DB shot.

2. **One DB shot vs many:** Standard’s save is a single script call (one network/DB round-trip). First-opt’s MGET + MSET + ZADD are separate round-trips (or two: MGET then MSET+ZADD), so latency adds up and CPU can spike from multiple serialized calls.

3. **Reducing first-opt round-trips:** To make first-opt competitive we can **batch the node operations into one Lua script**: one script that does MGET (read keys) + MSET (updates) + ZADD (index) in a single `run_script` call, i.e. **one DB shot** for the node store, similar to standard’s single-shot save.
