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
#        5. policy "alert: KEV, or HIGH/CRITICAL with EPSS >= 0.1 on
#           internet-exposed" (one CEL condition, see POLICY_EXPRESSION) and
#           the push rule "ntfy: KEV or high-EPSS on internet-exposed", which
#           fires only on that policy's violations. EPSS isn't in DT 5.2's
#           notification schema, so a plain rule filter can't test it; the
#           policy engine can. The rule is created DISABLED and keeps its
#           on/off state on re-runs, except that creating the policy (or
#           renaming the old rule) turns it off once, so the first evaluation
#           of existing findings doesn't push them all.
#        6. scheduled rule "ntfy: weekly vulnerability digest"
#           (NEW_VULNERABILITIES_SUMMARY, Saturdays, skipped when nothing is new)
#        7. team "sbom-scanner" + API key -> DT_API_KEY in .env (only when the
#           current DT_API_KEY doesn't work)
#
#   scripts/deptrack-setup.sh triage-key
#       Needs the admin password (as for apply). Team "triage" with
#       VIEW_PORTFOLIO, VIEW_VULNERABILITY, VULNERABILITY_ANALYSIS + API key
#       -> DT_TRIAGE_API_KEY in .env (only when the current one doesn't work).
#       For the weekly sweep: read findings and record analyses.
#
#   scripts/deptrack-setup.sh status        mirror runs, project count, alert state
#   scripts/deptrack-setup.sh alerts on|off turn the push rule on/off (not the digest)
#   scripts/deptrack-setup.sh test-alert    send both rules' test notifications
#                                           and check they reached ntfy
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
RULE_NAME="ntfy: KEV or high-EPSS on internet-exposed"
# Earlier names of the push rule: found and renamed in place, not duplicated.
LEGACY_RULE_NAMES=("ntfy: new HIGH/CRITICAL vulnerabilities")
DIGEST_RULE_NAME="ntfy: weekly vulnerability digest"
# Saturday 13:00 UTC (8 or 9 am ET), ahead of the Saturday security sweep.
DIGEST_CRON="0 13 * * 6"
SECRET_NAME="NTFY_AUTH_HEADER"
GITHUB_SECRET_NAME="GITHUB_ADVISORIES_TOKEN"
TEAM_NAME="sbom-scanner"
TEAM_PERMISSIONS=(BOM_UPLOAD PROJECT_CREATION_UPLOAD VIEW_PORTFOLIO PORTFOLIO_MANAGEMENT)
TRIAGE_TEAM_NAME="triage"
TRIAGE_PERMISSIONS=(VIEW_PORTFOLIO VIEW_VULNERABILITY VULNERABILITY_ANALYSIS)
# OSV ecosystems: the distros our images are built on + the language
# ecosystems Syft finds in them. (DT's default is only Go/Maven/npm/NuGet/PyPI.)
OSV_ECOSYSTEMS='["Alpine", "Debian", "Ubuntu", "npm", "PyPI", "Go", "Maven", "crates.io", "RubyGems", "Packagist", "NuGet"]'
# DT projects (= container names) reachable from the internet: a public vhost
# in infrastructure/nginx/conf.d/production.conf, or a port forwarded on the
# router (minecraft 25565, asa 7777/udp). Keep in sync when that changes.
INTERNET_PROJECTS=(nginx personal-website flask-api cookbook plex tallied tallied-demo
    tasks tasks-demo uptime-kuma ntfy seafile minecraft asa)
POLICY_NAME="alert: KEV, or HIGH/CRITICAL with EPSS >= 0.1 on internet-exposed"
# Policy CEL (component scope; `vulns` already excludes suppressed findings):
# any KEV finding, or a HIGH/CRITICAL one with EPSS >= 0.1 in an internet-
# exposed project. Re-evaluated on every BOM upload, so a CVE that is added to
# KEV, or whose EPSS rises, later still alerts.
POLICY_EXPRESSION="vulns.exists(v, v.is_kev || (project.name in $(printf '%s\n' "${INTERNET_PROJECTS[@]}" \
    | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read().split()))') \
&& v.severity in [\"CRITICAL\", \"HIGH\"] && has(v.epss_score) && v.epss_score >= 0.1))"
# The push rule only listens to POLICY_VIOLATION; this keeps it to our policy.
FILTER_EXPRESSION="group == Group.GROUP_POLICY_VIOLATION && subject.policy_violation.condition.policy.name == \"${POLICY_NAME}\""

