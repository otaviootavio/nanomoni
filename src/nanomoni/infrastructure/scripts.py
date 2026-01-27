"""Central registry for Redis Lua scripts used across the application."""

VENDOR_SCRIPTS = {
    "save_signature_payment": """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_amount = tonumber(ARGV[2])
        local channel_amount = tonumber(ARGV[3])

        -- Check channel existence (fast check via key existence or just rely on channel_amount)
        -- Since we pass channel_amount, we assume the caller verified the channel exists locally.
        -- But for strictness, we can check if the channel key exists.
        local channel_exists = redis.call('EXISTS', channel_key)
        if channel_exists == 0 then
            return {2, ''}
        end
        
        if new_amount > channel_amount then
            -- Channel capacity exceeded - get current tx for error reporting
            local current_raw = redis.call('GET', latest_key)
            return {0, current_raw or ''}
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
    "save_payword_payment": """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_k = tonumber(ARGV[2])

        -- Load and decode the stored channel to read max_k (atomic validation)
        local channel_raw = redis.call('GET', channel_key)
        if not channel_raw then
            return {2, ''}
        end
        local channel = cjson.decode(channel_raw)
        local max_k = tonumber(channel.payword_max_k or channel.max_k)
        if not max_k then
            -- Channel exists but is missing PayWord configuration
            return {2, ''}
        end
        if new_k > max_k then
            -- k exceeds PayWord commitment window
            local current_raw = redis.call('GET', latest_key)
            return {3, current_raw or ''}
        end

        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end

        local current = cjson.decode(current_raw)
        local current_k = tonumber(current.k)
        if new_k > current_k then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
    """,
    "save_paytree_payment": """
        local latest_key = KEYS[1]
        local channel_key = KEYS[2]
        local new_val = ARGV[1]
        local new_i = tonumber(ARGV[2])

        -- Load and decode the stored channel to read max_i (atomic validation)
        local channel_raw = redis.call('GET', channel_key)
        if not channel_raw then
            return {2, ''}
        end
        local channel = cjson.decode(channel_raw)
        local max_i = tonumber(channel.paytree_max_i)
        if not max_i then
            -- Channel exists but is missing PayTree configuration
            return {2, ''}
        end
        if new_i > max_i then
            -- i exceeds PayTree commitment window
            local current_raw = redis.call('GET', latest_key)
            return {3, current_raw or ''}
        end

        local current_raw = redis.call('GET', latest_key)
        if not current_raw then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        end

        local current = cjson.decode(current_raw)
        local current_i = tonumber(current.i)
        if new_i > current_i then
            redis.call('SET', latest_key, new_val)
            return {1, new_val}
        else
            return {0, current_raw}
        end
    """,
}

# Consolidated script used for all three channel initialization scenarios
# (save_channel_and_initial_payment, save_channel_and_initial_payword_state, save_channel_and_initial_paytree_state)
_SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT = """
    local channel_key = KEYS[1]
    local latest_key = KEYS[2]
    local channel_json = ARGV[1]
    local state_json = ARGV[2]
    local created_ts = tonumber(ARGV[3])
    local channel_id = ARGV[4]
    
    -- Check if channel already exists
    if redis.call('EXISTS', channel_key) == 1 then
        return {0, ''}
    end
    
    -- Check if tx already exists (shouldn't if channel doesn't, but for safety)
    if redis.call('EXISTS', latest_key) == 1 then
        return {0, ''}
    end
    
    -- 1. Save Channel Metadata
    redis.call('SET', channel_key, channel_json)
    
    -- 2. Save Initial State
    redis.call('SET', latest_key, state_json)
    
    -- 3. Update Indices
    redis.call('ZADD', 'payment_channels:all', created_ts, channel_id)
    redis.call('ZADD', 'payment_channels:open', created_ts, channel_id)
    
    return {1, state_json}
"""

# Register the consolidated script under the original three keys for backward compatibility
VENDOR_SCRIPTS.update(
    {
        "save_channel_and_initial_payment": _SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT,
        "save_channel_and_initial_payword_state": _SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT,
        "save_channel_and_initial_paytree_state": _SAVE_CHANNEL_AND_INITIAL_STATE_SCRIPT,
    }
)

ISSUER_SCRIPTS = {
    "create_channel": (
        "if redis.call('EXISTS', KEYS[1]) == 1 then "
        "  return 0 "
        "end "
        "redis.call('SET', KEYS[1], ARGV[1]) "
        "return 1"
    ),
}
