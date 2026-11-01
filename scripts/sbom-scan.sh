#!/usr/bin/env bash
# =============================================================================
# sbom-scan.sh — SBOM every running container and upload it to Dependency-Track
# =============================================================================
# For each running container: resolve its image + digest, generate a
# CycloneDX SBOM with Syft (scripts/install-syft.sh), and upload it to
# Dependency-Track as project <container name>, version "<tag>@<short digest>",
# marked latest. Idempotent: a version that already exists is skipped, so
# only containers whose image changed are uploaded.
#
# A new version is a clone of the previous latest (components, findings and
# audit decisions carried over) before its BOM goes in, so an image bump
# alerts only on findings that are actually new, not on every old CVE again.
# After each upload every other version of the project (not latest) is
# deactivated, not deleted: DT leaves inactive projects out of the portfolio
# metrics but keeps their history. Needs PORTFOLIO_MANAGEMENT; without it the
# script logs a warning and leaves them active.
#
# Talks to the apiserver container directly on the docker bridge (no nginx).
# Needs: docker group, python3, curl, DT_API_KEY in .env. No sudo.
# Logs to logs/sbom-scan.log; on any failure sends ONE short ntfy push
# (topic homelab) with the summary.
#
# Usage:
#   scripts/sbom-scan.sh                  # nightly run
#   scripts/sbom-scan.sh --dry-run        # show what would be uploaded
#   scripts/sbom-scan.sh --force          # re-upload even unchanged images
#   scripts/sbom-scan.sh --only NAME      # one container
#   scripts/sbom-scan.sh --no-notify      # don't push to ntfy on failure
#   scripts/sbom-scan.sh --deactivate-superseded-only [--dry-run]
#                                         # no scanning: deactivate every non-latest
#                                         # version of every project (one-time cleanup)
#   scripts/sbom-scan.sh --deactivate-missing [--dry-run]
#                                         # no scanning: deactivate every version of every
#                                         # sbom-scan project whose name matches no existing
#                                         # container (after removing a service). Not in cron.
#                                         # If the container comes back, the next nightly
#                                         # run reactivates its version as latest.
#
# Cron (mcheli's crontab, 03:30 — after backup.sh at 02:00):
#   30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1
# =============================================================================

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env}"
LOG_FILE="${LOG_FILE:-${PROJECT_DIR}/logs/sbom-scan.log}"
SYFT="${SYFT:-$HOME/.local/bin/syft}"
CACHE_DIR="${CACHE_DIR:-$HOME/.cache/sbom-scan}"
DT_CONTAINER="${DT_CONTAINER:-deptrack-apiserver}"
PROCESS_TIMEOUT="${PROCESS_TIMEOUT:-900}"   # seconds to wait for DT to analyze one BOM
NTFY_TOPIC="homelab"

DRY_RUN=false
FORCE=false
NOTIFY=true
ONLY=""
DEACTIVATE_ONLY=false
DEACTIVATE_MISSING=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=true ;;
        --force)     FORCE=true ;;
        --no-notify) NOTIFY=false ;;
        --only)      ONLY="${2:?--only needs a container name}"; shift ;;
        --deactivate-superseded-only) DEACTIVATE_ONLY=true ;;
        --deactivate-missing) DEACTIVATE_ONLY=true; DEACTIVATE_MISSING=true ;;
        -h|--help)   sed -n '2,43p' "$0"; exit 0 ;;
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
NTFY_PUBLISH_TOKEN="${NTFY_PUBLISH_TOKEN:-$(env_get NTFY_PUBLISH_TOKEN)}"

# IP of a container on the compose "infrastructure" network (host -> bridge).
container_ip() {
    docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}' "$1" 2>/dev/null \
        | awk '$1 ~ /(^|_)infrastructure$/ && $2 != "" {print $2; exit}'
}