cmd="${1:-}"
case "$cmd" in
    init-admin|apply|alerts|status|test-alert|triage-key) ;;
    *) sed -n '2,47p' "$0"; exit 2 ;;
esac

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
# json EXPR [ARG...] -> EXPR evaluated on the last response body (`d`); extra
# ARGs are sys.argv[3:] (pass names that way instead of quoting them into EXPR)
json() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
r = eval(sys.argv[2])
print("" if r is None else (json.dumps(r) if isinstance(r, (dict, list)) else r))' "${WORK}/resp" "$@"
}
expect() {  # expect "<what>" <code> <ok codes...>
    local what="$1" code="$2"; shift 2
    local ok
    for ok in "$@"; do [[ "$code" == "$ok" ]] && return 0; done
    die "${what}: HTTP ${code} $(head -c 400 "${WORK}/resp")"
}
# secret_file NAME VALUE -> path of a 0600 file holding VALUE (no newline), for
# curl's --data-urlencode name@file: keeps passwords out of argv (ps-visible).
secret_file() {
    ( umask 077; printf '%s' "$2" > "${WORK}/sec-$1" )
    echo "${WORK}/sec-$1"
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
    code=$(api POST /api/v1/user/login --data-urlencode "username=$1" \
        --data-urlencode "password@$(secret_file login-pw "$2")")
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
        --data-urlencode password=admin --data-urlencode "newPassword@$(secret_file new-pw "$pw")" \
        --data-urlencode "confirmPassword@$(secret_file new-pw "$pw")")
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

write_rule() {  # write_rule push|digest UUID true|false  (full update of that rule)
    local code
    python3 - "$1" "$2" "$3" "$RULE_NAME" "$FILTER_EXPRESSION" "$DIGEST_RULE_NAME" "$DIGEST_CRON" \
        "$SECRET_NAME" > "${WORK}/rule.json" <<'EOF'
import json, sys
kind, uuid, enabled, name, expr, digest_name, digest_cron, secret = sys.argv[1:9]
rule = {
    "uuid": uuid, "scope": "PORTFOLIO", "level": "INFORMATIONAL",
    "enabled": enabled == "true", "logSuccessfulPublish": True, "notifyChildren": True,
    # authHeaderValue is a secret *reference* (x-secret-ref): the secret's name.
    "publisherConfig": json.dumps({"destinationUrl": "http://ntfy/",
                                   "authHeaderName": "Authorization",
                                   "authHeaderValue": secret}),
}
if kind == "push":
    rule.update(name=name, notifyOn=["POLICY_VIOLATION"], filterExpression=expr)
else:
    rule.update(name=digest_name, notifyOn=["NEW_VULNERABILITIES_SUMMARY"],
                scheduleCron=digest_cron, scheduleSkipUnchanged=True)
print(json.dumps(rule))
EOF
    code=$(api POST /api/v1/notification/rule -H 'Content-Type: application/json' -d @"${WORK}/rule.json")
    expect "configure ${1} rule" "$code" 200 304
}

# rule_lookup NAME... -> "uuid enabled name" of the first rule with one of these
# names (empty if none), from the rule list in the last response.
rule_lookup() {
    json "next((f\"{r['uuid']} {str(r.get('enabled', False)).lower()} {r['name']}\"
               for n in sys.argv[3:] for r in d if r['name'] == n), None)" "$@"
}

