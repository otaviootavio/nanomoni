# Cross-check: Merkle Proof Compression memo vs codebase

This document cross-references the PayTree Engineering memo **"Merkle Proof Compression: Sequential Verification Strategy"** (Feb 2026, `merkle_proof_compression.pdf`) with the implementation in this repo.

---

## 1. First compression (authentication path intersection)

**Memo:**  
- `k_max = max{ LCP(x, aᵢ) | i = 1, …, m }`  
- Prover sends only levels `0` through `n − k_max − 1`. Levels `n − k_max` through `n − 1` are omitted (verifier already has them from P(a)).

**Code:**

- **`src/nanomoni/crypto/merkle_index.py`**
  - `lca_between(a, b, n)` — LCP in bits; docstring states Property 1: `|P(a) ∩ P(b)| = k`.
  - `compute_send_levels_first_opt(i, last_verified_index, depth)` returns `list(range(max(0, depth - k_max)))` with `k_max = lca_between(i, last_verified_index, depth)`.
- **First-opt prover** (`paytree_first_opt/prover.py`): uses `k_max = max(lca_between(leaf_index, a, depth) for a in indexes)` and `send_levels = list(range(max(0, depth - k_max)))` — matches memo (with `last_verified_index` or multiple `already_sent_indexes`).

**Verdict:** Implemented as in memo. Send levels = `{0, 1, …, n − k_max − 1}`.

---

## 2. Second compression (cross-path intersection)

**Memo:**  
- Property 2: `|P(x) ∩ Q(a)| = 1` at level `n − LCP(x, a) − 1`.  
- Forbidden levels: `F = { n − LCP(x, aᵢ) − 1 | i = 1…m }`.  
- Send levels: `L_send = { 0, 1, …, n−k_max−1 } \ F`.

**Code:**

- **`merkle_index.py`**: docstring for `lca_between` states Property 2: unique intersection at level `n − k − 1`.
- **`compute_send_levels_second_opt(i, depth, known_keys)`**: sends level `j` only if `key(level, get_sibling_position_at_level(i, level)) not in known_keys`. Repo stores P ∪ Q from prior proofs, so any level whose sibling is already in repo is omitted. That matches “omit level if it’s in F” (F = levels where P(x) ∩ Q(aᵢ) gives a node already stored).
- **Second-opt verifier** (`paytree_second_opt/verifier_store.py`): `store_proof_with_path` stores both P (siblings) and Q (computed path via `_compute_path_nodes`). So verifier accumulates K(a) = P(a) ∪ Q(a) as in memo.

**Verdict:** Implemented. Second-opt uses P ∪ Q and omits levels whose sibling key is in `known_keys`; effect is the same as memo’s F and L_send.

**Note:** Paper example has “F = {2, 1, 7}” for x=00001011 and prior 00001111, 00001000, 01111111. Our test uses forbidden `{depth − kᵢ − 1}` → {2, 1, 6}. So memo’s “7” is likely a typo for “6” (level for LCP(x, 127) = 1 → 8−1−1 = 6).

---

## 3. Early-stop verification

**Memo:**  
- Verifier can stop when the reconstructed hash matches any trusted node in ∪ K(aᵢ).  
- Earliest stop = first node on Q(x) that appears in stored P(aᵢ) or Q(aᵢ) = LCA at level `n − k_max`.  
- Sub-root at level `n − k_max`.

**Code:**

- **First-opt** (`paytree_first_opt/verifier.py`):  
  - `trusted_level = depth - k_max`, `known_node_hash = repo.get_node(trusted_level, i >> trusted_level)`.  
  - If not None, verifies only up to that node: `verify_proof_to_known_node(..., known_node_level=trusted_level)` with `siblings[:trusted_level]`.  
- **Second-opt** (`paytree_second_opt/verifier.py`):  
  - Same idea: `candidate_level = depth - k_max`, `candidate_pos = get_ancestor_at_level(i, candidate_level)`; if that key is in repo, set `trusted_level` and verify to it.

