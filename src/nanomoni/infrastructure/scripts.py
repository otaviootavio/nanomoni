"""Central registry for Redis Lua scripts used across the application.

Return Code Conventions for payment scripts:
    - 0: Stale/no update — new value not strictly greater than stored value.
    - 1: Success — state saved.
    - 2: Channel not found or missing required config field.
    - 3: Capacity exceeded — new value exceeds channel max.
"""

VENDOR_SCRIPTS: dict[str, str] = {
    "save_signature_payment": """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_amount = tonumber(ARGV[2])
        local channel_amount = tonumber(ARGV[3])

        local channel_exists = redis.call('EXISTS', channel_key)
        if channel_exists == 0 then
            return {2, ''}
        end

        if new_amount > channel_amount then
            local current_raw = redis.call('GET', latest_key)
            return {3, current_raw or ''}
        end

        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end

        local current = cjson.decode(current_raw)
        local current_amount = tonumber(current.cumulative_owed_amount)
        if new_amount > current_amount then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
    """,
}

# Shared script for signature-mode channel initialisation.
# KEYS[1] = payment_channel:{id}, KEYS[2] = payment_state:{id}
# ARGV[1] = channel_json, ARGV[2] = state_json, ARGV[3] = created_ts, ARGV[4] = channel_id
_SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT = """
    local channel_key = KEYS[1]
    local latest_key = KEYS[2]
    local channel_json = ARGV[1]
    local state_json = ARGV[2]
    local created_ts = tonumber(ARGV[3])
    local channel_id = ARGV[4]

    if redis.call('EXISTS', channel_key) == 1 then
        return {0, ''}
    end
    if redis.call('EXISTS', latest_key) == 1 then
        return {0, ''}
    end

    redis.call('SET', channel_key, channel_json)
    redis.call('SET', latest_key, state_json)
    redis.call('ZADD', 'payment_channels:all', created_ts, channel_id)
    redis.call('ZADD', 'payment_channels:open', created_ts, channel_id)

    return {1, state_json}
"""

VENDOR_SCRIPTS["save_channel_and_initial_payment"] = (
    _SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT
)

# ---- Unified scripts for PaymentRepository (proof-based channels) ----

# save_payment: atomic CAS for unified PaymentChannel + PaymentState + CryptoProof.
# KEYS[1] = payment_channel:{id}, KEYS[2] = payment_state:{id}, KEYS[3] = crypto_proof:{id}
# ARGV[1] = new_ref (int), ARGV[2] = state_json, ARGV[3] = proof_json
_SAVE_PAYMENT_SCRIPT = """
    local channel_key = KEYS[1]
    local state_key = KEYS[2]
    local proof_key = KEYS[3]
    local new_ref = tonumber(ARGV[1])
    local state_json = ARGV[2]
    local proof_json = ARGV[3]

    local channel_raw = redis.call('GET', channel_key)
    if not channel_raw then
        return {2, ''}
    end
    local channel = cjson.decode(channel_raw)

    local max_steps = tonumber(channel.max_steps)
    if not max_steps then
        return {2, ''}
    end
    if new_ref > max_steps then
        local cur = redis.call('GET', state_key)
        return {3, cur or ''}
    end

    local last_ref = channel.last_proof_reference
    local prev = (last_ref ~= nil and last_ref ~= cjson.null) and tonumber(last_ref) or -1

    if new_ref > prev then
        channel.last_proof_reference = new_ref
        redis.call('SET', channel_key, cjson.encode(channel))
        redis.call('SET', state_key, state_json)
        redis.call('SET', proof_key, proof_json)
        return {1, tostring(new_ref)}
    else
        return {0, tostring(prev)}
    end
"""