find_rule() {  # find_rule NAME... -> rule uuid or dies
    local code found
    code=$(api GET /api/v1/notification/rule)
    expect "list rules" "$code" 200
    found=$(rule_lookup "$@")
    [[ -n "$found" ]] || die "rule '$1' not found; run apply first"
    echo "${found%% *}"
}

alerts() {  # alerts on|off
    [[ "${1:-}" == on || "${1:-}" == off ]] || die "usage: $0 alerts on|off"
    wait_for_api
    admin_login
    local rule_uuid
    rule_uuid=$(find_rule "$RULE_NAME")
    write_rule push "$rule_uuid" "$([[ "$1" == on ]] && echo true || echo false)"
    log "alert rule '${RULE_NAME}' is now $1"
}

ensure_policy() {  # -> "created" or "existing" (on stdout); creates/updates policy + its one condition
    local code policy_uuid cond_uuid state
    code=$(api GET /api/v1/policy -G --data-urlencode pageSize=500)
    expect "list policies" "$code" 200
    policy_uuid=$(json "next((p['uuid'] for p in d if p['name'] == sys.argv[3]), None)" "$POLICY_NAME")
    cond_uuid=$(json "next((c['uuid'] for p in d if p['name'] == sys.argv[3] for c in p.get('policyConditions') or []), None)" "$POLICY_NAME")
    state=existing
    python3 - "$POLICY_NAME" "$policy_uuid" > "${WORK}/policy.json" <<'EOF'
import json, sys
name, uuid = sys.argv[1:3]
body = {"name": name, "operator": "ANY", "violationState": "WARN",
        "onlyLatestProjectVersion": True, "includeChildren": False, "invertTagMatch": False}
if uuid:
    body["uuid"] = uuid
print(json.dumps(body))
EOF
    if [[ -z "$policy_uuid" ]]; then
        code=$(api PUT /api/v1/policy -H 'Content-Type: application/json' -d @"${WORK}/policy.json")
        expect "create policy" "$code" 201
        policy_uuid=$(json "d['uuid']")
        state=created
    else
        code=$(api POST /api/v1/policy -H 'Content-Type: application/json' -d @"${WORK}/policy.json")
        expect "update policy" "$code" 200 304
    fi
    python3 - "$POLICY_EXPRESSION" "$cond_uuid" > "${WORK}/cond.json" <<'EOF'
import json, sys
expr, uuid = sys.argv[1:3]
body = {"subject": "EXPRESSION", "operator": "MATCHES", "value": expr, "violationType": "SECURITY"}
if uuid:
    body["uuid"] = uuid
print(json.dumps(body))
EOF
    if [[ -z "$cond_uuid" ]]; then
        code=$(api PUT "/api/v1/policy/${policy_uuid}/condition" -H 'Content-Type: application/json' -d @"${WORK}/cond.json")
        expect "create policy condition (a 400 lists CEL errors)" "$code" 201
    else
        code=$(api POST /api/v1/policy/condition -H 'Content-Type: application/json' -d @"${WORK}/cond.json")
        expect "update policy condition (a 400 lists CEL errors)" "$code" 200
    fi
    echo "$state"
}

ensure_team() {  # ensure_team NAME PERMISSION... -> team uuid; creates the team, grants the permissions
    local name="$1" code team_uuid perm; shift
    code=$(api GET /api/v1/team)
    expect "list teams" "$code" 200
    team_uuid=$(json "next((t['uuid'] for t in d if t['name'] == sys.argv[3]), None)" "$name")
    if [[ -z "$team_uuid" ]]; then
        code=$(api PUT /api/v1/team -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"name": sys.argv[1]}))' "$name")")
        expect "create team ${name}" "$code" 201
        team_uuid=$(json "d['uuid']")
        log "team ${name} created" >&2
    fi
    for perm in "$@"; do
        code=$(api POST "/api/v1/permission/${perm}/team/${team_uuid}")
        expect "grant ${perm} to ${name}" "$code" 200 304
    done
    log "team ${name}: $*" >&2
    echo "$team_uuid"
}

