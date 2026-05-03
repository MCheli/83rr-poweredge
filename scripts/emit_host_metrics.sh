#!/bin/bash
# Pulls a few key host metrics from Prometheus and ships them to OpenSearch
# as docs we can alert on. Bridges the metrics-vs-logs gap until Prometheus
# Alertmanager is set up.
#
# Schedule via cron every 5 min:
#   */5 * * * * /home/mcheli/83rr-poweredge/scripts/emit_host_metrics.sh \
#     >> /home/mcheli/83rr-poweredge/logs/host_metrics.log 2>&1

set -euo pipefail

PROM_QUERY='
disk_used_pct: (node_filesystem_size_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"} - node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"}) / node_filesystem_size_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"} * 100
mem_used_pct: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
cpu_used_pct: (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100
load_1m: node_load1
'

emit_metric() {
    local name="$1" promql="$2"
    local val
    val=$(docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=$(echo -n "$promql" | python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read()))")" 2>/dev/null \
        | python3 -c "import json, sys; d=json.load(sys.stdin); r=d['data']['result']; print(r[0]['value'][1] if r else 'null')" 2>/dev/null || echo "null")

    [ "$val" = "null" ] && return

    local now_iso=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
    local payload="{\"@timestamp\":\"${now_iso}\",\"container_name\":\"host-metrics\",\"event_type\":\"metric\",\"metric_name\":\"${name}\",\"metric_value\":${val},\"level\":\"INFO\"}"

    # Add level=WARNING for thresholds we care about
    case "$name" in
        disk_used_pct)
            local int_val=${val%.*}
            [ "$int_val" -ge 85 ] 2>/dev/null && payload="${payload%\}},\"level\":\"WARNING\"}" || true
            [ "$int_val" -ge 95 ] 2>/dev/null && payload="${payload%\}},\"level\":\"ERROR\"}" || true
            ;;
        mem_used_pct)
            local int_val=${val%.*}
            [ "$int_val" -ge 90 ] 2>/dev/null && payload="${payload%\}},\"level\":\"WARNING\"}" || true
            ;;
    esac

    docker exec opensearch curl -s -X POST \
        "http://localhost:9200/logs-homelab-$(date +%Y.%m.%d)/_doc" \
        -H 'Content-Type: application/json' \
        -d "${payload}" >/dev/null 2>&1 || true
}

emit_metric disk_used_pct '(node_filesystem_size_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"} - node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"}) / node_filesystem_size_bytes{fstype!~"tmpfs|fuse.*",mountpoint="/"} * 100'
emit_metric mem_used_pct '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
emit_metric cpu_used_pct '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100'
emit_metric load_1m 'node_load1'
