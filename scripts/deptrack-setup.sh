#!/usr/bin/env bash
# =============================================================================
# deptrack-setup.sh — first-boot + idempotent configuration of Dependency-Track
# =============================================================================
# Run on the server after `docker compose ... up -d deptrack-*` is healthy.
# Every step checks current state first, so re-running is safe.
#
#   scripts/deptrack-setup.sh init-admin
#       Replaces the default admin/admin password with a random one and writes
#       it to ~/.config/deptrack/admin-password (0600). Move it into 1Password
#       ("Dependency-Track admin"), then delete the file. Run once.
#
#   scripts/deptrack-setup.sh apply
#       Needs the admin password: $DT_ADMIN_PASSWORD, else the file above,
#       else a prompt. Then:
#        1. base URL https://deptrack.ops.markcheli.com (links in alerts)
#        2. vuln sources: OSV (OS + language ecosystems) and NVD on; GitHub
#           Advisories only if DT_GITHUB_TOKEN is set in .env; mirrors kicked off
#        3. secret NTFY_AUTH_HEADER = "Bearer $NTFY_PUBLISH_TOKEN"
#        4. publisher "ntfy" (webhook + infrastructure/dependency-track/ntfy-template.peb)
#        5. alert "ntfy: new HIGH/CRITICAL vulnerabilities" (NEW_VULNERABILITY,
#           NEW_VULNERABLE_DEPENDENCY, severity >= HIGH or known-exploited)
#        6. team "sbom-scanner" + API key -> DT_API_KEY in .env (only when the
#           current DT_API_KEY doesn't work)
#
#   scripts/deptrack-setup.sh test-alert
#       Sends the alert's test notification and checks it reached ntfy.
#
# Talks to the apiserver container on the docker bridge (DT_URL overrides).
# =============================================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env}"
TEMPLATE="${PROJECT_DIR}/infrastructure/dependency-track/ntfy-template.peb"
ADMIN_PW_FILE="${ADMIN_PW_FILE:-$HOME/.config/deptrack/admin-password}"
BASE_URL="https://deptrack.ops.markcheli.com"
PUBLISHER_NAME="ntfy"
RULE_NAME="ntfy: new HIGH/CRITICAL vulnerabilities"
SECRET_NAME="NTFY_AUTH_HEADER"
GITHUB_SECRET_NAME="GITHUB_ADVISORIES_TOKEN"
TEAM_NAME="sbom-scanner"
TEAM_PERMISSIONS=(BOM_UPLOAD PROJECT_CREATION_UPLOAD VIEW_PORTFOLIO PORTFOLIO_MANAGEMENT)
# OSV ecosystems: the distros our images are built on + the language
# ecosystems Syft finds in them. (DT's default is only Go/Maven/npm/NuGet/PyPI.)
OSV_ECOSYSTEMS='["Alpine", "Debian", "Ubuntu", "npm", "PyPI", "Go", "Maven", "crates.io", "RubyGems", "Packagist", "NuGet"]'
# Severity >= HIGH, or anything on a KEV list. Ternary keeps each branch on
# the subject type of its group.
FILTER_EXPRESSION='group == Group.GROUP_NEW_VULNERABILITY ? (subject.vulnerability.severity in ["CRITICAL", "HIGH"] || subject.vulnerability.is_kev) : subject.vulnerabilities.exists(v, v.severity in ["CRITICAL", "HIGH"] || v.is_kev)'

cmd="${1:-}"
[[ "$cmd" == init-admin || "$cmd" == apply || "$cmd" == test-alert ]] || {
    sed -n '2,31p' "$0"; exit 2; }

log() { echo "[deptrack-setup] $*"; }
die() { echo "[deptrack-setup] ERROR: $*" >&2; exit 1; }

env_get() {
    [[ -f "$ENV_FILE" ]] || return 0
    local v
    v=$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-)
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    printf '%s' "$v"
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
chmod 700 "$WORK"

if [[ -z "${DT_URL:-}" ]]; then
    ip=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}' deptrack-apiserver 2>/dev/null \
        | awk '$1 ~ /(^|_)infrastructure$/ && $2 != "" {print $2; exit}') || true
    [[ -n "${ip:-}" ]] || die "deptrack-apiserver is not running"
    DT_URL="http://${ip}:8080"
fi
DT_URL="${DT_URL%/}"