# save_channel_and_initial_payment_unified: atomic first-payment init for proof-based channels.
# KEYS[1] = payment_channel:{id}, KEYS[2] = payment_state:{id}, KEYS[3] = crypto_proof:{id}
# ARGV[1] = channel_json (last_proof_reference already set), ARGV[2] = state_json,
# ARGV[3] = proof_json, ARGV[4] = created_ts, ARGV[5] = channel_id
_SAVE_CHANNEL_AND_INITIAL_PAYMENT_UNIFIED_SCRIPT = """
    local channel_key = KEYS[1]
    local state_key = KEYS[2]
    local proof_key = KEYS[3]
    local channel_json = ARGV[1]
    local state_json = ARGV[2]
    local proof_json = ARGV[3]
    local created_ts = tonumber(ARGV[4])
    local channel_id = ARGV[5]

    if redis.call('EXISTS', channel_key) == 1 then
        return {0, ''}
    end
    if redis.call('EXISTS', state_key) == 1 then
        return {0, ''}
    end

    redis.call('SET', channel_key, channel_json)
    redis.call('SET', state_key, state_json)
    redis.call('SET', proof_key, proof_json)
    redis.call('ZADD', 'payment_channels:all', created_ts, channel_id)
    redis.call('ZADD', 'payment_channels:open', created_ts, channel_id)

    return {1, state_json}
"""

# save_payment_with_nodes: first-opt PayTree atomic save (nodes + channel + state + proof).
# Performs the same monotonic CAS as save_payment (against the *stored* channel's
# last_proof_reference / max_steps) so concurrent first-opt payments cannot move the
# reference backwards or exceed capacity. Nothing is written unless the CAS passes.
# KEYS[1] = merkle_node_index:{id}, KEYS[2] = payment_channel:{id},
# KEYS[3] = payment_state:{id}, KEYS[4] = crypto_proof:{id},
# KEYS[5] = payment_channels:open, KEYS[6] = payment_channels:closed
# ARGV[1] = channel_id, ARGV[2] = num_node_pairs,
# ARGV[3..2+2n] = node_suffix, val pairs,
# ARGV[3+2n] = new_ref, ARGV[4+2n] = state_json, ARGV[5+2n] = proof_json,
# ARGV[6+2n] = channel_json, ARGV[7+2n] = is_closed ("0"/"1"), ARGV[8+2n] = created_ts
# Returns {status, ref}: 1 = success (ref=new_ref), 0 = stale/not-increasing (ref=prev),
#         2 = no max_steps available, 3 = capacity exceeded (ref=prev).
_SAVE_PAYMENT_WITH_NODES_SCRIPT = """
    local index_key = KEYS[1]
    local channel_key = KEYS[2]
    local state_key = KEYS[3]
    local proof_key = KEYS[4]
    local open_key = KEYS[5]
    local closed_key = KEYS[6]
    local channel_id = ARGV[1]
    local n = tonumber(ARGV[2]) or 0
    local prefix = "merkle_node:" .. channel_id .. ":"

    local new_ref = tonumber(ARGV[3 + n*2])
    local state_json = ARGV[4 + n*2]
    local proof_json = ARGV[5 + n*2]
    local channel_json = ARGV[6 + n*2]
    local new_is_closed = (ARGV[7 + n*2] == '1')
    local created_ts = tonumber(ARGV[8 + n*2]) or 0

    -- Resolve the authoritative max_steps and previous reference for the CAS.
    -- A stored channel is the source of truth; for a brand-new channel fall back
    -- to the channel_json being written (sourced from the issuer).
    local max_steps = nil
    local prev = -1
    local old_is_closed = nil
    local existing = redis.call('GET', channel_key)
    if existing and existing ~= '' then
        local ch = cjson.decode(existing)
        old_is_closed = ch.is_closed
        max_steps = tonumber(ch.max_steps)
        local last_ref = ch.last_proof_reference
        if last_ref ~= nil and last_ref ~= cjson.null then
            prev = tonumber(last_ref)
        end
    else
        local new_ch = cjson.decode(channel_json)
        max_steps = tonumber(new_ch.max_steps)
    end

    if not max_steps then
        return {2, ''}
    end
    if new_ref > max_steps then
        return {3, tostring(prev)}
    end
    if new_ref <= prev then
        return {0, tostring(prev)}
    end

    -- CAS passed: commit nodes first, then channel/state/proof atomically.
    for i = 1, n do
        local suffix = ARGV[2 + (i-1)*2 + 1]
        local val = ARGV[2 + (i-1)*2 + 2]
        redis.call('SET', prefix .. suffix, val)
        redis.call('ZADD', index_key, 0, suffix)
    end

    redis.call('SET', channel_key, channel_json)
    redis.call('SET', state_key, state_json)
    redis.call('SET', proof_key, proof_json)

    if old_is_closed == nil then
        -- Brand-new channel in the vendor store: register it in the indexes so
        -- get_all()/listing and index-based cleanup can see it.
        redis.call('ZADD', 'payment_channels:all', created_ts, channel_id)
        if new_is_closed then
            redis.call('ZADD', closed_key, created_ts, channel_id)
        else
            redis.call('ZADD', open_key, created_ts, channel_id)
        end
    elseif old_is_closed ~= new_is_closed then
        if new_is_closed then
            redis.call('ZREM', open_key, channel_id)
            redis.call('ZADD', closed_key, created_ts, channel_id)
        else
            redis.call('ZREM', closed_key, channel_id)
            redis.call('ZADD', open_key, created_ts, channel_id)
        end
    end

    return {1, tostring(new_ref)}
"""

