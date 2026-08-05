# Protocol layer analysis: paytree walkthroughs

Both flows live in `tests/unit/crypto/test_paytree_first_opt_walkthrough.py`:

- **test_paytree_standard_walkthrough** — PayTree protocol: full proof (leaf → root) per payment.
- **test_paytree_first_opt_walkthrough** — First optimization: pruned proof (leaf → sub-root) using LCA with prior payments; verifier stores siblings (and can store extra path nodes).

Goal: **crypto** = pure functions → **protocol** = orchestration over crypto → **other** = API, DB, etc.

---

## 1. All used functions (by source)

### From `nanomoni.crypto.merkle_index`

| Function | Used in standard | Used in first_opt | Purpose |
|----------|------------------|-------------------|---------|
| `lca_between(a, b, n)` | no | yes | LCP length for pruning (sub-root level) |
| `get_ancestor_at_level(leaf_index, level)` | no | yes | Ancestor position for pruned proof |
| `get_sibling_keys_eytzinger(leaf_index, depth)` | yes (info only) | no | Eytzinger keys for auth path (display) |
| `get_sibling_position_at_level(leaf_index, level)` | indirect | indirect | Used by tree/store helpers |
| `key_eytzinger(level, position, depth)` | yes | yes | Eytzinger key for node store |

### From `nanomoni.crypto.merkle_tree`

| Function | Used in standard | Used in first_opt | Purpose |
|----------|------------------|-------------------|---------|
| `build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(...)` | yes | yes | Sibling (level, pos) indexes for proof |
| `build_merkle_tree(leaves)` | yes | yes | Build tree; get root + levels |
| `combine_children(left, right, left_is_first)` | no (indirect) | no (indirect) | Used inside verification / path computation |
| `hash_bytes(data)` | yes | yes | Leaf hash, tree build |
| `verify_proof_of_leaf_a_given_ancestor_b(secret, leaf_index, siblings, subroot_node, subroot_index, depth)` | yes | yes | Verify proof to sub-root |

### Defined in the walkthrough test file

| Name | Type | Used in standard | Used in first_opt |
|------|------|------------------|-------------------|
| `_leaf_index_to_binary(i, num_bits)` | helper | yes | yes |
| `_node_key(level, position, depth)` | helper | yes | yes |
| `MerkleNodeStore` | class | yes | yes |
| `ProverSecretStore` | class | yes | yes |
| `ProverNodeStore` | class | yes | yes |
| `build_prover_storages(num_leaves, leaf_secrets)` | protocol | yes | yes |
| `VerifierNodeStore` | class | yes | yes |
| `VerifierSecretStore` | class | yes | yes |
| `ProverSentIndexStore` | class | yes | yes |
| `VerifierReceivedIndexStore` | class | yes | yes |
| `verifier_store_root(store, root, depth)` | protocol | yes | yes |
| `verifier_store_proof(store, leaf_index, siblings, depth)` | protocol | yes | yes |
| `verifier_stores_secret(secret_store, leaf_index, secret, depth)` | protocol | yes | yes |
| `verifier_store_computed_path(store, leaf_index, leaf_hash, siblings, depth)` | protocol | no | no (defined, not called) |
| `infer_subroot_index_for_incoming_pruned_merkle_proof(leaf_index, siblings_count, depth)` | protocol | no | yes |
| `_lookup_sibling_hashes(store, indexes, depth)` | helper | yes | yes |
| `_run_standard_setup(num_leaves, leaf_secrets)` | setup | yes | yes |
| `test_paytree_standard_walkthrough` | test | — | — |
| `test_paytree_first_opt_walkthrough` | test | — | — |

---

## 2. Purely for test

- **`_run_standard_setup`** — Builds prover/verifier stores and sends root to verifier; used only by the two test functions. Either keep as test helper or re-export a “protocol setup” that returns the same stores/depth for tests to use.
- **`test_paytree_standard_walkthrough`** — Test: runs standard flow with fixed leaf list and prints.
- **`test_paytree_first_opt_walkthrough`** — Test: runs first-opt flow with fixed leaf list and prints.
- **Print statements** and **hardcoded leaf index lists** (`[0, 3, 4, 5, 6, 7]` / `[0, 1, 3, 4, 6, 7]`) are test-only.

**Borderline:**

- **`ProverSentIndexStore`** / **`VerifierReceivedIndexStore`** — In the test they only record indexes for “prior payments” used by first_opt. In production, “prior received” is the verifier’s persisted state (e.g. DB). So they can live in **protocol** as in-memory state types; the protocol layer does not depend on DB, and the API/DB layer can map “verifier state” to these types or to repository calls.
- **`get_sibling_keys_eytzinger`** — Used only for a single `print` in the standard walkthrough. Optional for protocol (e.g. debug/display); not required for core logic.

---

## 3. How to build the `protocol` layer

### 3.1 Layering

- **crypto** — Pure functions only: `merkle_index` (keys, paths, LCA, sibling positions) and `merkle_tree` (hash, build tree, proof indexes, verify proof). No storage, no I/O.
- **protocol** — Orchestrates crypto and defines the paytree flows and storage *contracts* (key scheme, what prover/verifier store). No HTTP, no DB; storage can be abstract (e.g. key–value interface) or concrete in-memory for tests.
- **Other (API, DB, etc.)** — Vendor/issuer APIs, repositories, client: they call **protocol** (and possibly **crypto**) and implement storage with DB/Redis, etc.