# api METHOD PATH [curl args...] -> HTTP status; body in $WORK/resp. Auth from $WORK/auth-hdr.
api() {
    local method="$1" path="$2" code; shift 2
    : > "${WORK}/resp"
    local auth=()
    [[ -f "${WORK}/auth-hdr" ]] && auth=(-H @"${WORK}/auth-hdr")
    code=$(curl -sS -o "${WORK}/resp" -w '%{http_code}' --max-time 60 -X "$method" \
        "${auth[@]}" "$@" "${DT_URL}${path}" 2>"${WORK}/curl-err") || true
    echo "${code:-000}"
}
# json EXPR -> EXPR evaluated on the last response body (`d`)
json() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
r = eval(sys.argv[2])
print("" if r is None else (json.dumps(r) if isinstance(r, (dict, list)) else r))' "${WORK}/resp" "$1"
}
expect() {  # expect "<what>" <code> <ok codes...>
    local what="$1" code="$2"; shift 2
    local ok
    for ok in "$@"; do [[ "$code" == "$ok" ]] && return 0; done
    die "${what}: HTTP ${code} $(head -c 400 "${WORK}/resp")"
}
urlenc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

wait_for_api() {
    local code
    for _ in $(seq 1 60); do
        code=$(api GET /api/version)
        [[ "$code" == 200 ]] && { log "API up: $(json "d.get('version')")"; return; }
        sleep 5
    done
    die "API not reachable at ${DT_URL} after 5 minutes"
}

login() {  # login USER PASSWORD -> writes bearer auth header file
    local code
    rm -f "${WORK}/auth-hdr"
    code=$(api POST /api/v1/user/login --data-urlencode "username=$1" --data-urlencode "password=$2")
    [[ "$code" == 200 ]] || return 1
    umask 077
    printf 'Authorization: Bearer %s\n' "$(cat "${WORK}/resp")" > "${WORK}/auth-hdr"
    umask 022
}

# ---------------------------------------------------------------------------
init_admin() {
    wait_for_api
    if login admin admin; then
        die "admin/admin logs in without a forced change; change it in the UI instead"
    fi
    if [[ -s "$ADMIN_PW_FILE" ]] && login admin "$(cat "$ADMIN_PW_FILE")"; then
        log "admin password already set (matches ${ADMIN_PW_FILE}); nothing to do"
        return
    fi
    local pw code
    pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
    code=$(api POST /api/v1/user/forceChangePassword --data-urlencode username=admin \
        --data-urlencode password=admin --data-urlencode "newPassword=${pw}" \
        --data-urlencode "confirmPassword=${pw}")
    expect "change default admin password (already changed? then use the password from 1Password)" "$code" 200
    mkdir -p "$(dirname "$ADMIN_PW_FILE")"
    ( umask 077; printf '%s\n' "$pw" > "$ADMIN_PW_FILE" )
    login admin "$pw" || die "new admin password does not log in"
    log "default admin password replaced. New password is in ${ADMIN_PW_FILE} (0600)."
    log "NEXT: save it in 1Password as 'Dependency-Track admin (deptrack.ops.markcheli.com)',"
    log "      run 'scripts/deptrack-setup.sh apply', then: shred -u ${ADMIN_PW_FILE}"
}

admin_login() {
    local pw="${DT_ADMIN_PASSWORD:-}"
    [[ -n "$pw" || ! -s "$ADMIN_PW_FILE" ]] || pw=$(cat "$ADMIN_PW_FILE")
    if [[ -z "$pw" && -t 0 ]]; then
        read -r -s -p "Dependency-Track admin password: " pw; echo
    fi
    [[ -n "$pw" ]] || die "no admin password (set DT_ADMIN_PASSWORD or run init-admin)"
    login admin "$pw" || die "admin login failed (wrong password, or run init-admin first)"
}

set_config_property() {  # group name value
    local code
    code=$(api POST /api/v1/configProperty -H 'Content-Type: application/json' \
        -d "$(python3 -c 'import json, sys; print(json.dumps({"groupName": sys.argv[1], "propertyName": sys.argv[2], "propertyValue": sys.argv[3]}))' "$1" "$2" "$3")")
    expect "config property $1/$2" "$code" 200 304
}

upsert_secret() {  # name value  (value goes via env + a 0600 file, never argv)
    local code
    ( umask 077; SECRET_NAME_="$1" SECRET_VALUE_="$2" python3 -c 'import json, os
print(json.dumps({"name": os.environ["SECRET_NAME_"], "value": os.environ["SECRET_VALUE_"]}))' > "${WORK}/secret.json" )
    code=$(api GET "/api/v2/secrets/$1")
    if [[ "$code" == 200 ]]; then
        python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); json.dump({"value": d["value"]}, open(sys.argv[1], "w"))' "${WORK}/secret.json"
        code=$(api PATCH "/api/v2/secrets/$1" -H 'Content-Type: application/json' -d @"${WORK}/secret.json")
        expect "update secret $1" "$code" 204 304
        log "secret $1 updated"
    else
        code=$(api POST /api/v2/secrets -H 'Content-Type: application/json' -d @"${WORK}/secret.json")
        expect "create secret $1" "$code" 201
        log "secret $1 created"
    fi
    rm -f "${WORK}/secret.json"
}