# Merkle node read+merge: MGET two nodes then MSET+ZADD updates atomically.
# KEYS[1] = merkle_node_index:{id}, KEYS[2] = read key 1, KEYS[3] = read key 2
# ARGV[1] = channel_id, ARGV[2] = num_updates, ARGV[3+] = suffix, val pairs
_MERKLE_GET_NODES_AND_MERGE_SCRIPT = """
    local index_key = KEYS[1]
    local read1 = redis.call('GET', KEYS[2])
    local read2 = redis.call('GET', KEYS[3])
    local channel_id = ARGV[1]
    local n = tonumber(ARGV[2]) or 0
    local prefix = "merkle_node:" .. channel_id .. ":"
    for i = 1, n do
        local suffix = ARGV[2 + (i-1)*2 + 1]
        local val = ARGV[2 + (i-1)*2 + 2]
        redis.call('SET', prefix .. suffix, val)
        redis.call('ZADD', index_key, 0, suffix)
    end
    return {read1 or '', read2 or ''}
"""

# Merkle node merge only: MSET + ZADD in one shot.
# KEYS[1] = merkle_node_index:{id}
# ARGV[1] = channel_id, ARGV[2] = num_pairs, ARGV[3+] = suffix, val pairs
_MERKLE_MERGE_NODES_SCRIPT = """
    local index_key = KEYS[1]
    local channel_id = ARGV[1]
    local n = tonumber(ARGV[2]) or 0
    local prefix = "merkle_node:" .. channel_id .. ":"
    for i = 1, n do
        local suffix = ARGV[2 + (i-1)*2 + 1]
        local val = ARGV[2 + (i-1)*2 + 2]
        redis.call('SET', prefix .. suffix, val)
        redis.call('ZADD', index_key, 0, suffix)
    end
    return 1
"""

VENDOR_SCRIPTS.update(
    {
        "save_payment": _SAVE_PAYMENT_SCRIPT,
        "save_channel_and_initial_payment_unified": _SAVE_CHANNEL_AND_INITIAL_PAYMENT_UNIFIED_SCRIPT,
        "save_payment_with_nodes": _SAVE_PAYMENT_WITH_NODES_SCRIPT,
        "merkle_get_nodes_and_merge": _MERKLE_GET_NODES_AND_MERGE_SCRIPT,
        "merkle_merge_nodes": _MERKLE_MERGE_NODES_SCRIPT,
    }
)

ISSUER_SCRIPTS = {
    "create_channel": (
        "if redis.call('EXISTS', KEYS[1]) == 1 then "
        "  return {0, ''} "
        "end "
        "redis.call('SET', KEYS[1], ARGV[1]) "
        "return {1, ARGV[1]}"
    ),
}
