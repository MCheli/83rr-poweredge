#!/usr/bin/env bash
# logq.sh — read-only OpenSearch log query for the homelab (runs from the Mac mini or on the server).
#
#   logq.sh                          # errors, last 1h, all services
#   logq.sh errors 6                 # errors, last 6h
#   logq.sh 'container_name:tasks AND log:timeout' 2
#   logq.sh errors 1 tasks           # errors for one container
#
# Output: total hits, hits per container, top 10 normalized messages.
# Exit code: 0 = no hits, 1 = hits found, 2 = query/transport failure
# (so a deploy watch can do: `logq.sh errors 0.25 tasks || echo "errors after deploy"`).
# Only issues _search requests. OpenSearch has the security plugin disabled, so no auth;
# it is reached with `docker exec opensearch curl` because 9200 isn't published on the host.
set -euo pipefail

Q="${1:-errors}"
HOURS="${2:-1}"
SVC="${3:-}"
HOST="${LOGQ_SSH_HOST:-83rr-poweredge}"

MINUTES=$(awk -v h="$HOURS" 'BEGIN { printf "%d", h * 60 }')
[ "$MINUTES" -ge 1 ] || MINUTES=1

if [ "$Q" = "errors" ]; then
  # level set by the homelab-logs ingest pipeline; status parsed for nginx/http logs.
  Q='level:(ERROR OR FATAL OR CRITICAL OR PANIC) OR status:>=500 OR log:(error OR traceback OR exception OR panic)'
fi
[ -n "$SVC" ] && Q="container_name:\"$SVC\" AND ($Q)"

BODY=$(jq -cn --arg q "$Q" --arg since "now-${MINUTES}m" '{
  size: 500, track_total_hits: true,
  sort: [{"@timestamp": "desc"}],
  _source: ["@timestamp", "container_name", "msg", "log"],
  query: {bool: {filter: [
    {range: {"@timestamp": {gte: $since}}},
    {query_string: {query: $q, default_field: "log"}}]}},
  aggs: {svc: {terms: {field: "container_name", size: 100}}}}')

run() {
  if command -v docker >/dev/null 2>&1 && docker inspect opensearch >/dev/null 2>&1; then
    docker exec -i opensearch curl -sf -H 'Content-Type: application/json' \
      'localhost:9200/logs-homelab-*/_search' --data-binary @-
  else
    ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
      "docker exec -i opensearch curl -sf -H 'Content-Type: application/json' 'localhost:9200/logs-homelab-*/_search' --data-binary @-"
  fi
}

RESP=$(printf '%s' "$BODY" | run) || { echo "logq: query failed" >&2; exit 2; }
echo "$RESP" | jq -e '.hits' >/dev/null 2>&1 || { echo "logq: bad response: ${RESP:0:300}" >&2; exit 2; }

TOTAL=$(echo "$RESP" | jq '.hits.total.value')
echo "query: $Q"
echo "window: last ${MINUTES}m   hits: $TOTAL"
[ "$TOTAL" -eq 0 ] && exit 0
echo "--- by container"
echo "$RESP" | jq -r '.aggregations.svc.buckets[] | "\(.doc_count)\t\(.key)"'
echo "--- top messages (of newest $(echo "$RESP" | jq '.hits.hits | length'), digits -> N)"
echo "$RESP" | jq -r '.hits.hits[]._source
  | "\(.container_name)\t\((.msg // .log // "") | gsub("\\s+$"; "") | gsub("[0-9]+"; "N") | .[0:160])"' \
  | sort | uniq -c | sort -rn | head -10
exit 1
