#!/usr/bin/env bash
# =============================================================================
# sbom-scan.sh — SBOM every running container and upload it to Dependency-Track
# =============================================================================
# For each running container: resolve its image + digest, generate a
# CycloneDX SBOM with Syft (scripts/install-syft.sh), and upload it to
# Dependency-Track as project <container name>, version "running": ONE stable
# version per container, so DT's portfolio history stays continuous and the
# dashboard shows the burn-down when an image is upgraded. The image ref and
# digest are kept on that version as project properties (group sbom-scan:
# image, digest, image-id, label) and tags (digest:<12 hex>, image:<ref>).
# Idempotent: a container whose digest matches the stored one is skipped, so
# only containers whose image changed are uploaded.
#
# Re-uploading into the same version keeps the findings, analyses and
# suppressions of every component that is still in the BOM (DT matches
# components by identity; checked on DT 5.2.1), so an image bump alerts only
# on findings that are actually new.
#
# Migration from the old model (one version "<tag>@<digest>" per image): when
# a container has no "running" version yet, its latest version is CLONED to
# "running" (components, findings, audit history), the BOM goes into the clone,
# any analysis the clone missed is copied by (component purl, vulnerability)
# with DT_TRIAGE_API_KEY, and every other version of the project is
# deactivated (not deleted; DT keeps their findings and audit history).
# The nightly run does this for any container it finds unmigrated;
# --migrate-stable does it for all of them at once and reports.
#
# After each run the current portfolio totals are appended as one JSON line to
# logs/deptrack-metrics.jsonl and written to logs/textfile/deptrack.prom for
# node-exporter's textfile collector (Grafana "Dependency-Track trend").
#
# Talks to the apiserver container directly on the docker bridge (no nginx).
# Needs: docker group, python3, curl, DT_API_KEY in .env (DT_TRIAGE_API_KEY
# for the analysis copy). No sudo. Logs to logs/sbom-scan.log; on any failure
# sends ONE short ntfy push (topic homelab) with the summary.
#
# Usage:
#   scripts/sbom-scan.sh                  # nightly run
#   scripts/sbom-scan.sh --dry-run        # show what would be uploaded (GETs only)
#   scripts/sbom-scan.sh --force          # re-upload even unchanged images
#   scripts/sbom-scan.sh --only NAME      # one container
#   scripts/sbom-scan.sh --no-notify      # don't push to ntfy on failure
#   scripts/sbom-scan.sh --migrate-stable [--dry-run]
#                                         # one-time: move every container that has no
#                                         # "running" version yet onto it (clone + upload +
#                                         # copy analyses + deactivate the old versions)
#   scripts/sbom-scan.sh --deactivate-superseded-only [--dry-run]
#                                         # no scanning: deactivate every non-latest
#                                         # version of every project (one-time cleanup)
#   scripts/sbom-scan.sh --deactivate-missing [--dry-run]
#                                         # no scanning: deactivate every version of every
#                                         # sbom-scan project whose name matches no existing
#                                         # container (after removing a service). Not in cron.
#                                         # If the container comes back, the next nightly
#                                         # run reactivates its "running" version.
#
# Cron (mcheli's crontab, 03:30 — after backup.sh at 02:00):
#   30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1
# =============================================================================

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env}"
LOG_FILE="${LOG_FILE:-${PROJECT_DIR}/logs/sbom-scan.log}"
METRICS_LOG="${METRICS_LOG:-${PROJECT_DIR}/logs/deptrack-metrics.jsonl}"
TEXTFILE_DIR="${TEXTFILE_DIR:-${PROJECT_DIR}/logs/textfile}"   # node-exporter textfile collector
SYFT="${SYFT:-$HOME/.local/bin/syft}"
CACHE_DIR="${CACHE_DIR:-$HOME/.cache/sbom-scan}"
DT_CONTAINER="${DT_CONTAINER:-deptrack-apiserver}"
PROCESS_TIMEOUT="${PROCESS_TIMEOUT:-900}"   # seconds to wait for DT to analyze one BOM
STABLE_VERSION="running"                    # the one DT version per container
NTFY_TOPIC="homelab"

DRY_RUN=false
FORCE=false
NOTIFY=true
ONLY=""
MIGRATE=false
DEACTIVATE_ONLY=false
DEACTIVATE_MISSING=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=true ;;
        --force)     FORCE=true ;;
        --no-notify) NOTIFY=false ;;
        --only)      ONLY="${2:?--only needs a container name}"; shift ;;
        --migrate-stable) MIGRATE=true ;;
        --deactivate-superseded-only) DEACTIVATE_ONLY=true ;;
        --deactivate-missing) DEACTIVATE_ONLY=true; DEACTIVATE_MISSING=true ;;
        -h|--help)   sed -n '2,60p' "$0"; exit 0 ;;
        *)           echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

mkdir -p "$(dirname "$LOG_FILE")" "$CACHE_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# One run at a time (cron + a manual run must not race on the same project).
if command -v flock >/dev/null 2>&1; then
    exec 9>"${CACHE_DIR}/lock"
    if ! flock -n 9; then
        log "another sbom-scan is running; exiting"
        exit 0
    fi
fi

WORK=$(mktemp -d "${CACHE_DIR}/run.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
chmod 700 "$WORK"

# Read KEY=value from .env without sourcing it (values may hold shell metachars).
env_get() {
    [[ -f "$ENV_FILE" ]] || return 0
    local v
    v=$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-)
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    printf '%s' "$v"
}