# ensure_team_key TEAM_NAME TEAM_UUID ENV_VAR: keeps the key in .env if it
# authenticates as that team, else creates a new key and writes it there.
ensure_team_key() {
    local name="$1" team_uuid="$2" var="$3" key code
    key="${!var:-$(env_get "$var")}"
    if [[ -n "$key" ]]; then
        code=$(curl -s -o "${WORK}/self" -w '%{http_code}' -H @<(printf 'X-Api-Key: %s\n' "$key") "${DT_URL}/api/v1/team/self")
        if [[ "$code" == 200 ]] && python3 -c 'import json, sys; sys.exit(json.load(open(sys.argv[1])).get("name") != sys.argv[2])' "${WORK}/self" "$name"; then
            log "${var} in .env works for team ${name}; keeping it"
            return
        fi
    fi
    code=$(api PUT "/api/v1/team/${team_uuid}/key")
    expect "create API key for ${name}" "$code" 201
    key=$(json "d['key']")
    DT_NEW_KEY_="$key" python3 - "$ENV_FILE" "$var" <<'EOF'
import os, sys
path, var, key = sys.argv[1], sys.argv[2], os.environ["DT_NEW_KEY_"]
lines = open(path).read().splitlines() if os.path.exists(path) else []
lines = [l for l in lines if not l.startswith(f"{var}=")] + [f"{var}={key}"]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(tmp, os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600)
os.replace(tmp, path)
EOF
    log "new ${name} API key written to ${ENV_FILE} as ${var} (team keys don't expire)"
}

triage_key() {
    wait_for_api
    admin_login
    local team_uuid
    team_uuid=$(ensure_team "$TRIAGE_TEAM_NAME" "${TRIAGE_PERMISSIONS[@]}")
    ensure_team_key "$TRIAGE_TEAM_NAME" "$team_uuid" DT_TRIAGE_API_KEY
}

status() {
    wait_for_api
    admin_login
    local src code
    for src in osv nvd github; do
        code=$(api GET "/api/v2/vuln-data-sources/${src}/mirror-runs/latest")
        if [[ "$code" == 200 ]]; then
            log "mirror ${src}: $(json "d.get('status')") $(json "d.get('failure_reason') or ''")"
        else
            log "mirror ${src}: no run (HTTP ${code})"
        fi
    done
    code=$(api GET /api/v1/project -G --data-urlencode pageSize=500)
    expect "list projects" "$code" 200
    log "projects: $(json "len(d)") ($(json "sum(1 for p in d if p.get('isLatest'))") latest versions)"
    code=$(api GET /api/v1/notification/rule)
    log "push rule enabled: $(json "next((r.get('enabled') for r in d if r['name'] == sys.argv[3]), 'missing')" "$RULE_NAME")"
    code=$(api GET /api/v1/notification/rule -G --data-urlencode triggerType=SCHEDULE)
    log "digest rule enabled: $(json "next((r.get('enabled') for r in d if r['name'] == sys.argv[3]), 'missing')" "$DIGEST_RULE_NAME")"
    code=$(api GET /api/v1/policy -G --data-urlencode pageSize=500)
    log "alert policy: $(json "'present' if any(p['name'] == sys.argv[3] for p in d) else 'missing'" "$POLICY_NAME")"
}

