#!/bin/bash
# =============================================================================
# Security telemetry emitter  (cron: every 10 min, as mcheli)
# =============================================================================
# Ships two signals into logs-homelab-* so OpenSearch monitors can alert:
#
#   1. event_type=security_unexpected_port
#        A TCP port is LISTENing that is not in the known-good allowlist.
#        Catches a new/rogue service or a misconfigured container publish.
#
#   2. event_type=security_external_db_conn
#        An ESTABLISHED connection to a sensitive backend port (OpenSearch
#        9200/9300, Postgres 5432, Grafana 3000) from a peer that is NOT
#        loopback and NOT the docker bridge range (172.16.0.0/12). On a
#        correctly firewalled host these backends are only reached via the
#        docker network / nginx, so any such row is worth a look.
#
# Read-only (ss); no sudo needed for socket/port enumeration. Emits via the
# same in-container OpenSearch endpoint used by emit_host_metrics.sh /
# backup.sh. All failures are non-fatal (best-effort telemetry).
#
# Cron:
#   */10 * * * * /home/mcheli/83rr-poweredge/scripts/emit_security_telemetry.sh >> /home/mcheli/83rr-poweredge/logs/security_telemetry.log 2>&1
# =============================================================================
set -uo pipefail

# Known-good LISTEN ports. Everything here is an intentionally-running
# service (see CLAUDE.md / docker-compose). A port NOT in this set fires
# the unexpected-port alert. Update deliberately when adding a service.
ALLOWED_PORTS=" 22 53 80 139 443 445 1900 3000 5001 5050 5051 5353 5432 7777 9200 9300 9600 9650 10000 11520 25565 32400 32410 32412 32413 32414 32469 32919 137 138 "

SENSITIVE_PORTS="9200 9300 5432 3000"

ts() { date -u +"%Y-%m-%dT%H:%M:%S.000Z"; }
INDEX="logs-homelab-$(date +%Y.%m.%d)"

emit() {
  # $1 = JSON object (single line)
  docker exec opensearch curl -s -X POST \
    "http://localhost:9200/${INDEX}/_doc" \
    -H 'Content-Type: application/json' -d "$1" >/dev/null 2>&1 || true
}

# ---- 1. Unexpected listening TCP ports --------------------------------------
ss -tlnH 2>/dev/null | awk '{print $4}' | sed -E 's/.*:([0-9]+)$/\1/' | sort -un | while read -r port; do
  [ -z "$port" ] && continue
  case "$ALLOWED_PORTS" in
    *" $port "*) : ;;  # known good
    *)
      emit "{\"@timestamp\":\"$(ts)\",\"container_name\":\"security-telemetry\",\"event_type\":\"security_unexpected_port\",\"level\":\"WARNING\",\"metric_name\":\"unexpected_listen_port\",\"port\":${port},\"msg\":\"Unexpected LISTEN port ${port} (not in allowlist)\"}"
      ;;
  esac
done

# ---- 2. Non-local connections to sensitive backend ports --------------------
for sp in $SENSITIVE_PORTS; do
  ss -tnH state established "( sport = :$sp )" 2>/dev/null | awk '{print $4" "$3}' | while read -r local peer; do
    peer_ip="${peer%:*}"
    case "$peer_ip" in
      127.0.0.1|::1|"") continue ;;                 # loopback
      172.1[6-9].*|172.2[0-9].*|172.3[01].*) continue ;;  # docker bridge 172.16/12
    esac
    emit "{\"@timestamp\":\"$(ts)\",\"container_name\":\"security-telemetry\",\"event_type\":\"security_external_db_conn\",\"level\":\"ERROR\",\"metric_name\":\"sensitive_port_peer\",\"port\":${sp},\"peer\":\"${peer_ip}\",\"msg\":\"Established connection to sensitive port ${sp} from non-local peer ${peer_ip}\"}"
  done
done