DT_API_KEY="${DT_API_KEY:-$(env_get DT_API_KEY)}"
DT_TRIAGE_API_KEY="${DT_TRIAGE_API_KEY:-$(env_get DT_TRIAGE_API_KEY)}"
NTFY_PUBLISH_TOKEN="${NTFY_PUBLISH_TOKEN:-$(env_get NTFY_PUBLISH_TOKEN)}"

# IP of a container on the compose "infrastructure" network (host -> bridge).
container_ip() {
    docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}' "$1" 2>/dev/null \
        | awk '$1 ~ /(^|_)infrastructure$/ && $2 != "" {print $2; exit}'
}

# Secrets go to curl via header files, never on the command line (ps-visible).
umask 077
printf 'X-Api-Key: %s\n' "$DT_API_KEY" > "${WORK}/dt-hdr"
printf 'X-Api-Key: %s\n' "$DT_TRIAGE_API_KEY" > "${WORK}/triage-hdr"
printf 'Authorization: Bearer %s\n' "$NTFY_PUBLISH_TOKEN" > "${WORK}/ntfy-hdr"
umask 022

FAILURES=()
fail() { FAILURES+=("$1"); log "ERROR: $1"; }

notify_failure() {
    [[ "$NOTIFY" == true && "$DRY_RUN" == false && ${#FAILURES[@]} -gt 0 ]] || return 0
    if [[ -z "$NTFY_PUBLISH_TOKEN" ]]; then
        log "NTFY_PUBLISH_TOKEN not set; cannot send failure push"
        return 0
    fi
    local body ip url sent=false
    body=$(python3 - "$NTFY_TOPIC" "${#FAILURES[@]}" "$TOTAL" "${FAILURES[@]}" <<'EOF'
import json, sys
topic, n, total, items = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
lines = items[:8] + ([f"... and {len(items) - 8} more"] if len(items) > 8 else [])
print(json.dumps({
    "topic": topic,
    "title": f"SBOM scan: {n} failure(s) of {total} container(s)",
    "message": "\n".join(lines) + "\nLog: ~/83rr-poweredge/logs/sbom-scan.log",
    "priority": 3,
    "tags": ["warning", "dependency-track"],
}))
EOF
)
    ip=$(container_ip ntfy)
    local urls=(${ip:+"http://${ip}/"} "https://ntfy.markcheli.com/")
    [[ -z "${NTFY_URL:-}" ]] || urls=("$NTFY_URL")
    for url in "${urls[@]}"; do
        if curl -fsS -o /dev/null --max-time 15 -H @"${WORK}/ntfy-hdr" \
                -H 'Content-Type: application/json' -d "$body" "$url"; then
            sent=true
            log "failure summary sent to ntfy (${url})"
            break
        fi
    done
    [[ "$sent" == true ]] || log "could not reach ntfy to send the failure summary"
}

finish() {
    local would=""
    [[ "$DRY_RUN" == true ]] && would="would be "
    if [[ "$DEACTIVATE_MISSING" == true ]]; then
        log "done: ${DEACTIVATED} version(s) of removed containers ${would}deactivated, ${#FAILURES[@]} failed"
    elif [[ "$DEACTIVATE_ONLY" == true ]]; then
        log "done: ${DEACTIVATED} superseded version(s) ${would}deactivated, ${#FAILURES[@]} failed"
    else
        [[ "$MIGRATE" == false ]] || log "migration: ${MIGRATED} container(s) ${would}moved to \"${STABLE_VERSION}\", ${ALREADY} already on it, ${STALE} project(s) without a container left as they are; analyses: ${ANALYSES_SRC} on the old versions, ${ANALYSES_COPIED} ${would}copied, ${ANALYSES_PRESENT} already present, ${ANALYSES_GONE} for components no longer in the image"
        log "done: ${UPLOADED} ${would}uploaded, ${SKIPPED} unchanged, ${DEACTIVATED} superseded ${would}deactivated, ${#FAILURES[@]} failed, ${TOTAL} containers"
    fi
    notify_failure
    [[ ${#FAILURES[@]} -eq 0 ]]
    exit $?
}

TOTAL=0
UPLOADED=0
SKIPPED=0
DEACTIVATED=0
MIGRATED=0
ALREADY=0
STALE=0
ANALYSES_SRC=0
ANALYSES_COPIED=0
ANALYSES_PRESENT=0
ANALYSES_GONE=0
CAN_DEACTIVATE=true
CAN_TRIAGE=false

log "=========================================="
MODE=""
if [[ "$DEACTIVATE_MISSING" == true ]]; then
    MODE=": deactivate projects of removed containers"
elif [[ "$DEACTIVATE_ONLY" == true ]]; then
    MODE=": deactivate superseded versions only"
elif [[ "$MIGRATE" == true ]]; then
    MODE=": migrate to one stable \"${STABLE_VERSION}\" version per container"
fi
log "sbom-scan starting${MODE}$( [[ "$DRY_RUN" == true ]] && echo ' (dry run)')"

# --- preflight -------------------------------------------------------------
if [[ "$DEACTIVATE_ONLY" == false && "$DRY_RUN" == false && ! -x "$SYFT" ]]; then
    fail "syft not found at ${SYFT} (run scripts/install-syft.sh)"
    finish
fi
# A dry run reads DT (GETs only) when it has a key; a plain dry scan can do
# without one (it then can't tell which containers changed).
DT_READ=true
if [[ -z "$DT_API_KEY" ]]; then
    if [[ "$DRY_RUN" == true && "$DEACTIVATE_ONLY" == false && "$MIGRATE" == false ]]; then
        DT_READ=false
        log "DT_API_KEY not set: dry run without Dependency-Track (every container listed as changed)"
    else
        fail "DT_API_KEY not set in ${ENV_FILE}"
        finish
    fi
fi
if [[ "$DT_READ" == false ]]; then
    DT_URL="http://dry-run.invalid"
elif [[ -z "${DT_URL:-}" ]]; then
    dt_ip=$(container_ip "$DT_CONTAINER")
    if [[ -z "$dt_ip" ]]; then
        fail "${DT_CONTAINER} is not running (no IP on the infrastructure network)"
        finish
    fi
    DT_URL="http://${dt_ip}:8080"
fi
DT_URL="${DT_URL%/}"
export SYFT_CHECK_FOR_APP_UPDATE=false
export TMPDIR="$WORK"   # syft unpacks image tarballs here; removed on exit

# dt METHOD PATH [curl args...] -> prints HTTP status; body in $WORK/resp
dt() {
    local method="$1" path="$2" code; shift 2
    : > "${WORK}/resp"
    code=$(curl -sS -o "${WORK}/resp" -w '%{http_code}' --max-time 300 -X "$method" \
        -H @"${WORK}/dt-hdr" "$@" "${DT_URL}${path}" 2>"${WORK}/curl-err") || true
    echo "${code:-000}"
}
# json EXPR -> evaluates EXPR on the last response (as `d`), prints the result
json() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
r = eval(sys.argv[2])
print("" if r is None else r)' "${WORK}/resp" "$1" 2>/dev/null
}
urlenc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

if [[ "$DT_READ" == true ]]; then
    code=$(dt GET /api/version)
    if [[ "$code" != 200 && "$code" != 401 && "$code" != 403 ]]; then
        fail "Dependency-Track API not reachable at ${DT_URL} (HTTP ${code} $(head -c 200 "${WORK}/curl-err"))"
        finish
    fi
    code=$(dt GET /api/v1/team/self)
    if [[ "$code" == 401 || "$code" == 403 ]]; then
        fail "Dependency-Track rejected DT_API_KEY (HTTP ${code}); recreate it with scripts/deptrack-setup.sh"
        finish
    fi
    # Deactivating and the image properties/tags need PORTFOLIO_MANAGEMENT (or
    # v5's PORTFOLIO_MANAGEMENT_UPDATE). Without it: warn, keep scanning, leave
    # superseded versions active (and unchanged images get re-uploaded).
    if [[ "$code" == 200 && "$(json "any(p.get('name') in ('PORTFOLIO_MANAGEMENT', 'PORTFOLIO_MANAGEMENT_UPDATE') for p in d.get('permissions') or [])")" != True ]]; then
        CAN_DEACTIVATE=false
        log "WARNING: DT_API_KEY's team lacks PORTFOLIO_MANAGEMENT: superseded versions stay active and keep counting in the portfolio metrics (scripts/deptrack-setup.sh apply grants it)"
    fi
    # Copying analyses needs VULNERABILITY_ANALYSIS: the triage key has it.
    if [[ -n "$DT_TRIAGE_API_KEY" ]] && [[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 \
            -H @"${WORK}/triage-hdr" "${DT_URL}/api/v1/team/self" 2>/dev/null)" == 200 ]]; then
        CAN_TRIAGE=true
    elif [[ "$MIGRATE" == true ]]; then
        fail "--migrate-stable needs a working DT_TRIAGE_API_KEY (scripts/deptrack-setup.sh triage-key) to check and copy analyses"
        finish
    fi
fi

# --- per-container work ----------------------------------------------------
# image_info NAME -> "tag digest image_id image_ref" (digest is sha256:<hex>)
image_info() {
    local name="$1" cfg_image image_id ref tag digest last repo
    cfg_image=$(docker inspect -f '{{.Config.Image}}' "$name") || return 1
    image_id=$(docker inspect -f '{{.Image}}' "$name") || return 1
    ref="${cfg_image%%@*}"
    last="${ref##*/}"
    if [[ "$last" == *:* ]]; then
        tag="${last##*:}"; repo="${ref%:*}"
    elif [[ "$cfg_image" == *@* ]]; then
        tag="digest"; repo="$ref"
    else
        tag="latest"; repo="$ref"
    fi
    if [[ "$cfg_image" == *@sha256:* ]]; then
        digest="sha256:${cfg_image##*@sha256:}"
    else
        # Prefer the registry digest of this repo; fall back to any, then to
        # the local image ID (locally built images have no RepoDigests).
        digest=$(docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$image_id" 2>/dev/null \
            | awk -v r="$repo" -F@ '$1 == r || $1 == "docker.io/" r || $1 == "docker.io/library/" r {print $2; exit}')
        [[ -n "$digest" ]] || digest=$(docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$image_id" 2>/dev/null \
            | awk -F@ 'NF == 2 {print $2; exit}')
        [[ -n "$digest" ]] || digest="$image_id"
    fi
    echo "$tag $digest $image_id $cfg_image"
}

# copy_analyses SRC_UUID DST_UUID|"" SRC_LABEL -> copies every analysis
# (state, justification, response, details, suppression) of version SRC onto
# the same finding (component purl + vulnerability source/ID) in DST, where
# DST has none yet. Never overwrites an analysis DST already has, so it is
# safe to repeat. Without DST (dry run) it only counts. Prints
# "<analysed on src> <copied> <already present> <component gone> <failed>".
copy_analyses() {
    python3 - "$DT_URL" "${WORK}/triage-hdr" "$1" "$2" "$3" <<'EOF'
import json, sys, urllib.parse, urllib.request
url, hdr, src, dst, label = sys.argv[1:6]
key = open(hdr).read().split(":", 1)[1].strip()

def call(method, path, body=None):
    req = urllib.request.Request(url + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Api-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        t = r.read()
        return json.loads(t) if t else None

def findings(project):  # paged: DT returns 100 per page by default
    out, page = [], 1
    while True:
        batch = call("GET", f"/api/v1/finding/project/{project}?suppressed=true&pageSize=500&pageNumber={page}")
        out += batch
        if len(batch) < 500:
            return out
        page += 1

def ident(f):
    c, v = f["component"], f["vulnerability"]
    return (c.get("purl") or f'{c.get("group") or ""}/{c.get("name")}@{c.get("version") or ""}',
            v.get("source"), v.get("vulnId"))

def analysed(f):
    a = f.get("analysis") or {}
    return a.get("state") not in (None, "NOT_SET") or bool(a.get("isSuppressed"))

old = {ident(f): f for f in findings(src) if analysed(f)}
if not dst:
    print(len(old), 0, 0, 0, 0)
    sys.exit(0)
new = {ident(f): f for f in findings(dst)}
copied = present = gone = failed = 0
for k, f in old.items():
    n = new.get(k)
    if n is None:
        gone += 1
        continue
    if analysed(n):
        present += 1
        continue
    a = f.get("analysis") or {}
    body = {"analysisState": a.get("state"), "isSuppressed": bool(a.get("isSuppressed"))}
    try:
        full = call("GET", "/api/v1/analysis?" + urllib.parse.urlencode({
            "project": src, "component": f["component"]["uuid"], "vulnerability": f["vulnerability"]["uuid"]})) or {}
        for field in ("analysisState", "analysisJustification", "analysisResponse", "analysisDetails"):
            if full.get(field) is not None:
                body[field] = full[field]
        body["isSuppressed"] = bool(full.get("isSuppressed", body["isSuppressed"]))
    except Exception:
        pass   # fall back to the state/suppression from the finding itself
    body.update(project=dst, component=n["component"]["uuid"], vulnerability=n["vulnerability"]["uuid"],
                comment=f"copied from version {label} by sbom-scan.sh")
    try:
        call("PUT", "/api/v1/analysis", body)
        copied += 1
    except Exception as e:
        failed += 1
        print(f"could not copy {k}: {e}", file=sys.stderr)
print(len(old), copied, present, gone, failed)
EOF
}

# set_image_meta UUID IMAGE_REF DIGEST IMAGE_ID LABEL -> active + latest, tags
# digest:<12 hex> and image:<ref> (others kept), properties sbom-scan/{image,
# digest,image-id,label}. The stored digest is what the next run compares.
set_image_meta() {
    local uuid="$1" ref="${2%%@*}" digest="$3" image_id="$4" label="$5" short body code prop val
    short="${digest#sha256:}"; short="${short:0:12}"
    code=$(dt GET "/api/v1/project/${uuid}")
    [[ "$code" == 200 ]] || { log "  WARNING: could not read project ${uuid} to tag it (HTTP ${code})"; return 1; }
    body=$(python3 - "${WORK}/resp" "$short" "$ref" <<'EOF'
import json, sys
p, short, ref = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
tags = [t["name"] for t in p.get("tags") or [] if not t["name"].startswith(("digest:", "image:"))]
tags = sorted(set(tags) | {"sbom-scan", f"digest:{short}", f"image:{ref.lower()}"})
print(json.dumps({"active": True, "isLatest": True, "tags": [{"name": t} for t in tags]}))
EOF
)
    code=$(dt PATCH "/api/v1/project/${uuid}" -H 'Content-Type: application/json' -d "$body")
    [[ "$code" == 200 || "$code" == 304 ]] || { log "  WARNING: could not set latest/tags on ${uuid} (HTTP ${code})"; return 1; }
    for prop in "image=${ref}" "digest=${digest}" "image-id=${image_id}" "label=${label}"; do
        val=$(python3 -c 'import json, sys; n, v = sys.argv[1].split("=", 1); print(json.dumps({"groupName": "sbom-scan",
            "propertyName": n, "propertyValue": v, "propertyType": "STRING"}))' "$prop")
        code=$(dt PUT "/api/v1/project/${uuid}/property" -H 'Content-Type: application/json' -d "$val")
        [[ "$code" == 201 ]] && continue
        code=$(dt POST "/api/v1/project/${uuid}/property" -H 'Content-Type: application/json' -d "$val")
        [[ "$code" == 200 || "$code" == 304 ]] || { log "  WARNING: could not set property ${prop%%=*} on ${uuid} (HTTP ${code})"; return 1; }
    done
}

# stored_digest UUID -> the sbom-scan/digest property of a version ("" if none)
stored_digest() {
    [[ "$(dt GET "/api/v1/project/${1}/property")" == 200 ]] || return 0
    json "next((p.get('propertyValue') for p in d if p.get('groupName') == 'sbom-scan' and p.get('propertyName') == 'digest'), '')"
}

# report_copy SRC DST LABEL NAME -> runs copy_analyses, logs, adds to the totals
report_copy() {
    local out n_src n_copied n_present n_gone n_failed
    if [[ "$CAN_TRIAGE" == false ]]; then
        log "  ${4}: WARNING: no working DT_TRIAGE_API_KEY, analyses not checked (the clone normally carries them)"
        return
    fi
    if ! out=$(copy_analyses "$1" "$2" "$3" 2>"${WORK}/copy-err"); then
        fail "${4}: could not compare analyses with ${3}: $(tail -n 1 "${WORK}/copy-err" | cut -c1-200)"
        return
    fi
    read -r n_src n_copied n_present n_gone n_failed <<<"$out"
    ANALYSES_SRC=$((ANALYSES_SRC + n_src)); ANALYSES_COPIED=$((ANALYSES_COPIED + n_copied))
    ANALYSES_PRESENT=$((ANALYSES_PRESENT + n_present)); ANALYSES_GONE=$((ANALYSES_GONE + n_gone))
    if [[ -z "$2" ]]; then
        log "  ${4}: ${n_src} analysis/analyses on ${3} to carry over"
    else
        log "  ${4}: analyses from ${3}: ${n_src} total, ${n_copied} copied, ${n_present} already present, ${n_gone} for components no longer in the image"
        (( n_failed == 0 )) || fail "${4}: ${n_failed} analysis/analyses could not be copied from ${3}"
    fi
}

declare -A SBOM_FOR_IMAGE=()   # image_id -> generated SBOM file (shared images scan once)

scan_container() {
    local name="$1" info tag digest image_id image_ref short label bom
    local stable_uuid="" stable_active=true src_uuid="" src_version="" code target_uuid token status cloned=false waited

    info=$(image_info "$name") || { fail "${name}: docker inspect failed"; return; }
    read -r tag digest image_id image_ref <<<"$info"
    short="${digest#sha256:}"; short="${short:0:12}"
    label="${tag}@${short}"

    if [[ "$DT_READ" == true ]]; then
        code=$(dt GET /api/v1/project/lookup -G --data-urlencode "name=${name}" --data-urlencode "version=${STABLE_VERSION}")
        if [[ "$code" == 200 ]]; then
            stable_uuid=$(json "d.get('uuid')")
            [[ "$(json "d.get('active', True)")" == True ]] || stable_active=false
        elif [[ "$code" != 404 ]]; then
            fail "${name}: project lookup failed (HTTP ${code})"
            return
        fi
    fi

    if [[ -n "$stable_uuid" ]]; then
        if [[ "$MIGRATE" == true ]]; then
            log "  ${name}: already on \"${STABLE_VERSION}\""
            ALREADY=$((ALREADY + 1))
            SKIPPED=$((SKIPPED + 1))
            return
        fi
        if [[ "$FORCE" == false && "$(stored_digest "$stable_uuid")" == "$digest" ]]; then
            log "  ${name} ${label}: unchanged, skipping"
            SKIPPED=$((SKIPPED + 1))
            # Container came back after --deactivate-missing: count it again.
            if [[ "$stable_active" == false ]]; then
                if [[ "$DRY_RUN" == true ]]; then
                    log "  ${name}: would reactivate \"${STABLE_VERSION}\""
                elif set_image_meta "$stable_uuid" "$image_ref" "$digest" "$image_id" "$label"; then
                    log "  ${name}: reactivated \"${STABLE_VERSION}\" (running again)"
                fi
            fi
            return
        fi
    elif [[ "$DT_READ" == true ]]; then
        # Not migrated yet: the old model's latest version is the source.
        code=$(dt GET "/api/v1/project/latest/$(urlenc "$name")")
        if [[ "$code" == 200 ]]; then
            src_uuid=$(json "d.get('uuid')")
            src_version=$(json "d.get('version')")
        fi
    fi

    if [[ "$DRY_RUN" == true ]]; then
        if [[ -n "$stable_uuid" ]]; then
            log "  ${name} ${label}: would scan ${image_id:7:12} and upload into \"${STABLE_VERSION}\""
        elif [[ -n "$src_uuid" ]]; then
            log "  ${name} ${label}: would clone ${src_version} -> \"${STABLE_VERSION}\", scan ${image_id:7:12} and upload"
            [[ "$CAN_TRIAGE" == false ]] || report_copy "$src_uuid" "" "$src_version" "$name"
            deactivate_superseded "" "$name"
            MIGRATED=$((MIGRATED + 1))
        else
            log "  ${name} ${label}: would scan ${image_id:7:12} and upload as new project"
        fi
        UPLOADED=$((UPLOADED + 1))
        return
    fi

    # Syft: SBOM of the exact local image the container runs (by image ID).
    bom="${SBOM_FOR_IMAGE[$image_id]:-}"
    if [[ -z "$bom" ]]; then
        bom="${WORK}/${image_id#sha256:}.cdx.json"
        log "  ${name} ${label}: generating SBOM"
        # By image ID first (exactly what runs); by the configured ref as a
        # fallback, which resolves to the same local image.
        if ! "$SYFT" scan "docker:${image_id}" -q -o "cyclonedx-json=${bom}" \
                --source-name "$name" --source-version "$label" >"${WORK}/syft.log" 2>&1 \
           && ! "$SYFT" scan "docker:${image_ref}" -q -o "cyclonedx-json=${bom}" \
                --source-name "$name" --source-version "$label" >>"${WORK}/syft.log" 2>&1; then
            fail "${name}: syft failed: $(tail -n 3 "${WORK}/syft.log" | tr '\n' ' ' | cut -c1-200)"
            rm -f "$bom"
            return
        fi
        SBOM_FOR_IMAGE[$image_id]="$bom"
    fi
    # Per-container copy: containers sharing an image share the scan, but each
    # BOM names its own container in metadata.component. Its version is the
    # image label; DT keeps the project version ("running") as it is.
    if ! python3 - "$bom" "${WORK}/${name}.cdx.json.gz" "$name" "$label" <<'EOF'; then
import gzip, json, sys
src, dst, name, version = sys.argv[1:5]
bom = json.load(open(src))
comp = bom.setdefault("metadata", {}).setdefault("component", {"type": "container"})
comp["name"], comp["version"] = name, version
with gzip.open(dst, "wt") as f:
    json.dump(bom, f)
EOF
        fail "${name}: could not prepare the SBOM for upload"
        return
    fi
    bom="${WORK}/${name}.cdx.json"

    # Migration: clone the old latest version to "running" so its findings and
    # audit decisions carry over and don't re-alert.
    target_uuid="$stable_uuid"
    if [[ -z "$target_uuid" && -n "$src_uuid" ]]; then
        code=$(dt POST "/api/v2/projects/${src_uuid}/clone" -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"version": sys.argv[1], "version_is_latest": True,
                "includes": ["COMPONENTS", "FINDINGS", "FINDINGS_AUDIT_HISTORY", "POLICY_VIOLATIONS",
                             "POLICY_VIOLATIONS_AUDIT_HISTORY", "PROPERTIES", "TAGS", "ACL"]}))' "$STABLE_VERSION")")
        if [[ "$code" == 201 ]]; then
            target_uuid=$(json "d.get('uuid')")
            cloned=true
            log "  ${name}: cloned ${src_version} -> \"${STABLE_VERSION}\""
        else
            log "  ${name}: clone failed (HTTP ${code}), uploading as a fresh version instead (analyses copied afterwards)"
        fi
    fi

    if [[ -n "$target_uuid" ]]; then
        code=$(dt POST /api/v1/bom -F "project=${target_uuid}" \
            -F "bom=@${bom}.gz;type=application/gzip")
    else
        code=$(dt POST /api/v1/bom -F "projectName=${name}" -F "projectVersion=${STABLE_VERSION}" \
            -F "autoCreate=true" -F "isLatest=true" -F "projectTags=sbom-scan" \
            -F "bom=@${bom}.gz;type=application/gzip")
    fi
    if [[ "$code" != 200 ]]; then
        fail "${name}: BOM upload failed (HTTP ${code}: $(head -c 200 "${WORK}/resp"))"
        if [[ "$cloned" == true ]]; then
            # Don't leave a "running" clone with the old BOM (the next run
            # would store nothing and retry, but the clone would count); put
            # the latest flag back on the old version.
            dt DELETE "/api/v1/project/${target_uuid}" >/dev/null
            dt PATCH "/api/v1/project/${src_uuid}" -H 'Content-Type: application/json' -d '{"isLatest": true}' >/dev/null
        fi
        return
    fi
    token=$(json "d.get('token')")
    target_uuid=$(json "d.get('projectUuid')")

    # Wait for import + analysis, so the run's result means something.
    waited=0
    status=""
    while (( waited < PROCESS_TIMEOUT )); do
        sleep 5; waited=$((waited + 5))
        code=$(dt GET "/api/v1/event/token/${token}")
        [[ "$code" == 200 ]] || continue
        status=$(json "d.get('status') or ('DONE' if not d.get('processing') else 'RUNNING')")
        [[ "$status" == COMPLETED || "$status" == FAILED || "$status" == DONE ]] && break
    done
    case "$status" in
        COMPLETED|DONE)
            log "  ${name} ${label}: uploaded into \"${STABLE_VERSION}\" and analyzed (${waited}s)"
            UPLOADED=$((UPLOADED + 1)) ;;
        FAILED)
            fail "${name}: Dependency-Track failed to process the BOM (token ${token})"
            return ;;
        *)
            log "  ${name} ${label}: uploaded; analysis still running after ${PROCESS_TIMEOUT}s"
            UPLOADED=$((UPLOADED + 1)) ;;
    esac

    # Recorded only after a good upload: a failed one is retried next run.
    set_image_meta "$target_uuid" "$image_ref" "$digest" "$image_id" "$label" \
        || log "  ${name}: WARNING: image properties not stored; the next run uploads it again"
    if [[ -n "$src_uuid" ]]; then
        report_copy "$src_uuid" "$target_uuid" "$src_version" "$name"
        MIGRATED=$((MIGRATED + 1))
    fi
    deactivate_superseded "$target_uuid" "$name"
}

# list_projects [NAME] -> every version (inactive included, all pages) in
# $WORK/projects.json. On failure prints the HTTP status and returns 1.
list_projects() {
    local page=1 code n args=()
    [[ -z "${1:-}" ]] || args=(--data-urlencode "name=$1")
    echo '[]' > "${WORK}/projects.json"
    while :; do
        code=$(dt GET /api/v1/project -G "${args[@]}" --data-urlencode "excludeInactive=false" \
            --data-urlencode "pageSize=100" --data-urlencode "pageNumber=${page}")
        [[ "$code" == 200 ]] || { echo "HTTP ${code}"; return 1; }
        n=$(python3 - "${WORK}/projects.json" "${WORK}/resp" <<'EOF'
import json, sys
acc, new = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
json.dump(acc + new, open(sys.argv[1], "w"))
print(len(new))
EOF
) || { echo "unreadable project list"; return 1; }
        (( n < 100 )) && return 0
        page=$((page + 1))
    done
}

# superseded CURRENT [NAME] -> "uuid name version latest" for every active
# version of a project other than CURRENT (the version just uploaded) and,
# without CURRENT, other than its latest. Projects with no active latest
# version are left alone.
superseded() {
    python3 - "${WORK}/projects.json" "$@" <<'EOF'
import json, sys
path, current, names = sys.argv[1], sys.argv[2], sys.argv[3:]
by_name = {}
for p in json.load(open(path)):
    if not names or p.get("name") in names:
        by_name.setdefault(p.get("name"), []).append(p)
for name, versions in sorted(by_name.items()):
    keep = [p for p in versions if p["uuid"] == current] or \
           [p for p in versions if p.get("isLatest") and p.get("active", True)]
    if not keep:
        continue
    for p in versions:
        if p.get("active", True) and p["uuid"] != keep[0]["uuid"]:
            print(p["uuid"], name, p.get("version", ""), keep[0].get("version", ""))
EOF
}

# deactivate_superseded [CURRENT_UUID NAME] -> active=false on every
# superseded version of NAME (or of every project). Deactivated, not deleted:
# DT drops inactive projects from the portfolio metrics but keeps their
# findings and audit history. Idempotent: an inactive version isn't selected
# again. In a dry run with NAME but no CURRENT, lists every active version of
# NAME (all of them would be superseded by the new "running" version).
deactivate_superseded() {
    local current="${1:-}" name="${2:-}" err code uuid pname ver latest
    if [[ "$CAN_DEACTIVATE" == false ]]; then
        if [[ -n "$name" ]]; then
            log "  ${name}: WARNING: superseded versions left active (no PORTFOLIO_MANAGEMENT)"
        else
            fail "cannot deactivate: DT_API_KEY's team lacks PORTFOLIO_MANAGEMENT"
        fi
        return
    fi
    if ! err=$(list_projects "$name"); then
        if [[ -n "$name" ]]; then
            log "  ${name}: WARNING: could not list versions to deactivate superseded ones (${err})"
        else
            fail "could not list projects (${err})"
        fi
        return
    fi
    if [[ "$DRY_RUN" == true && -n "$name" && -z "$current" ]]; then
        current="dry-run-${STABLE_VERSION}"
        python3 - "${WORK}/projects.json" "$name" "$STABLE_VERSION" > "${WORK}/superseded" <<'EOF' || return
import json, sys
for p in json.load(open(sys.argv[1])):
    if p.get("name") == sys.argv[2] and p.get("active", True):
        print(p["uuid"], p["name"], p.get("version", ""), sys.argv[3])
EOF
    else
        superseded "$current" ${name:+"$name"} > "${WORK}/superseded" || return
    fi
    while read -r uuid pname ver latest; do
        [[ -n "$uuid" ]] || continue
        if [[ "$DRY_RUN" == true ]]; then
            log "  ${pname}: would deactivate ${ver} (latest: ${latest})"
            DEACTIVATED=$((DEACTIVATED + 1))
            continue
        fi
        code=$(dt PATCH "/api/v1/project/${uuid}" -H 'Content-Type: application/json' -d '{"active": false}')
        if [[ "$code" == 200 || "$code" == 304 ]]; then
            log "  ${pname}: deactivated superseded version ${ver} (latest: ${latest})"
            DEACTIVATED=$((DEACTIVATED + 1))
        elif [[ "$code" == 401 || "$code" == 403 ]]; then
            CAN_DEACTIVATE=false
            log "  ${pname}: WARNING: DT refused to deactivate ${ver} (HTTP ${code}); the key needs PORTFOLIO_MANAGEMENT. Superseded versions left active."
            [[ -n "$name" ]] || fail "DT refused deactivation (HTTP ${code})"
            return
        else
            log "  ${pname}: could not deactivate ${ver} (HTTP ${code}: $(head -c 200 "${WORK}/resp"))"
            [[ -n "$name" ]] || fail "${pname}: could not deactivate ${ver} (HTTP ${code})"
        fi
    done < "${WORK}/superseded"
}

# missing RUNNING_NAMES_FILE -> "uuid name version" for every active version of
# every sbom-scan project whose name is not an existing container.
missing() {
    python3 - "${WORK}/projects.json" "$1" <<'EOF'
import json, sys
running = set(open(sys.argv[2]).read().split())
for p in sorted(json.load(open(sys.argv[1])), key=lambda p: (p.get("name", ""), p.get("version", ""))):
    tags = {t.get("name") for t in p.get("tags") or []}
    if "sbom-scan" in tags and p.get("name") not in running and p.get("active", True):
        print(p["uuid"], p.get("name"), p.get("version", ""))
EOF
}

# deactivate_missing -> active=false on every version of every project whose
# container is gone (a removed service). Deactivated, not deleted; if the
# container comes back, scan_container reactivates its "running" version.
deactivate_missing() {
    local err code uuid pname ver
    if [[ "$CAN_DEACTIVATE" == false ]]; then
        fail "cannot deactivate: DT_API_KEY's team lacks PORTFOLIO_MANAGEMENT"
        return
    fi
    # -a: a stopped container (mid-upgrade, crashed) still exists; only a
    # removed one counts as missing.
    docker ps -a --format '{{.Names}}' > "${WORK}/running" || { fail "docker ps failed"; return; }
    # Never read "no containers" as "every container was removed".
    if [[ ! -s "${WORK}/running" ]]; then
        fail "docker ps -a returned no containers (docker group / daemon?); nothing deactivated"
        return
    fi
    if ! err=$(list_projects); then
        fail "could not list projects (${err})"
        return
    fi
    missing "${WORK}/running" > "${WORK}/missing" || { fail "could not read the project list"; return; }
    while read -r uuid pname ver; do
        [[ -n "$uuid" ]] || continue
        if [[ "$DRY_RUN" == true ]]; then
            log "  ${pname}: would deactivate ${ver} (no such container)"
            DEACTIVATED=$((DEACTIVATED + 1))
            continue
        fi
        code=$(dt PATCH "/api/v1/project/${uuid}" -H 'Content-Type: application/json' -d '{"active": false}')
        if [[ "$code" == 200 || "$code" == 304 ]]; then
            log "  ${pname}: deactivated ${ver} (no such container)"
            DEACTIVATED=$((DEACTIVATED + 1))
        else
            fail "${pname}: could not deactivate ${ver} (HTTP ${code}: $(head -c 200 "${WORK}/resp"))"
        fi
    done < "${WORK}/missing"
}

# report_stale RUNNING_NAMES -> logs every active project with no running
# container (migration leaves those alone; --deactivate-missing handles them).
report_stale() {
    local err
    if ! err=$(list_projects); then
        fail "could not list projects (${err})"
        return
    fi
    while read -r pname ver; do
        [[ -n "$pname" ]] || continue
        log "  ${pname} ${ver}: no running container, left as it is (scripts/sbom-scan.sh --deactivate-missing if it was removed)"
        STALE=$((STALE + 1))
    done < <(python3 - "${WORK}/projects.json" "$1" <<'EOF'
import json, sys
running = set(open(sys.argv[2]).read().split())
for p in sorted(json.load(open(sys.argv[1])), key=lambda p: p.get("name", "")):
    if p.get("active", True) and p.get("isLatest") and p.get("name") not in running:
        print(p.get("name"), p.get("version", ""))
EOF
)
}

# record_trend -> DT's current portfolio totals as one JSON line in
# $METRICS_LOG and as gauges in $TEXTFILE_DIR/deptrack.prom (node-exporter).
# Our own time series: DT's dashboard history only sums the projects that are
# active today (see docs/dependency-track.md). Best effort: never fails the run.
record_trend() {
    local code out waited=0
    # Recompute first so tonight's uploads are in it (needs PORTFOLIO_MANAGEMENT;
    # without it the numbers are from DT's last periodic refresh).
    code=$(dt GET /api/v1/metrics/portfolio/refresh)
    [[ "$code" == 200 ]] && sleep 30
    code=$(dt GET /api/v1/metrics/portfolio/current)
    while [[ "$code" != 200 ]] && (( waited < 60 )); do
        sleep 10; waited=$((waited + 10))
        code=$(dt GET /api/v1/metrics/portfolio/current)
    done
    if [[ "$code" != 200 ]]; then
        log "WARNING: could not read /metrics/portfolio/current (HTTP ${code}); trend not recorded"
        return 0
    fi
    mkdir -p "$(dirname "$METRICS_LOG")" "$TEXTFILE_DIR" 2>/dev/null
    if ! out=$(python3 - "${WORK}/resp" "$METRICS_LOG" "$TEXTFILE_DIR" <<'EOF'
import json, os, sys, time
cur, log_path, textdir = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
fields = ["critical", "high", "medium", "low", "unassigned", "inheritedRiskScore", "suppressed",
          "vulnerabilities", "projects", "vulnerableProjects", "kev", "policyViolationsTotal"]
now = time.time()
rec = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))}
rec.update({f: cur.get(f) for f in fields})
with open(log_path, "a") as f:
    f.write(json.dumps(rec) + "\n")
names = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "unassigned": "unassigned"}
lines = ["# HELP deptrack_portfolio_findings Unsuppressed findings in active DT projects, by severity (sbom-scan.sh).",
         "# TYPE deptrack_portfolio_findings gauge"]