configure_source() {  # name json-merge-patch
    local name="$1" patch="$2" code path="/api/v2/extension-points/vuln-data-source/extensions/$1/config"
    code=$(api GET "$path")
    expect "read ${name} config" "$code" 200
    python3 -c 'import json, sys
cur = json.load(open(sys.argv[1]))["config"]
cur.update(json.loads(sys.argv[2]))
print(json.dumps({"config": cur}))' "${WORK}/resp" "$patch" > "${WORK}/cfg.json"
    code=$(api PUT "$path" -H 'Content-Type: application/json' -d @"${WORK}/cfg.json")
    expect "write ${name} config" "$code" 204 304
    log "vuln source ${name}: $(python3 -c 'import json, sys; c = json.load(open(sys.argv[1]))["config"]; c.pop("apiToken", None); print(json.dumps(c))' "${WORK}/cfg.json")"
    code=$(api POST "/api/v2/vuln-data-sources/${name}/mirror-runs")
    case "$code" in
        202) log "vuln source ${name}: mirror started" ;;
        409) log "vuln source ${name}: mirror already running" ;;
        *)   log "vuln source ${name}: could not start mirror (HTTP ${code}); it runs on schedule anyway" ;;
    esac
}

apply() {
    wait_for_api
    admin_login
    local ntfy_token github_token code pub_uuid rule_uuid team_uuid key perm

    # 1. Base URL
    set_config_property general base.url "$BASE_URL"
    log "base URL = ${BASE_URL}"

    # 2. Vulnerability sources
    configure_source osv "{\"enabled\": true, \"ecosystems\": ${OSV_ECOSYSTEMS}}"
    configure_source nvd '{"enabled": true}'
    github_token="${DT_GITHUB_TOKEN:-$(env_get DT_GITHUB_TOKEN)}"
    if [[ -n "$github_token" ]]; then
        upsert_secret "$GITHUB_SECRET_NAME" "$github_token"
        configure_source github "{\"enabled\": true, \"apiToken\": \"${GITHUB_SECRET_NAME}\"}"
    else
        log "vuln source github: skipped (no DT_GITHUB_TOKEN in .env; OSV already carries GitHub advisories)"
    fi

    # 3. ntfy auth secret
    ntfy_token="${NTFY_PUBLISH_TOKEN:-$(env_get NTFY_PUBLISH_TOKEN)}"
    [[ -n "$ntfy_token" ]] || die "NTFY_PUBLISH_TOKEN not set in ${ENV_FILE}"
    upsert_secret "$SECRET_NAME" "Bearer ${ntfy_token}"

    # 4. Publisher "ntfy": webhook extension + our template
    [[ -f "$TEMPLATE" ]] || die "missing ${TEMPLATE}"
    code=$(api GET /api/v1/notification/publisher)
    expect "list publishers" "$code" 200
    pub_uuid=$(json "next((p['uuid'] for p in d if p['name'] == '${PUBLISHER_NAME}'), None)")
    python3 - "$TEMPLATE" "$PUBLISHER_NAME" "$pub_uuid" > "${WORK}/pub.json" <<'EOF'
import json, sys
tpl, name, uuid = sys.argv[1], sys.argv[2], sys.argv[3]
body = {"name": name, "extensionName": "webhook", "templateMimeType": "application/json",
        "description": "ntfy JSON publish to topic homelab (83rr-poweredge scripts/deptrack-setup.sh)",
        "template": open(tpl).read()}
if uuid:
    body["uuid"] = uuid
print(json.dumps(body))
EOF
    if [[ -z "$pub_uuid" ]]; then
        code=$(api PUT /api/v1/notification/publisher -H 'Content-Type: application/json' -d @"${WORK}/pub.json")
        expect "create publisher" "$code" 201
        pub_uuid=$(json "d['uuid']")
        log "publisher ${PUBLISHER_NAME} created"
    else
        code=$(api POST /api/v1/notification/publisher -H 'Content-Type: application/json' -d @"${WORK}/pub.json")
        expect "update publisher" "$code" 200 304
        log "publisher ${PUBLISHER_NAME} template refreshed"
    fi

    # 5. Alert rule
    code=$(api GET /api/v1/notification/rule)
    expect "list rules" "$code" 200
    rule_uuid=$(json "next((r['uuid'] for r in d if r['name'] == '''${RULE_NAME}'''), None)")
    if [[ -z "$rule_uuid" ]]; then
        code=$(api PUT /api/v1/notification/rule -H 'Content-Type: application/json' \
            -d "{\"name\": \"${RULE_NAME}\", \"scope\": \"PORTFOLIO\", \"level\": \"INFORMATIONAL\", \"publisher\": {\"uuid\": \"${pub_uuid}\"}}")
        expect "create rule" "$code" 201
        rule_uuid=$(json "d['uuid']")
        log "alert rule created"
    fi
    python3 - "$rule_uuid" "$RULE_NAME" "$FILTER_EXPRESSION" "$SECRET_NAME" > "${WORK}/rule.json" <<'EOF'
import json, sys
uuid, name, expr, secret = sys.argv[1:5]
print(json.dumps({
    "uuid": uuid, "name": name, "scope": "PORTFOLIO", "level": "INFORMATIONAL",
    "enabled": True, "logSuccessfulPublish": True, "notifyChildren": True,
    "notifyOn": ["NEW_VULNERABILITY", "NEW_VULNERABLE_DEPENDENCY"],
    "filterExpression": expr,
    # authHeaderValue is a secret *reference* (x-secret-ref): the secret's name.
    "publisherConfig": json.dumps({"destinationUrl": "http://ntfy/",
                                   "authHeaderName": "Authorization",
                                   "authHeaderValue": secret}),
}))
EOF
    code=$(api POST /api/v1/notification/rule -H 'Content-Type: application/json' -d @"${WORK}/rule.json")
    expect "configure rule" "$code" 200 304
    log "alert rule '${RULE_NAME}' -> http://ntfy/ (topic homelab), groups NEW_VULNERABILITY + NEW_VULNERABLE_DEPENDENCY"

    # 6. Scanner team + key
    code=$(api GET /api/v1/team)
    expect "list teams" "$code" 200
    team_uuid=$(json "next((t['uuid'] for t in d if t['name'] == '${TEAM_NAME}'), None)")
    if [[ -z "$team_uuid" ]]; then
        code=$(api PUT /api/v1/team -H 'Content-Type: application/json' -d "{\"name\": \"${TEAM_NAME}\"}")
        expect "create team" "$code" 201
        team_uuid=$(json "d['uuid']")
        log "team ${TEAM_NAME} created"
    fi
    for perm in "${TEAM_PERMISSIONS[@]}"; do
        code=$(api POST "/api/v1/permission/${perm}/team/${team_uuid}")
        expect "grant ${perm}" "$code" 200 304
    done
    log "team ${TEAM_NAME}: ${TEAM_PERMISSIONS[*]}"

    key="${DT_API_KEY:-$(env_get DT_API_KEY)}"
    if [[ -n "$key" ]] && [[ "$(curl -s -o /dev/null -w '%{http_code}' -H @<(printf 'X-Api-Key: %s\n' "$key") "${DT_URL}/api/v1/team/self")" == 200 ]]; then
        log "DT_API_KEY in .env works; keeping it"
    else
        code=$(api PUT "/api/v1/team/${team_uuid}/key")
        expect "create API key" "$code" 201
        key=$(json "d['key']")
        python3 - "$ENV_FILE" "$key" <<'EOF'
import os, sys
path, key = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines() if os.path.exists(path) else []
lines = [l for l in lines if not l.startswith("DT_API_KEY=")] + [f"DT_API_KEY={key}"]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(tmp, os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600)
os.replace(tmp, path)
EOF
        log "new ${TEAM_NAME} API key written to ${ENV_FILE} as DT_API_KEY (team keys don't expire)"
    fi
    log "done. Test the alert path: scripts/deptrack-setup.sh test-alert"
}

