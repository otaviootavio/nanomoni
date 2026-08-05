# PayTree Optimized Variants (First Opt & Second Opt)

This PR introduces PayTree First Opt and Second Opt payment schemes to nanomoni, along with performance fixes that address critical O(n²) and unbounded-growth design flaws. The benchmark at 1M payments is now terminating; previously it was effectively non-terminating due to quadratic work and gigabyte-scale serialization.

---

## Related Issues

| Issue | Title | Status |
|-------|-------|--------|
| [#50](https://github.com/otaviootavio/nanomoni/issues/50) | perf: PayTree First Opt has two quadratic/unbounded design flaws that make the benchmark unterminating | **Closed** (resolved by this branch) |
| [#53](https://github.com/otaviootavio/nanomoni/issues/53) | perf: Unbounded Redis key accumulation for PayTree node cache entries | **Closed** (Redis Hash migration) |
| [#54](https://github.com/otaviootavio/nanomoni/issues/54) | perf: Merge two sequential Redis round-trips into single MGET per payment | Open (follow-up) |

---

## Summary of Changes

### 1. PayTree First Opt & Second Opt Implementation
- Full end-to-end flow: issuer (channel open), vendor (payment receive), client (payment send)
- DTOs, validators, use cases, HTTP routers, Lua scripts for atomic Redis updates
- In-memory storage adapters for tests; E2E and use-case tests

### 2. Bug Fixes (Issue #50)

#### Bug 1 — `verified_indices` O(n²) accumulation
- **Problem:** `verified_indices` grew by one per payment; `compute_send_levels` scanned the entire list for each payment → O(n²) total work.
- **Rationale:** Payments are strictly monotonically increasing. The maximum LCP with any past index is always achieved by the **most recent** verified index. Storing all past indices is redundant.
- **Fix:** Replaced `verified_indices: list[int]` with `last_verified_index: Optional[int]` in First Opt. `compute_send_levels` is now O(1).

#### Bug 2 — `node_cache_b64` O(n × depth) serialization
- **Problem:** The vendor merged the cache on every payment; after 1M payments at depth 20, the cache held ~20M entries (~1.2 GB JSON), re-serialized on every payment.
- **Rationale:** For the *next* payment, only the most recent payment's siblings matter (they share the longest prefix). Older cache entries are permanently dead weight.
- **Fix (First Opt):** Replace instead of merge — `update_cache_with_full_siblings` now returns a fresh dict of exactly `depth` entries.

### 3. Second Opt Architectural Difference

Second Opt is algorithmically richer: it uses `forbidden_levels` derived from *all* past LCPs to prune more aggressively than First Opt. Simply keeping only `last_verified_index` would lose that advantage.

**Design decision:** Instead of storing `verified_indices`, derive skippable levels **directly from the node cache**:

```python
send_levels = [l for l in range(depth) if f"{l}:{(i >> l) ^ 1}" not in node_cache_b64]
```

This is O(depth), requires no stored index history, and preserves full Second Opt pruning quality. See [\#50 (comment)](https://github.com/otaviootavio/nanomoni/issues/50#issuecomment-3935870634).

### 4. Per-Node Redis Keys (Issue #50 Discussion)

**Design decision:** Store each tree node as its own Redis key instead of packing the cache into the state JSON. Benefits:
- Vendor fetches only `depth` keys per payment via MGET
- Per-payment writes are O(depth) via Lua MSET
- No growing state blob; `node_cache_b64` removed from both Opt state entities

See [\#50 (comment)](https://github.com/otaviootavio/nanomoni/issues/50#issuecomment-3936009255).

### 5. Redis Hash Migration (Issue #53)

**Problem:** Per-node keys (`paytree1opt_node:{channel}:{level}:{position}`) accumulate unbounded — every payment adds ~2×depth keys, none ever deleted. At 1M payments, ~40M keys per channel (~2.4 GB).

**Fix:** Migrate to one Redis Hash per channel (`paytree1opt_nodes:{channel_id}`, `paytree2opt_nodes:{channel_id}`). Use `HMGET`/`HSET` instead of `MGET`/`MSET`. Reduces Redis keys from 2+2d per read and 1+e per write to **3 keys total** per operation.

Closes [#53](https://github.com/otaviootavio/nanomoni/issues/53).

### 6. Architectural Split: First Opt (LCP) vs Second Opt (cache-lookup)

**Design decision:** First Opt keeps its O(1) LCP-based `compute_send_levels` + replace-style cache. Second Opt uses O(depth) cache-key lookup + merge-style cache. Switching First Opt to cache-lookup would require merging the cache (accumulating siblings from all payments), making it a "partial Second Opt" and losing the elegant constant-size state. The tradeoff was evaluated and the split was maintained. See [\#50 (comment)](https://github.com/otaviootavio/nanomoni/issues/50#issuecomment-3936098999).

### 7. Early-Stop Verification & Fetch Optimization

**CPU:** Both variants compute `trusted_level = depth - k_max` via LCP and hash only from the leaf up to the trusted node, saving O(k_max) hash operations per payment.

**Redis I/O:** `get_paytree_*_sibling_cache_for_index` accepts `trusted_level` and fetches only levels `[0, trusted_level)` instead of all `depth` keys. In sequential workloads, `trusted_level` is small.

See [\#50 (comment)](https://github.com/otaviootavio/nanomoni/issues/50#issuecomment-3936739510).

### 8. `max_i` in Payment DTO

Added `max_i` to `ReceivePaytreeFirstOptPaymentDTO` and `ReceivePaytreeSecondOptPaymentDTO`. Enables future single round-trip optimization (Issue #54): the vendor can fetch channel, state, and sibling cache in one MGET when `max_i` is known upfront.

---

## Implementation Status (from [\#50](https://github.com/otaviootavio/nanomoni/issues/50#issuecomment-3937673600))

| Problem | Status |
|---------|--------|
| Unbounded `verified_indices` (First Opt) | Done |
| Unbounded `verified_indices` (Second Opt) | Done (cache-lookup, no stored indices) |
| Cache serialization bottleneck → per-node Redis keys | Done |
| Redis key accumulation → Hash migration | Done (Issue #53) |
| Architectural split (LCP vs cache-lookup) | Maintained |
| Early-stop verification + fetch optimization | Done |
| Single Redis round-trip per payment | Open (Issue #54) |

---

## Breaking Changes

- **Redis Hash migration:** Existing data with `paytree1opt_node:*` and `paytree2opt_node:*` keys will not be readable. Channels must be re-opened. For benchmark and fresh deployments this is acceptable.

---

## Testing

- Use-case tests for First Opt and Second Opt flows
- E2E tests for both variants
- Idempotency and duplicate-proof handling tests
- In-memory storage implements `hmget`/`hset` for test compatibility

---

Closes #50  
Closes #53