lines += [f'deptrack_portfolio_findings{{severity="{v}"}} {cur.get(k) or 0}' for k, v in names.items()]
for metric, key, help_ in [
        ("deptrack_portfolio_inherited_risk_score", "inheritedRiskScore", "DT inherited risk score of the active portfolio."),
        ("deptrack_portfolio_suppressed", "suppressed", "Suppressed findings (FP / not affected) in active DT projects."),
        ("deptrack_portfolio_projects", "projects", "Active DT projects."),
        ("deptrack_portfolio_vulnerable_projects", "vulnerableProjects", "Active DT projects with at least one finding."),
        ("deptrack_portfolio_kev", "kev", "Findings in CISA's known-exploited list."),
        ("deptrack_portfolio_policy_violations", "policyViolationsTotal", "Policy violations in active DT projects.")]:
    lines += [f"# HELP {metric} {help_}", f"# TYPE {metric} gauge", f"{metric} {cur.get(key) or 0}"]
lines += ["# HELP deptrack_portfolio_last_update_timestamp_seconds When sbom-scan.sh last recorded these.",
          "# TYPE deptrack_portfolio_last_update_timestamp_seconds gauge",
          f"deptrack_portfolio_last_update_timestamp_seconds {int(now)}"]
tmp = os.path.join(textdir, ".deptrack.prom.tmp")
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(tmp, 0o644)
os.replace(tmp, os.path.join(textdir, "deptrack.prom"))   # atomic for the collector
print(f"critical {rec['critical']}, high {rec['high']}, risk {rec['inheritedRiskScore']}, suppressed {rec['suppressed']}")
EOF
); then
        log "WARNING: could not write the trend to ${METRICS_LOG} / ${TEXTFILE_DIR}"
        return 0
    fi
    log "trend recorded: ${out}"
}

if [[ "$DEACTIVATE_MISSING" == true ]]; then
    deactivate_missing
    finish
fi
if [[ "$DEACTIVATE_ONLY" == true ]]; then
    deactivate_superseded
    finish
fi

mapfile -t CONTAINERS < <(docker ps --format '{{.Names}}' | sort)
if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
    fail "docker ps returned no running containers (docker group / daemon?)"
    finish
fi
for c in "${CONTAINERS[@]}"; do
    [[ -z "$ONLY" || "$c" == "$ONLY" ]] || continue
    TOTAL=$((TOTAL + 1))
    scan_container "$c"
done
if [[ -n "$ONLY" && $TOTAL -eq 0 ]]; then
    fail "--only ${ONLY}: no running container with that name"
fi
if [[ "$MIGRATE" == true && -z "$ONLY" ]]; then
    printf '%s\n' "${CONTAINERS[@]}" > "${WORK}/running"
    report_stale "${WORK}/running"
fi
if [[ "$DRY_RUN" == false && -z "$ONLY" ]]; then
    record_trend
fi

finish
