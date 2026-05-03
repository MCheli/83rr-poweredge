-- Cache for container ID to name mapping
local container_cache = {}

-- For docker daemon events (input plugin: docker_events).
-- Fluent Bit's docker_events ships the entire event as a JSON string in
-- `message`. We parse it manually here (parser filter was unreliable),
-- then pull container_name/container_id/event_type out of the nested
-- Actor field so they're at top level for aggregation.
-- Fluent Bit's lua filter doesn't ship cjson, so we extract the fields
-- we need from the raw JSON string with simple string.match patterns.
-- Field shape per docker events: status / id / from / Type / Action /
-- Actor.ID / Actor.Attributes.name. We pull the four flat fields directly
-- and parse Actor.Attributes.name with a nested pattern.
function normalize_docker_event(tag, timestamp, record)
    local raw = record["message"]
    if type(raw) == "string" then
        local action = string.match(raw, '"Action":"([^"]+)"')
        local etype = string.match(raw, '"Type":"([^"]+)"')
        local actor_id = string.match(raw, '"Actor":%s*{[^}]*"ID":"([^"]+)"')
        local actor_name = string.match(raw, '"Attributes":%s*{[^}]-"name":"([^"]+)"')
        if action then record["Action"] = action end
        if etype then record["Type"] = etype end
        if actor_id then record["actor_id"] = actor_id end
        if actor_name then record["actor_name"] = actor_name end
        record["message"] = nil
    end

    if record["actor_name"] then
        record["container_name"] = record["actor_name"]
        record["actor_name"] = nil
    end
    if record["actor_id"] then
        record["container_id"] = string.sub(record["actor_id"], 1, 12)
        record["actor_id"] = nil
    end

    local actor = record["Actor"]
    if type(actor) == "table" then
        if type(actor["Attributes"]) == "table" then
            local name = actor["Attributes"]["name"]
            if name then record["container_name"] = name end
            local image = actor["Attributes"]["image"]
            if image then record["image"] = image end
        end
        if actor["ID"] then
            record["container_id"] = string.sub(actor["ID"], 1, 12)
        end
    end
    if record["Action"] then record["event_type"] = record["Action"] end
    if record["Type"] then record["event_scope"] = record["Type"] end

    -- Filter out the firehose of healthcheck exec_create/exec_start/exec_die
    -- events — Docker emits one per probe per container, ~5k/day of noise
    -- that overwhelms the actually-useful lifecycle events. Also drop
    -- network connect/disconnect on every container start (we infer those
    -- from container start/stop anyway).
    local action = record["Action"] or "?"
    if string.sub(action, 1, 5) == "exec_" then
        return -1, timestamp, record  -- drop record
    end
    if action == "connect" or action == "disconnect" then
        return -1, timestamp, record
    end

    -- Build a human-readable `log` line + level mapping for what's left:
    -- start, stop, restart, kill, die, oom, create, destroy, pull, etc.
    local cname  = record["container_name"] or "?"
    record["log"] = "docker " .. (record["event_scope"] or "?") .. " " .. action .. " " .. cname
    if action == "die" or action == "kill" or action == "oom" then
        record["level"] = "ERROR"
    elseif action == "stop" or action == "destroy" then
        record["level"] = "WARNING"
    else
        record["level"] = "INFO"
    end
    return 1, timestamp, record
end

function add_container_name(tag, timestamp, record)
    -- Extract container ID from tag (docker.<container_id>)
    local container_id = string.match(tag, "docker%.([a-z0-9]+)")

    if container_id then
        -- Add short container ID
        record["container_id"] = string.sub(container_id, 1, 12)

        -- Check cache first
        if container_cache[container_id] then
            record["container_name"] = container_cache[container_id]
        else
            -- Try to read container name from Docker config
            local config_path = "/var/lib/docker/containers/" .. container_id .. "/config.v2.json"
            local file = io.open(config_path, "r")

            if file then
                local content = file:read("*all")
                file:close()

                -- Extract container name from JSON (simple pattern match)
                local name = string.match(content, '"Name":"/?([^"]+)"')
                if name then
                    container_cache[container_id] = name
                    record["container_name"] = name
                else
                    record["container_name"] = "unknown"
                end
            else
                record["container_name"] = "unknown"
            end
        end
    end

    return 1, timestamp, record
end
