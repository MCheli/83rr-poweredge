#!/bin/bash
# emit_alert_metrics.sh — host facts Prometheus can't scrape itself, written
# as node-exporter textfile metrics for the Grafana alert rules
# (docs/OBSERVABILITY.md#alerting):
#
#   homelab_cert_not_after_timestamp_seconds{cert}   every ssl_certificate that
#       nginx's production.conf serves (file in infrastructure/nginx/certs)
#   homelab_ups_up                       1 = upsc answered for ups@localhost
#   homelab_ups_on_battery               1 = ups.status has OB
#   homelab_ups_low_battery              1 = ups.status has LB
#   homelab_ups_battery_charge_percent   battery.charge
#   homelab_ups_battery_runtime_seconds  battery.runtime
#   homelab_ups_load_percent             ups.load
#
# Output: logs/textfile/homelab-alerts.prom (atomic rename). The Grafana rule
# "alert metrics stale" fires if this file stops being refreshed.
# Read-only: no secrets, no sudo (upsc needs no login).
#
# Schedule via cron every minute (wrapped by cron-notify.sh):
#   * * * * * /home/mcheli/83rr-poweredge/scripts/cron-notify.sh alert-metrics \
#     /home/mcheli/83rr-poweredge/scripts/emit_alert_metrics.sh \
#     >> /home/mcheli/83rr-poweredge/logs/alert_metrics.log 2>&1

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEXTFILE_DIR="${TEXTFILE_DIR:-${PROJECT_DIR}/logs/textfile}"
NGINX_CONF="${PROJECT_DIR}/infrastructure/nginx/conf.d/production.conf"
CERT_DIR="${PROJECT_DIR}/infrastructure/nginx/certs"
UPS="${UPS:-ups@localhost}"
OUT="${TEXTFILE_DIR}/homelab-alerts.prom"

[[ -d "$TEXTFILE_DIR" ]] || { echo "no textfile dir ${TEXTFILE_DIR}" >&2; exit 1; }
tmp=$(mktemp "${TEXTFILE_DIR}/.homelab-alerts.XXXXXX") || exit 1
trap 'rm -f "$tmp"' EXIT

{
    echo "# HELP homelab_cert_not_after_timestamp_seconds Expiry (notAfter) of a certificate nginx serves."
    echo "# TYPE homelab_cert_not_after_timestamp_seconds gauge"
    # /etc/nginx/certs/<name>.crt in the container = infrastructure/nginx/certs/<name>.crt here
    for name in $(sed -n 's#^[[:space:]]*ssl_certificate[[:space:]]\+/etc/nginx/certs/\([^;[:space:]]*\);.*#\1#p' "$NGINX_CONF" | sort -u); do
        f="${CERT_DIR}/${name}"
        end=$(openssl x509 -noout -enddate -in "$f" 2>/dev/null | cut -d= -f2-) || continue
        [[ -n "$end" ]] || continue
        ts=$(date -d "$end" +%s 2>/dev/null) || continue
        echo "homelab_cert_not_after_timestamp_seconds{cert=\"${name}\"} ${ts}"
    done

    ups=$(upsc "$UPS" 2>/dev/null)
    up=0; [[ -n "$ups" ]] && up=1
    val() { awk -F': ' -v k="$1" '$1 == k {print $2; exit}' <<<"$ups"; }
    status=$(val ups.status)
    ob=0; [[ " $status " == *" OB "* ]] && ob=1
    lb=0; [[ " $status " == *" LB "* ]] && lb=1
    echo "# HELP homelab_ups_up 1 if upsc answered for the UPS."
    echo "# TYPE homelab_ups_up gauge"
    echo "homelab_ups_up ${up}"
    if [[ $up -eq 1 ]]; then
        echo "# HELP homelab_ups_on_battery 1 if the UPS runs on battery (ups.status OB)."
        echo "# TYPE homelab_ups_on_battery gauge"
        echo "homelab_ups_on_battery ${ob}"
        echo "# HELP homelab_ups_low_battery 1 if the UPS reports low battery (ups.status LB)."
        echo "# TYPE homelab_ups_low_battery gauge"
        echo "homelab_ups_low_battery ${lb}"
        for pair in battery.charge:homelab_ups_battery_charge_percent \
                    battery.runtime:homelab_ups_battery_runtime_seconds \
                    ups.load:homelab_ups_load_percent; do
            v=$(val "${pair%%:*}")
            [[ "$v" =~ ^[0-9.]+$ ]] || continue
            echo "# HELP ${pair#*:} NUT ${pair%%:*} of ${UPS}."
            echo "# TYPE ${pair#*:} gauge"
            echo "${pair#*:} ${v}"
        done
    fi
} > "$tmp"

chmod 644 "$tmp"
command mv -f "$tmp" "$OUT"
trap - EXIT