**Verdict:** Early stop at level `n − k_max` when that sub-root is in the repo is implemented in both first- and second-opt.

---

## 4. Q(x) ∩ P(aᵢ) — adjacent leaves (“zero siblings”)

**Memo:**  
- When x and aᵢ are adjacent (differ only in last bit), the “leaf-parent hash at level 0” (interpreted as the node one level above the leaf) can already be in P(aᵢ).  
- Example: leaf 0 verified first → P(a₀) stores sibling at (level 0, pos 1) = leaf 1. Then verifying leaf 1: compare Hash(leaf₁) with stored node; 0 siblings sent, 1 hash (or 0 if we only compare).  
- Memo also states: to support this and second compression, the verifier must **store Q(a)** (computed path) in addition to P(a).

**Code:**

- **First-opt** stores only P(a) (siblings + leaf at (0, leaf_index)). It does **not** store Q(a). So:
  - (0, leaf_index) is stored and is the early-stop anchor for the *other* leaf in the pair (the sibling at level 0). For leaf 1 we have (0,0) from proof 0; one hash gives (1,0). We do **not** have (1,0) in first-opt, so we still verify to root (or to a sub-root that is in P, e.g. when it’s a sibling of another prior leaf).
- **Second-opt** stores P(a) and Q(a). So (1,0) is stored after verifying leaf 0. When verifying leaf 1 we can stop at (1,0) — early stop with one hash.

**Verdict:**  
- “Store Q(a) so that early stop and second compression work” is implemented in **second-opt** (P + Q stored).  
- First-opt intentionally stores only P; it gets first compression and early stop only when the sub-root is a *sibling* from a prior proof (not an arbitrary path node).  
- The memo’s “0 siblings sent” adjacent-leaves case is maximally exploited when the verifier has the parent (1,0). That requires Q(0) stored → second-opt. In first-opt we still send 1 sibling (level 0) for leaf 1 and do one hash, then fetch more from repo and verify to root.

---

## 5. Implementation requirements (memo)

| Requirement | Code |
|-------------|------|
| Store nodes keyed by (level, position), not (proof_index, level) | Yes. `key(level, position)` → `"level:position"` in both first-opt and second-opt stores. |
| Store Q(a) in addition to P(a) after every verification | Yes in **second-opt** (`store_proof_with_path`). No in first-opt (by design: first-opt stores only P). |
| On fallback (sub-root not stored), still persist computed Q(a) afterward | Second-opt: we always call `store_proof_with_path` after a successful verification, which stores P + Q. So we always persist Q for the proof we just verified. We do not “fall back” to root and then skip storing Q. So we do persist Q after every successful verification. |

---

## 6. Summary table (memo vs code)

| Strategy | Memo | First-opt code | Second-opt code |
|----------|------|----------------|-----------------|
| First compression | Send levels 0..n−k_max−1 | `compute_send_levels_first_opt` ✓ | Uses first + second (known_keys) |
| Second compression | Omit levels in F (P(x)∩Q(aᵢ)) | N/A (no Q stored) | `compute_send_levels_second_opt` + P∪Q ✓ |
| Early stop at LCA | Stop at level n−k_max when in repo | `trusted_level = depth - k_max`, verify to `get_node(trusted_level, ...)` ✓ | Same idea ✓ |
| Q(x)∩P(aᵢ) adjacent | 0 siblings, 1 hash or compare | 1 sibling sent, 1 hash; no (1,0) in repo → verify to root | Q stored → early stop at (1,0) ✓ |
| Store P only | — | ✓ VerifierRepo stores P | — |
| Store P ∪ Q | Required for second compression & full early stop | — | ✓ store_proof_with_path |

---

## 7. Minor note (paper example)

- Memo example “F = {2, 1, 7}” for x=00001011 and priors 15, 8, 127: our tests use F = {2, 1, **6**} (level 7 would be 8−0−1 for LCP=0, but LCP(11, 127)=1 so 8−1−1=6). So the memo’s “7” is likely a typo; code and spec use 6.
