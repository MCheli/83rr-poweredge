-- Cache for container ID to name mapping
local container_cache = {}

-- For docker daemon events (input plugin: docker_events).
-- docker_events does a single read() of up to Buffer_Size bytes from the
-- /events stream and packs whatever it got as ONE record under `message`;
-- it does no line framing. Docker writes one JSON object per line, so a read
-- can hold several events, or start/end mid-event when a burst (every
-- healthcheck's exec_* events land together) is bigger than the buffer. The
-- old code parsed the whole buffer as one event: a buffer that began with an
-- exec_ event was dropped along with any die/stop behind it, and a buffer that
-- began mid-event became "docker ? ? unknown" (~850 docs/day). Now each line
-- is handled on its own and lines that aren't the start of an event are
-- dropped. Buffer_Size in fluent-bit.conf is raised so splits are rare.
-- Fluent Bit's lua filter doesn't ship cjson, so we extract the fields
-- we need from the raw JSON string with simple string.match patterns.
-- Field shape per docker events: status / id / from / Type / Action /
-- Actor.ID / Actor.Attributes.name.

-- Turn one event's fields into a record, or nil to drop it.
-- `labels` = {project=, oneoff=, exit_code=} from Actor.Attributes (may be empty).
local function build_event(action, etype, actor_id, actor_name, labels)
    -- Filter out the firehose of healthcheck exec_create/exec_start/exec_die
    -- events — Docker emits one per probe per container, ~5k/day of noise
    -- that overwhelms the actually-useful lifecycle events. Also drop
    -- network connect/disconnect on every container start (we infer those
    -- from container start/stop anyway).
    if string.sub(action, 1, 5) == "exec_" then return nil end
    if action == "connect" or action == "disconnect" then return nil end

    local rec = { event_type = action }
    if etype then rec["event_scope"] = etype end
    if etype == "container" then
        rec["container_name"] = actor_name
        if actor_id then rec["container_id"] = string.sub(actor_id, 1, 12) end
        -- Compose labels tell real services from scratch/`docker run`
        -- containers (no project) and `docker compose run` one-offs
        -- (oneoff "True"); die events carry the exit code. All three are
        -- used by the container-died alert.
        rec["compose_project"] = labels.project
        rec["compose_oneoff"] = labels.oneoff
        rec["exit_code"] = tonumber(labels.exit_code or "")
    elseif etype == "image" then
        -- For image events the "name" is the image name/sha and shouldn't
        -- masquerade as a container_name (would pollute aggregations).
        rec["image"] = actor_name or actor_id
        rec["container_name"] = "docker-image-event"
    else
        -- volume / network / builder / daemon: the actor isn't a container.
        rec["docker_object"] = actor_name or actor_id
        rec["container_name"] = "docker-" .. (etype or "daemon") .. "-event"
    end

    -- Build a human-readable `log` line + level mapping for what's left:
    -- start, stop, restart, kill, die, oom, create, destroy, pull, etc.
    rec["log"] = "docker " .. (etype or "?") .. " " .. action .. " "
        .. (rec["container_name"] or rec["docker_object"] or "?")
    if action == "die" or action == "kill" or action == "oom" then
        rec["level"] = "ERROR"
    elseif action == "stop" or action == "destroy" then
        rec["level"] = "WARNING"
    else
        rec["level"] = "INFO"
    end
    return rec
end

local function parse_event_line(line)
    -- A fragment (the tail of an event cut by the previous read) doesn't
    -- start with '{' or has no Action; there's nothing usable in it.
    if string.sub(line, 1, 1) ~= "{" then return nil end
    local action = string.match(line, '"Action":"([^"]+)"')
    if not action then return nil end
    return build_event(
        action,
        string.match(line, '"Type":"([^"]+)"'),
        string.match(line, '"Actor":%s*{[^}]*"ID":"([^"]+)"'),
        string.match(line, '"Attributes":%s*{[^}]-"name":"([^"]+)"'),
        {
            project = string.match(line, '"com%.docker%.compose%.project":"([^"]+)"'),
            oneoff = string.match(line, '"com%.docker%.compose%.oneoff":"([^"]+)"'),
            exit_code = string.match(line, '"exitCode":"(%-?%d+)"'),
        })
end

function normalize_docker_event(tag, timestamp, record)
    local raw = record["message"]
    local out = {}
    if type(raw) == "string" then
        for line in string.gmatch(raw, "[^\r\n]+") do
            local rec = parse_event_line(line)
            if rec then out[#out + 1] = rec end
        end
    elseif type(record["Action"]) == "string" then
        -- Already structured (a Parser set on the input).
        local actor = record["Actor"]
        local actor_id, actor_name
        local labels = {}
        if type(actor) == "table" then
            actor_id = actor["ID"]
            local attrs = actor["Attributes"]
            if type(attrs) == "table" then
                actor_name = attrs["name"]
                labels = {
                    project = attrs["com.docker.compose.project"],
                    oneoff = attrs["com.docker.compose.oneoff"],
                    exit_code = attrs["exitCode"],
                }
            end
        end
        local rec = build_event(record["Action"], record["Type"], actor_id, actor_name, labels)
        if rec then out[1] = rec end
    end

    if #out == 0 then return -1, timestamp, record end
    if #out == 1 then return 1, timestamp, out[1] end
    -- A table of records splits one input record into several.
    return 1, timestamp, out
end

function add_container_name(tag, timestamp, record)
    -- Extract container ID from tag (docker.<container_id>)
    -- Only docker.<64-hex id> tags from the tail input; docker.events also
    -- matches docker.* and would otherwise get container_name "unknown" and
    -- a failed config.v2.json lookup per event.
    local container_id = string.match(tag, "^docker%.(%x+)$")

    if container_id and #container_id == 64 then
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
