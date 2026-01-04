-- Cache for container ID to name mapping
local container_cache = {}

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
