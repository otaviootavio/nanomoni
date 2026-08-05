# Bottleneck Analysis (flame graph × code)

Cross-check of the CPU profile with the codebase to identify common bug categories: multiple DB/store calls, unoptimized algorithms, and related issues.

---

## 1. Unoptimized algorithm (major – client proof generation)

**Profile:** `payment_proof_first_opt` → `_get_merkle_proof_pruned` → `proof_indexes_first_opt` → `<genexpr>` → **`lca_between` (~21 s)**.

**Code:** `src/nanomoni/protocol/paytree_first_opt.py`:

```python
k_max = max((lca_between(leaf_index, a, depth) for a in prior_leaves), default=-1)
```

**What’s wrong:**  
- `prior_leaves` is the list of **all** leaf indexes already sent in the session.  
- Client loop (`client/paytree.py`): for each payment `i`, we call `payment_proof_first_opt(i, prior_sent_indexes)` and then append `i` to `prior_sent_indexes`.  
- So for the k-th payment we call `lca_between` **k−1** times (once per prior).  
- Total over N payments: **0 + 1 + 2 + … + (N−1) = N(N−1)/2 → O(N²)** calls to `lca_between`.

**Why it hurts:**  
- `lca_between` itself is O(1) (bit ops in `crypto/merkle_index.py`), but the **number of calls** grows quadratically with the number of payments.  
- This matches the flame graph: the `<genexpr>` and `lca_between` dominate client CPU.

**Fix (correct and safe for sequential sends):**  
- Verifier side already uses a **single** `last_verified_index` (see `compute_send_levels_first_opt` in `merkle_index.py`).  
- For **sequential** sends 0, 1, 2, …, the LCP of leaf `i` with any prior `j < i` is **maximized at j = i−1**. So the same pruning is achieved by using only the **last** prior.  
- In `proof_indexes_first_opt`, when `prior_leaves` is non-empty, use only the last element for `k_max`:

  - e.g. `last_prior = prior_leaves[-1]` and `k_max = lca_between(leaf_index, last_prior, depth)` (and `default=-1` when `prior_leaves` is empty).  
- That reduces work from **O(N²)** to **O(N)** over a session.

**Category:** Not optimized algorithm (redundant work in a hot path).

---

## 2. Multiple DB/store calls (vendor first-opt node store)

**Profile:** Vendor side is not the main cost in the **client** flame graph (client time is dominated by proof generation). Still, vendor store usage can be improved.

**Code:** `src/nanomoni/infrastructure/vendor/paytree_first_opt_repository_impl.py` – `merge_nodes`:

```python
async def merge_nodes(self, channel_id: str, updates: dict[str, str]) -> None:
    index = _index_key(channel_id)
    for node_key, hash_b64 in updates.items():
        await self._store.set(_node_key(channel_id, node_key), hash_b64)
        await self._store.zadd(index, {node_key: 0.0})
```

**What’s wrong:**  
- For each node we do **two** round-trips: `set` and `zadd`.  
- Per payment, `_build_first_opt_node_updates` produces O(depth) nodes (siblings + path). So **~2 × (2 × depth)** store calls per payment (e.g. depth 20 → ~80 calls per payment).

**Category:** Multiple DB/store calls (no batching/pipelining).

**Fix:**  
- Use a single pipeline (or batch) for the whole `updates` dict: e.g. pipeline all `set` and one `zadd` with all keys, or batch `set` + one `zadd` per payment, depending on store API.

---

## 3. No N+1 in payment proof path (client)

**Checked:**  
- Client proof path uses in-memory `Paytree._tree_levels` and `proof_indexes_first_opt` / `_get_merkle_proof_pruned` (no DB).  
- So the client bottleneck is **not** multiple DB calls; it’s the O(N²) use of `lca_between` above.

---

## 4. Vendor per-payment DB pattern (acceptable, not N+1)

**Code:** `receive_paytree_payment` → `get_paytree_pruned_channel_state` (one call per request); first-opt branch → `get_nodes([root_key, subroot_index])` (one batched read), then `merge_nodes(updates)` and `payment_channel_repository.update(payment_channel)`.  
- One channel fetch per request is expected (REST one-payment-per-request).  
- `get_nodes` is already a single batched read.  
- The only improvement here is to reduce the number of store operations inside `merge_nodes` (see §2).

---

## Summary

| # | Category              | Location                         | Severity | Fix |
|---|------------------------|----------------------------------|----------|-----|
| 1 | Unoptimized algorithm  | `proof_indexes_first_opt`: max over all `prior_leaves` | High (client CPU) | Use only last prior for `k_max` when sending sequentially |
| 2 | Multiple DB/store calls | `merge_nodes`: loop with set + zadd per key | Medium (vendor latency) | Pipeline/batch all sets and zadd |
| 3 | N+1 / repeated DB      | Client proof path                | None     | No DB in proof path |
| 4 | Per-request DB usage   | Vendor receive_paytree_payment   | Low      | Already one channel fetch + one get_nodes; improve merge_nodes only |

Recommendation: implement the **proof_indexes_first_opt** change first (use last prior only for sequential sends); then consider **merge_nodes** pipelining for vendor-side load.
