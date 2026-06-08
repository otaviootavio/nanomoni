# PayTree first-opt vendor: receive-payment data flow

Optimistic single-node fetch (aligned with `test_paytree_first_opt_walkthrough`).

```mermaid
flowchart TD
    subgraph request["Request"]
        A["receive_paytree_payment(channel_id, dto)"]
        DTO["dto: i, leaf_b64, siblings_b64[]"]
    end

    subgraph init["Init"]
        B["depth = compute_tree_depth(max_i)"]
        C["root_key = key_eytzinger(depth, 0, depth)"]
    end

    subgraph one_query["One query: root + subroot"]
        Q1["root_key, subroot_index = infer (depth, i, len(siblings))"]
        Q2["get_nodes(channel_id, [root_key, subroot_index])"]
        Q3["root_b64, subroot_b64 from result"]
    end

    subgraph root_ensure["Ensure root in store"]
        R2{"root_b64?"}
        R3["merge_nodes({ root_key → paytree_root_b64 })"]
    end

    subgraph duplicate["Duplicate check (dto.i ≤ prev_i)"]
        D1["check_duplicate_paytree_payment_by_leaf"]
        D2{"is_duplicate?"}
        D4["subroot_b64 (from get_nodes)"]
        D5["verify_paytree_proof_first_opt"]
        D6["return idempotent PaytreePaymentResponseDTO"]
    end

    subgraph validate["Validate"]
        V1["validate_paytree_i"]
        V2["validate_paytree_amount"]
    end

    subgraph verify["Verify pruned proof"]
        S3["subroot_b64 (from get_nodes)"]
        S4["verify_paytree_proof_first_opt(leaf_b64, i, siblings_b64, subroot_b64, subroot_index, depth)"]
    end

    subgraph persist["Persist"]
        P1["updates = _build_first_opt_node_updates(siblings + path)"]
        P2["merge_nodes(channel_id, updates)"]
        P3["save_channel if is_first_payment"]
        P4["channel.last_leaf_* = dto; update(channel)"]
    end

    subgraph response["Response"]
        OUT["PaytreePaymentResponseDTO(channel_id, i, cumulative_owed_amount, created_at)"]
    end

    A --> B --> C --> Q1 --> Q2 --> Q3 --> R2
    R2 -->|None| R3
    R2 -->|present| duplicate
    R3 --> duplicate

    D1 --> D2
    D2 -->|yes| D4 --> D5 --> D6
    D2 -->|no| validate

    validate --> V1 --> V2 --> S3 --> S4
    S4 --> P1 --> P2 --> P3 --> P4 --> OUT
```

## Storage reads (one round-trip)

| Step | What | Redis |
|------|------|--------|
| Root + subroot | Infer both keys, then one fetch | `MGET paytree_first_opt_node:{channel_id}:{root_key}` and `...:{subroot_index}` |

Infer and fetch are merged: compute `root_key` and `subroot_index`, then `get_nodes(channel_id, [root_key, subroot_index])` — one MGET, no `ZREVRANGE`, no second GET.

## Storage writes

| Step | What | Redis |
|------|------|--------|
| Root if missing | One key | `SET paytree_first_opt_node:...` + `ZADD` index |
| After verify | New nodes | `SET` per node + `ZADD` index (merge_nodes) |
| Channel metadata | Pruned channel | `SET payment_channel:{channel_id}` (save/update) |

## Dataflow summary

1. **In:** `channel_id`, `dto` (i, leaf_b64, siblings_b64).
2. **One read:** compute `root_key` and `subroot_index` (infer), then `get_nodes(channel_id, [root_key, subroot_index])` → root_b64, subroot_b64.
3. **Ensure root:** if root_b64 missing, `merge_nodes({ root_key })` once.
4. **Duplicate path:** if same (i, leaf), use subroot_b64 from step 2 → verify → return idempotent.
5. **Main path:** validate i and amount → use subroot_b64 from step 2 → verify.
6. **Write:** build updates (siblings + path), `merge_nodes`; optionally save channel; update channel last_leaf_*.
7. **Out:** `PaytreePaymentResponseDTO`.