# Secrets go to curl via header files, never on the command line (ps-visible).
umask 077
printf 'X-Api-Key: %s\n' "$DT_API_KEY" > "${WORK}/dt-hdr"
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
    if [[ "$DEACTIVATE_MISSING" == true ]]; then
        log "done: ${DEACTIVATED} version(s) of removed containers $( [[ "$DRY_RUN" == true ]] && echo 'to deactivate' || echo 'deactivated'), ${#FAILURES[@]} failed"
    elif [[ "$DEACTIVATE_ONLY" == true ]]; then
        log "done: ${DEACTIVATED} superseded version(s) $( [[ "$DRY_RUN" == true ]] && echo 'to deactivate' || echo 'deactivated'), ${#FAILURES[@]} failed"
    else
        log "done: ${UPLOADED} uploaded, ${SKIPPED} unchanged, ${DEACTIVATED} superseded deactivated, ${#FAILURES[@]} failed, ${TOTAL} containers"
    fi
    notify_failure
    [[ ${#FAILURES[@]} -eq 0 ]]
    exit $?
}

TOTAL=0
UPLOADED=0
SKIPPED=0
DEACTIVATED=0
CAN_DEACTIVATE=true

log "=========================================="
MODE=""
if [[ "$DEACTIVATE_MISSING" == true ]]; then
    MODE=": deactivate projects of removed containers"
elif [[ "$DEACTIVATE_ONLY" == true ]]; then
    MODE=": deactivate superseded versions only"
fi
log "sbom-scan starting${MODE}$( [[ "$DRY_RUN" == true ]] && echo ' (dry run)')"

# --- preflight -------------------------------------------------------------
if [[ "$DEACTIVATE_ONLY" == false && ! -x "$SYFT" ]]; then
    fail "syft not found at ${SYFT} (run scripts/install-syft.sh)"
    finish
fi
if [[ -z "$DT_API_KEY" && ( "$DRY_RUN" == false || "$DEACTIVATE_ONLY" == true ) ]]; then
    fail "DT_API_KEY not set in ${ENV_FILE}"
    finish
fi
# A dry scan doesn't touch DT; a dry deactivation reads it (GETs only).
if [[ -z "${DT_URL:-}" && "$DRY_RUN" == true && "$DEACTIVATE_ONLY" == false ]]; then
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

if [[ "$DRY_RUN" == false || "$DEACTIVATE_ONLY" == true ]]; then
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
    # Deactivating needs PORTFOLIO_MANAGEMENT (or v5's PORTFOLIO_MANAGEMENT_UPDATE).
    # Without it: warn, keep scanning, leave superseded versions active.
    if [[ "$code" == 200 && "$(json "any(p.get('name') in ('PORTFOLIO_MANAGEMENT', 'PORTFOLIO_MANAGEMENT_UPDATE') for p in d.get('permissions') or [])")" != True ]]; then
        CAN_DEACTIVATE=false
        log "WARNING: DT_API_KEY's team lacks PORTFOLIO_MANAGEMENT: superseded versions stay active and keep counting in the portfolio metrics (scripts/deptrack-setup.sh apply grants it)"
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

declare -A SBOM_FOR_IMAGE=()   # image_id -> generated SBOM file (shared images scan once)

scan_container() {
    local name="$1" info tag digest image_id image_ref short version bom
    local prev_uuid="" prev_version="" code target_uuid token status cloned=false waited

    info=$(image_info "$name") || { fail "${name}: docker inspect failed"; return; }
    read -r tag digest image_id image_ref <<<"$info"
    short="${digest#sha256:}"; short="${short:0:12}"
    version="${tag}@${short}"

    if [[ "$DRY_RUN" == false && "$FORCE" == false ]]; then
        code=$(dt GET /api/v1/project/lookup -G --data-urlencode "name=${name}" --data-urlencode "version=${version}")
        if [[ "$code" == 200 ]]; then
            log "  ${name} ${version}: unchanged, skipping"
            SKIPPED=$((SKIPPED + 1))
            # Rolled back to an older image: its version exists but was
            # deactivated; make it the active latest again.
            if [[ "$(json "d.get('active', True) and d.get('isLatest')")" != True ]]; then
                target_uuid=$(json "d.get('uuid')")
                code=$(dt PATCH "/api/v1/project/${target_uuid}" -H 'Content-Type: application/json' \
                    -d '{"active": true, "isLatest": true}')
                if [[ "$code" == 200 || "$code" == 304 ]]; then
                    log "  ${name}: reactivated ${version} as latest (running again)"
                    deactivate_superseded "$target_uuid" "$name"
                else
                    log "  ${name}: WARNING: could not reactivate ${version} as latest (HTTP ${code})"
                fi
            fi
            return
        elif [[ "$code" != 404 ]]; then
            fail "${name}: project lookup failed (HTTP ${code})"
            return
        fi
    fi

    if [[ "$DRY_RUN" == true ]]; then
        log "  ${name} ${version}: would scan ${image_id:7:12} and upload"
        return
    fi

    # Syft: SBOM of the exact local image the container runs (by image ID).
    bom="${SBOM_FOR_IMAGE[$image_id]:-}"
    if [[ -z "$bom" ]]; then
        bom="${WORK}/${image_id#sha256:}.cdx.json"
        log "  ${name} ${version}: generating SBOM"
        # By image ID first (exactly what runs); by the configured ref as a
        # fallback, which resolves to the same local image.
        if ! "$SYFT" scan "docker:${image_id}" -q -o "cyclonedx-json=${bom}" \
                --source-name "$name" --source-version "$version" >"${WORK}/syft.log" 2>&1 \
           && ! "$SYFT" scan "docker:${image_ref}" -q -o "cyclonedx-json=${bom}" \
                --source-name "$name" --source-version "$version" >>"${WORK}/syft.log" 2>&1; then
            fail "${name}: syft failed: $(tail -n 3 "${WORK}/syft.log" | tr '\n' ' ' | cut -c1-200)"
            rm -f "$bom"
            return
        fi
        SBOM_FOR_IMAGE[$image_id]="$bom"
    fi
    # Per-container copy: containers sharing an image share the scan, but each
    # BOM names its own container in metadata.component.
    if ! python3 - "$bom" "${WORK}/${name}.cdx.json.gz" "$name" "$version" <<'EOF'; then
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

    # Clone the previous latest version so carried-over findings don't re-alert.
    code=$(dt GET "/api/v1/project/latest/$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$name")")
    if [[ "$code" == 200 ]]; then
        prev_uuid=$(json "d.get('uuid')")
        prev_version=$(json "d.get('version')")
    fi
    target_uuid=""
    if [[ -n "$prev_uuid" && "$prev_version" != "$version" ]]; then
        code=$(dt POST "/api/v2/projects/${prev_uuid}/clone" -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"version": sys.argv[1], "version_is_latest": True,
                "includes": ["COMPONENTS", "FINDINGS", "FINDINGS_AUDIT_HISTORY", "POLICY_VIOLATIONS",
                             "POLICY_VIOLATIONS_AUDIT_HISTORY", "PROPERTIES", "TAGS", "ACL"]}))' "$version")")
        if [[ "$code" == 201 ]]; then
            target_uuid=$(json "d.get('uuid')")
            cloned=true
            log "  ${name}: cloned ${prev_version} -> ${version}"
        else
            log "  ${name}: clone failed (HTTP ${code}), uploading as a fresh version instead"
        fi
    fi

    if [[ -n "$target_uuid" ]]; then
        code=$(dt POST /api/v1/bom -F "project=${target_uuid}" \
            -F "bom=@${bom}.gz;type=application/gzip")
    else
        code=$(dt POST /api/v1/bom -F "projectName=${name}" -F "projectVersion=${version}" \
            -F "autoCreate=true" -F "isLatest=true" -F "projectTags=sbom-scan" \
            -F "bom=@${bom}.gz;type=application/gzip")
    fi
    if [[ "$code" != 200 ]]; then
        fail "${name}: BOM upload failed (HTTP ${code}: $(head -c 200 "${WORK}/resp"))"
        if [[ "$cloned" == true ]]; then
            # Don't leave a clone with the old BOM under the new version (the
            # next run would skip it); put the latest flag back on the old one.
            dt DELETE "/api/v1/project/${target_uuid}" >/dev/null
            dt PATCH "/api/v1/project/${prev_uuid}" -H 'Content-Type: application/json' -d '{"isLatest": true}' >/dev/null
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
            log "  ${name} ${version}: uploaded and analyzed (${waited}s)"
            UPLOADED=$((UPLOADED + 1)) ;;
        FAILED)
            fail "${name}: Dependency-Track failed to process the BOM (token ${token})"
            return ;;
        *)
            log "  ${name} ${version}: uploaded; analysis still running after ${PROCESS_TIMEOUT}s"
            UPLOADED=$((UPLOADED + 1)) ;;
    esac

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

# superseded CURRENT [NAME] -> "uuid name version latest" for every active,
# non-latest version of a project that also has an active latest version.
# Never CURRENT (the version just uploaded).
superseded() {
    python3 - "${WORK}/projects.json" "$@" <<'EOF'
import json, sys
path, current, names = sys.argv[1], sys.argv[2], sys.argv[3:]
by_name = {}
for p in json.load(open(path)):
    if not names or p.get("name") in names:
        by_name.setdefault(p.get("name"), []).append(p)
for name, versions in sorted(by_name.items()):
    latest = [p for p in versions if p.get("isLatest") and p.get("active", True)]
    if not latest:
        continue
    for p in versions:
        if p.get("active", True) and not p.get("isLatest") and p["uuid"] != current:
            print(p["uuid"], name, p.get("version", ""), latest[0].get("version", ""))
EOF
}

# deactivate_superseded [CURRENT_UUID NAME] -> active=false on every
# superseded version of NAME (or of every project). Deactivated, not deleted:
# DT drops inactive projects from the portfolio metrics but keeps their
# history. Idempotent: an inactive version isn't selected again.
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
    superseded "$current" ${name:+"$name"} > "${WORK}/superseded" || return
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
# container comes back, scan_container's rollback path reactivates its version.
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

finish