test_alert() {
    wait_for_api
    admin_login
    local code rule_uuid start
    code=$(api GET /api/v1/notification/rule)
    expect "list rules" "$code" 200
    rule_uuid=$(json "next((r['uuid'] for r in d if r['name'] == '''${RULE_NAME}'''), None)")
    [[ -n "$rule_uuid" ]] || die "rule '${RULE_NAME}' not found; run apply first"
    start=$(date +%s)
    code=$(api POST "/api/v1/notification/publisher/test/${rule_uuid}")
    expect "send test notification" "$code" 200
    log "test notification dispatched; checking ntfy's cache..."
    sleep 10
    docker cp -q ntfy:/var/lib/ntfy/cache.db "${WORK}/cache.db" || die "cannot read ntfy cache"
    python3 - "${WORK}/cache.db" "$start" <<'EOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
rows = c.execute("SELECT title FROM messages WHERE topic='homelab' AND time >= ? AND tags LIKE '%dependency-track%'",
                 (int(sys.argv[2]) - 5,)).fetchall()
print("[deptrack-setup] ntfy received:", [r[0] for r in rows] or "NOTHING")
sys.exit(0 if rows else 1)
EOF
}

case "$cmd" in
    init-admin) init_admin ;;
    apply)      apply ;;
    test-alert) test_alert ;;
esac
