-- Extract container name from the tag
-- Tag format: docker.var.lib.docker.containers.<container_id>.<container_id>-json.log
function extract_container_name(tag, timestamp, record)
    -- Extract container ID from tag
    local container_id = string.match(tag, "containers%.([^%.]+)%.")
    if container_id then
        record["container_id"] = string.sub(container_id, 1, 12)
    end
    return 1, timestamp, record
end