apply() {
    wait_for_api
    admin_login
    local ntfy_token github_token code pub_uuid rule_uuid rule_name team_uuid enabled found policy_state

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

    # 5. Alert policy + push rule
    policy_state=$(ensure_policy)
    log "policy '${POLICY_NAME}' ${policy_state}"
    code=$(api GET /api/v1/notification/rule)
    expect "list rules" "$code" 200
    found=$(rule_lookup "$RULE_NAME" "${LEGACY_RULE_NAMES[@]}")
    if [[ -z "$found" ]]; then
        code=$(api PUT /api/v1/notification/rule -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"name": sys.argv[1], "scope": "PORTFOLIO", "level": "INFORMATIONAL", "publisher": {"uuid": sys.argv[2]}}))' "$RULE_NAME" "$pub_uuid")")
        expect "create rule" "$code" 201
        rule_uuid=$(json "d['uuid']")
        # Created OFF: the first evaluation would otherwise push every
        # existing match. Turn on with `alerts on` after the next scan.
        enabled=false
        log "push rule created (disabled until 'alerts on')"
    else
        read -r rule_uuid enabled rule_name <<<"$found"
        if [[ "$rule_name" != "$RULE_NAME" || "$policy_state" == created ]]; then
            # Same reason: a new policy (or the switch from the old severity
            # rule) means the next scan evaluates every existing finding.
            [[ "$enabled" == true ]] && log "push rule turned OFF until the next scan has run; then: $0 alerts on"
            enabled=false
        fi
    fi
    write_rule push "$rule_uuid" "$enabled"
    log "push rule '${RULE_NAME}' -> http://ntfy/ (topic homelab), POLICY_VIOLATION of '${POLICY_NAME}', enabled=${enabled}"

    # 6. Weekly digest (scheduled rule; DT creates these disabled)
    code=$(api GET /api/v1/notification/rule)
    expect "list rules" "$code" 200
    found=$(rule_lookup "$DIGEST_RULE_NAME")
    if [[ -z "$found" ]]; then
        code=$(api PUT /api/v1/notification/rule/scheduled -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"name": sys.argv[1], "scope": "PORTFOLIO", "level": "INFORMATIONAL", "publisher": {"uuid": sys.argv[2]}}))' "$DIGEST_RULE_NAME" "$pub_uuid")")
        expect "create digest rule" "$code" 201
        rule_uuid=$(json "d['uuid']")
        enabled=true
        log "digest rule created"
    else
        read -r rule_uuid enabled _ <<<"$found"
    fi
    write_rule digest "$rule_uuid" "$enabled"
    log "digest rule '${DIGEST_RULE_NAME}' cron '${DIGEST_CRON}' (UTC), NEW_VULNERABILITIES_SUMMARY, enabled=${enabled}"

    # 7. Scanner team + key
    team_uuid=$(ensure_team "$TEAM_NAME" "${TEAM_PERMISSIONS[@]}")
    ensure_team_key "$TEAM_NAME" "$team_uuid" DT_API_KEY
    log "done. Test the alert path: scripts/deptrack-setup.sh test-alert"
}

test_alert() {
    wait_for_api
    admin_login
    local code push_uuid digest_uuid start
    push_uuid=$(find_rule "$RULE_NAME")
    digest_uuid=$(find_rule "$DIGEST_RULE_NAME")
    start=$(date +%s)
    code=$(api POST "/api/v1/notification/publisher/test/${push_uuid}")
    expect "send push rule test notification" "$code" 200
    code=$(api POST "/api/v1/notification/publisher/test/${digest_uuid}")
    expect "send digest rule test notification" "$code" 200
    log "test notifications dispatched (push + digest); checking ntfy's cache..."
    sleep 10
    docker cp -q ntfy:/var/lib/ntfy/cache.db "${WORK}/cache.db" || die "cannot read ntfy cache"
    # If the cache runs in WAL mode, the newest messages are still in the -wal file.
    docker cp -q ntfy:/var/lib/ntfy/cache.db-wal "${WORK}/cache.db-wal" 2>/dev/null || true
    python3 - "${WORK}/cache.db" "$start" <<'EOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
rows = c.execute("SELECT title FROM messages WHERE topic='homelab' AND time >= ? AND tags LIKE '%dependency-track%'",
                 (int(sys.argv[2]) - 5,)).fetchall()
print("[deptrack-setup] ntfy received:", [r[0] for r in rows] or "NOTHING")
sys.exit(0 if len(rows) >= 2 else 1)  # one per rule
EOF
}

case "$cmd" in
    init-admin) init_admin ;;
    apply)      apply ;;
    alerts)     alerts "${2:-}" ;;
    status)     status ;;
    test-alert) test_alert ;;
    triage-key) triage_key ;;
esac