### 3.2 Suggested layout

```
src/nanomoni/
  crypto/                    # unchanged: pure functions
    merkle_index.py
    merkle_tree.py
    paytree.py               # client + verify_paytree_proof (can stay or move; see below)

  protocol/                  # NEW LAYER
    __init__.py
    paytree_standard.py      # standard flow: build proof leaf->root, verifier verify
    paytree_first_opt.py     # first-opt: LCA + pruned proof, infer sub-root, verifier verify
```

**Keep in test file only (not in protocol folder):**

- **Storage** — Node/secret/index store types: MerkleNodeStore, ProverSecretStore, VerifierNodeStore, VerifierSecretStore, ProverSentIndexStore, VerifierReceivedIndexStore; operations: verifier_store_root, verifier_store_proof, verifier_stores_secret, verifier_store_computed_path, _lookup_sibling_hashes, _leaf_index_to_binary, _node_key, infer_subroot_index_for_incoming_pruned_merkle_proof.

- **protocol/paytree_standard.py**  
  - **Prover:** given leaf index and prover stores → read secret, `build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(0, leaf_index, depth, 0)`, `_lookup_sibling_hashes` → (secret, siblings).  
  - **Verifier:** given (secret, siblings), sub-root = root from store → `verify_proof_of_leaf_a_given_ancestor_b` → then `verifier_store_proof` + `verifier_stores_secret`.

- **protocol/paytree_first_opt.py**  
  - **Prover:** given leaf index, prior received indexes, depth, prover stores → `lca_between(leaf_index, prior, depth)` for all priors, take max → ancestor level/position → `build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(0, leaf_index, ancestor_level, ancestor_pos)` → `_lookup_sibling_hashes` → (secret, pruned_siblings).  
  - **Verifier:** given (secret, siblings), depth → `infer_subroot_index_for_incoming_pruned_merkle_proof(leaf_index, len(siblings), depth)` → read sub-root from store → `verify_proof_of_leaf_a_given_ancestor_b` → `verifier_store_proof` + `verifier_stores_secret` (and optionally `verifier_store_computed_path`).

- **Setup**  
  - build_prover_storages, verifier_store_root, _run_standard_setup (keep in test file)
### 3.3 Dependencies

- **protocol** imports only from **crypto** (and stdlib). No `application`, `domain`, `infrastructure`, `api`.
- **application** (use cases) and **client** can import from **protocol** and **crypto**; they implement storage (e.g. PaytreeRepository) using **infrastructure** and call protocol steps instead of duplicating the flow.

### 3.4 Relation to existing `crypto/paytree.py`

- **crypto/paytree.py** today: `Paytree` (client tree + proofs), `verify_paytree_proof`, encoding (b64), `update_cache_with_siblings_and_path`.  
- Options:  
  - **A)** Keep in crypto: treat as “client + verification” convenience that uses merkle_tree/merkle_index. Protocol layer then uses crypto (merkle_*) and defines prover/verifier flows and stores; API can keep using `verify_paytree_proof` and client `Paytree` as today.  
  - **B)** Move verification and path-update logic into **protocol** (e.g. protocol calls `verify_proof_of_leaf_a_given_ancestor_b` and defines key scheme); crypto stays pure (merkle_index + merkle_tree only). Then `verify_paytree_proof` becomes a thin wrapper in protocol (or in crypto that delegates to protocol).  

Recommendation: start with **A** — add **protocol** with the flows and stores from the walkthrough; keep **crypto/paytree.py** as is. Later, if you want a single place for “all verification and key logic”, move that into protocol and have crypto only do hashing and tree/proof indexing.

### 3.5 Tests

- **Unit tests for protocol:**  
  - Keep `test_paytree_first_opt_walkthrough.py` (or rename to `test_protocol_paytree_walkthrough.py`) under e.g. `tests/unit/protocol/`.  
  - Tests import from nanomoni.protocol (and crypto); use `_run_standard_setup` (or protocol’s public setup) and the same in-memory stores; test functions remain as today but call protocol functions instead of in-test implementations.  
- **Purely test:** `_run_standard_setup` can stay in the test file as a test helper that uses `protocol.setup` + protocol storage types, or move to protocol as a “demo setup” used only by tests.

---

## 4. Summary

| Layer | Responsibility |
|-------|----------------|
| **crypto** | Pure functions: merkle_index (keys, LCA, sibling positions), merkle_tree (hash, build, proof indexes, verify). Optional: paytree client + verify_paytree_proof. |
| **protocol** | Standard and first-opt flows (prover build proof, verifier infer sub-root when pruned, verify). No storage, no setup; those stay in test file. No HTTP/DB. |
| **Other** | API (vendor/issuer), DB/Redis, repositories, client: use protocol + crypto and implement storage. |

**Used functions:** listed in §1; **test-only:** storage types, setup (`_run_standard_setup`, `build_prover_storages`, `verifier_store_root`), the two test functions, prints, and hardcoded leaf lists (§2). **Protocol layer:** new folder `protocol/` with `paytree_standard`, `paytree_first_opt` (crypto orchestration only); storage and setup stay in test file (§3).
