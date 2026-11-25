#!/bin/bash
# cron-notify.sh — run one cron job; if it fails, say so ONCE on ntfy.
#
#   cron-notify.sh JOB_NAME COMMAND [ARGS...]
#
# Wraps every line of the server's crontab (docs/OBSERVABILITY.md#alerting):
#   0 2 * * * /home/mcheli/83rr-poweredge/scripts/cron-notify.sh backup \
#       /home/mcheli/83rr-poweredge/scripts/backup.sh >> .../logs/backup.log 2>&1
# Env assignments go in front of the wrapper (cron passes them through).
#
# - Runs COMMAND directly (no eval) and exits with its exit code.
# - Non-zero exit after a success (or on the first run): ONE ntfy push to topic
#   homelab, priority 4 (high), title "cron job failed: JOB_NAME". Further
#   failures stay quiet until the job succeeds again; that success sends one
#   low-priority (2) "recovered" push. State: logs/cron-notify/JOB_NAME.failed.
# - Every run writes logs/textfile/cron-JOB_NAME.prom for node-exporter:
#     homelab_cron_last_run_timestamp_seconds{job}
#     homelab_cron_last_exit_code{job}
#     homelab_cron_last_success_timestamp_seconds{job}   (kept across failures)
#   Grafana alerts on these (backup not succeeded in 26 h).
# - The token (NTFY_PUBLISH_TOKEN, repo .env) goes to curl in a header file,
#   never on a command line or in a log. A failed push never changes the exit
#   code. CRON_NOTIFY_STATE_DIR / CRON_NOTIFY_TEXTFILE_DIR override the dirs
#   (used by the route test, so it leaves no state behind).

set -u

if [[ $# -lt 2 ]]; then
    echo "usage: $0 JOB_NAME COMMAND [ARGS...]" >&2
    exit 64
fi
JOB="$1"; shift
if [[ ! "$JOB" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "cron-notify: JOB_NAME must match [A-Za-z0-9._-]+ (got '$JOB')" >&2
    exit 64
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
STATE_DIR="${CRON_NOTIFY_STATE_DIR:-${PROJECT_DIR}/logs/cron-notify}"
TEXTFILE_DIR="${CRON_NOTIFY_TEXTFILE_DIR:-${PROJECT_DIR}/logs/textfile}"
NTFY_TOPIC="${NTFY_TOPIC:-homelab}"
HOST="$(hostname -s)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron-notify ${JOB}: $*"; }

started=$(date +%s)
"$@"
rc=$?
finished=$(date +%s)

# Read KEY=value from .env without sourcing it (values may hold shell metachars).
env_get() {
    [[ -f "$ENV_FILE" ]] || return 0
    local v
    v=$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-)
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    printf '%s' "$v"
}

# IP of a container on the compose "infrastructure" network (host -> bridge).
container_ip() {
    docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}' "$1" 2>/dev/null \
        | awk '$1 ~ /(^|_)infrastructure$/ && $2 != "" {print $2; exit}'
}

# ntfy_push PRIORITY TAG TITLE MESSAGE -> one push to topic homelab
ntfy_push() {
    local token body ip url hdr sent=false
    token="${NTFY_PUBLISH_TOKEN:-$(env_get NTFY_PUBLISH_TOKEN)}"
    if [[ -z "$token" ]]; then
        log "NTFY_PUBLISH_TOKEN not set; push \"$3\" skipped"
        return 0
    fi
    hdr=$(umask 077; mktemp)
    printf 'Authorization: Bearer %s\n' "$token" > "$hdr"
    unset token
    body=$(python3 -c 'import json, sys; print(json.dumps({"topic": sys.argv[1], "priority": int(sys.argv[2]), "tags": [sys.argv[3], "cron"], "title": sys.argv[4], "message": sys.argv[5]}))' \
        "$NTFY_TOPIC" "$1" "$2" "$3" "$4")
    ip=$(container_ip ntfy)
    local urls=(${ip:+"http://${ip}/"} "https://ntfy.markcheli.com/")
    [[ -z "${NTFY_URL:-}" ]] || urls=("$NTFY_URL")
    for url in "${urls[@]}"; do
        if curl -fsS -o /dev/null --max-time 15 -H @"$hdr" \
                -H 'Content-Type: application/json' -d "$body" "$url"; then
            sent=true
            log "push \"$3\" sent (${url})"
            break
        fi
    done
    rm -f "$hdr"
    [[ "$sent" == true ]] || log "could not reach ntfy to send \"$3\""
}

# Textfile metrics (atomic: write a temp file, then rename).
write_metrics() {
    [[ -d "$TEXTFILE_DIR" ]] || return 0
    local prom="${TEXTFILE_DIR}/cron-${JOB}.prom" last_ok=""
    if [[ $rc -eq 0 ]]; then
        last_ok=$finished
    elif [[ -f "$prom" ]]; then
        last_ok=$(awk '/^homelab_cron_last_success_timestamp_seconds/ {print $2}' "$prom")
    fi
    local tmp
    tmp=$(mktemp "${TEXTFILE_DIR}/.cron-${JOB}.XXXXXX") || return 0
    {
        echo "# HELP homelab_cron_last_run_timestamp_seconds When the cron job last finished."
        echo "# TYPE homelab_cron_last_run_timestamp_seconds gauge"
        echo "homelab_cron_last_run_timestamp_seconds{job=\"${JOB}\"} ${finished}"
        echo "# HELP homelab_cron_last_exit_code Exit code of the cron job's last run."
        echo "# TYPE homelab_cron_last_exit_code gauge"
        echo "homelab_cron_last_exit_code{job=\"${JOB}\"} ${rc}"
        if [[ -n "$last_ok" ]]; then
            echo "# HELP homelab_cron_last_success_timestamp_seconds When the cron job last exited 0."
            echo "# TYPE homelab_cron_last_success_timestamp_seconds gauge"
            echo "homelab_cron_last_success_timestamp_seconds{job=\"${JOB}\"} ${last_ok}"
        fi
    } > "$tmp"
    chmod 644 "$tmp"
    command mv -f "$tmp" "$prom"
}
write_metrics

mkdir -p "$STATE_DIR"
state="${STATE_DIR}/${JOB}.failed"
if [[ $rc -ne 0 ]]; then
    if [[ ! -f "$state" ]]; then
        echo "rc=${rc} since=${finished}" > "$state"
        log "exit ${rc} after $((finished - started))s; sending the failure push"
        ntfy_push 4 warning "cron job failed: ${JOB}" \
            "${JOB} exited ${rc} on ${HOST} after $((finished - started))s ($(date '+%Y-%m-%d %H:%M %Z')). Its log is the file its crontab line appends to (crontab -l). One push per failure streak; a success sends \"recovered\"."
    else
        log "exit ${rc}; still failing (already reported), no push"
    fi
elif [[ -f "$state" ]]; then
    since=$(sed -n 's/.*since=\([0-9]*\).*/\1/p' "$state")
    rm -f "$state"
    log "succeeded again; sending the recovery push"
    ntfy_push 2 white_check_mark "cron job recovered: ${JOB}" \
        "${JOB} succeeded again on ${HOST}${since:+ (failing since $(date -d "@${since}" '+%Y-%m-%d %H:%M %Z' 2>/dev/null || echo "$since"))}."
fi

exit $rc
