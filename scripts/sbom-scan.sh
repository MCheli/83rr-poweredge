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
# on findings that are actually new. A component whose VERSION changed (say
# openssl moved to a newer Ubuntu build) is a new component without them, so
# the analysed findings of "running" are snapshotted before each re-upload and
# replayed afterwards. Every analysis copy (replay, clone, migration) matches
# the same purl first, then the same purl at another version: a suppressed
# NOT_AFFECTED/FALSE_POSITIVE is carried to the one newer-or-equal build
# (comment "re-verify"); anything else (a downgrade, several candidates, other
# states) is logged as "needs review" and pushed to ntfy.
#
# Migration from the old model (one version "<tag>@<digest>" per image), ONLY
# with --migrate-stable: for a container with no "running" version yet, its
# latest version is CLONED to
# "running" (components, findings, audit history), the BOM goes into the clone,
# any analysis the clone missed is copied by (component purl, vulnerability)
# with DT_TRIAGE_API_KEY, and every other version of the project is
# deactivated (not deleted; DT keeps their findings and audit history).
# Idempotent: a re-run copies analyses from, and deactivates, any old version
# still active (a run that died half-way). The nightly run never migrates: an
# unmigrated container stays on the old model (clone of the latest version to
# a new "<tag>@<digest>" version on image change, old one deactivated); a
# container with no project at all starts on "running".
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
PENDING_DIR="${CACHE_DIR}/pending"          # analysis snapshots a run couldn't replay yet
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
        -h|--help)   sed -n '2,64p' "$0"; exit 0 ;;
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

# ntfy_push TITLE TAG ITEMS... -> ONE short push (topic homelab, first 8 items)
ntfy_push() {
    if [[ -z "$NTFY_PUBLISH_TOKEN" ]]; then
        log "NTFY_PUBLISH_TOKEN not set; cannot send the push \"${1}\""
        return 0
    fi
    local body ip url sent=false
    body=$(python3 - "$NTFY_TOPIC" "$@" <<'EOF'
import json, sys
topic, title, tag, items = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
lines = items[:8] + ([f"... and {len(items) - 8} more"] if len(items) > 8 else [])
print(json.dumps({
    "topic": topic,
    "title": title,
    "message": "\n".join(lines) + "\nLog: ~/83rr-poweredge/logs/sbom-scan.log",
    "priority": 3,
    "tags": [tag, "dependency-track"],
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
            log "push \"${1}\" sent to ntfy (${url})"
            break
        fi
    done
    [[ "$sent" == true ]] || log "could not reach ntfy to send the push \"${1}\""
}

# notify -> failures, and analyses that need a human (not carried across a
# version change), each as one push. Not on --no-notify or a dry run.
notify() {
    [[ "$NOTIFY" == true && "$DRY_RUN" == false ]] || return 0
    (( ${#FAILURES[@]} == 0 )) \
        || ntfy_push "SBOM scan: ${#FAILURES[@]} failure(s) of ${TOTAL} container(s)" warning "${FAILURES[@]}"
    (( ${#REVIEW[@]} == 0 )) \
        || ntfy_push "SBOM scan: ${#REVIEW[@]} triage analysis/analyses need review" mag "${REVIEW[@]}"
}

finish() {
    local would=""
    [[ "$DRY_RUN" == true ]] && would="would be "
    if [[ "$DEACTIVATE_MISSING" == true ]]; then
        log "done: ${DEACTIVATED} version(s) of removed containers ${would}deactivated, ${#FAILURES[@]} failed"
    elif [[ "$DEACTIVATE_ONLY" == true ]]; then
        log "done: ${DEACTIVATED} superseded version(s) ${would}deactivated, ${#FAILURES[@]} failed"
    else
        [[ "$MIGRATE" == false ]] || log "migration: ${MIGRATED} container(s) ${would}moved to \"${STABLE_VERSION}\", ${ALREADY} already on it, ${STALE} project(s) without a container left as they are; analyses: ${ANALYSES_SRC} on the old versions, ${ANALYSES_COPIED} ${would}copied, ${ANALYSES_CARRIED} carried across version change, ${ANALYSES_PRESENT} already present, ${ANALYSES_REVIEW} need review, ${ANALYSES_GONE} for components no longer in the image"
        [[ "$MIGRATE" == true || "$COPY_RAN" == false ]] || log "analyses: ${ANALYSES_SRC} checked, ${ANALYSES_COPIED} copied, ${ANALYSES_CARRIED} carried across version change, ${ANALYSES_PRESENT} already present, ${ANALYSES_REVIEW} need review, ${ANALYSES_GONE} for components no longer in the image"
        log "done: ${UPLOADED} ${would}uploaded, ${SKIPPED} unchanged, ${DEACTIVATED} superseded ${would}deactivated, ${#FAILURES[@]} failed, ${TOTAL} containers"
    fi
    notify
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
ANALYSES_CARRIED=0
ANALYSES_REVIEW=0
COPY_RAN=false
CONVERGED=0
REVIEW=()
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

# analyses snapshot PROJECT_UUID OUT_FILE -> every analysed finding of
# PROJECT (component, vulnerability, full GET /api/v1/analysis) as JSON in
# OUT_FILE; prints how many.
#
# analyses copy project|snapshot SRC DST_UUID|"" SRC_LABEL REVIEW_FILE ->
# copies every analysis (state, justification, response, details,
# suppression) of version SRC (or of a snapshot file) onto DST, where DST has
# none yet. Two passes:
#   1. the same finding: component purl + vulnerability source/ID;
#   2. for an analysis with no such finding, the same purl WITHOUT its
#      version (same qualifiers) + source/ID: a package that moved to another
#      build. Copied only if there is exactly one candidate, it has no
#      analysis, the old analysis is a suppressed NOT_AFFECTED/FALSE_POSITIVE,
#      and the new version is >= the old (dpkg rules for pkg:deb, apk rules
#      for pkg:apk, semver/PEP 440 otherwise); the copy says "re-verify".
#      Anything else is a "needs review" line in REVIEW_FILE.
# Never overwrites an analysis DST already has, so it is safe to repeat.
# Without DST (dry run) it only counts. Prints "<analysed on src> <copied>
# <already present> <component gone> <failed> <carried across version
# change> <needs review>".
analyses() {
    python3 - "$DT_URL" "${WORK}/triage-hdr" "$@" <<'EOF'
import json, re, sys, urllib.parse, urllib.request
url, hdr, mode = sys.argv[1:4]
key = open(hdr).read().split(":", 1)[1].strip()
CARRY_STATES = ("NOT_AFFECTED", "FALSE_POSITIVE")   # carried across a version change (suppressed only)
FIELDS = ("analysisState", "analysisJustification", "analysisResponse", "analysisDetails")

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

def full_analysis(project, f):
    return call("GET", "/api/v1/analysis?" + urllib.parse.urlencode({
        "project": project, "component": f["component"]["uuid"], "vulnerability": f["vulnerability"]["uuid"]})) or {}

def loose(f):
    """((purl without version, qualifiers sorted), source, vulnId), purl type, version"""
    c, v = f["component"], f["vulnerability"]
    purl = c.get("purl")
    if not purl:
        return (f'{c.get("group") or ""}/{c.get("name")}', v.get("source"), v.get("vulnId")), "", c.get("version") or ""
    rest, _, sub = purl.partition("#")
    rest, _, quals = rest.partition("?")
    head, at, ver = rest.rpartition("@")
    if not at or "/" in ver:   # no version (an "@" in the namespace)
        head, ver = rest, ""
    quals = "&".join(sorted(q for q in quals.split("&") if q))
    typ = head[4:].split("/", 1)[0].lower() if head.startswith("pkg:") else ""
    base = head + (f"?{quals}" if quals else "") + (f"#{sub}" if sub else "")
    return (base, v.get("source"), v.get("vulnId")), typ, urllib.parse.unquote(ver)

# --- version order: cmp(a, b) -> <0 / 0 / >0; ValueError if not comparable ---
def dpkg_cmp(a, b):   # dpkg --compare-versions (epoch:upstream-revision)
    def split(v):
        epoch, _, rest = v.partition(":") if ":" in v else ("0", "", v)
        if not epoch.isdigit():
            raise ValueError(v)
        up, dash, rev = rest.rpartition("-")
        return int(epoch), (up if dash else rest), (rev if dash else "")
    def order(c):
        return 0 if c.isdigit() else ord(c) if c.isalpha() else -1 if c == "~" else ord(c) + 256
    def verrev(x, y):
        i = j = 0
        while i < len(x) or j < len(y):
            while (i < len(x) and not x[i].isdigit()) or (j < len(y) and not y[j].isdigit()):
                ox = order(x[i]) if i < len(x) else 0
                oy = order(y[j]) if j < len(y) else 0
                if ox != oy:
                    return ox - oy
                i += 1; j += 1
            while i < len(x) and x[i] == "0":
                i += 1
            while j < len(y) and y[j] == "0":
                j += 1
            first = 0
            while i < len(x) and x[i].isdigit() and j < len(y) and y[j].isdigit():
                first = first or int(x[i]) - int(y[j])
                i += 1; j += 1
            if i < len(x) and x[i].isdigit():
                return 1
            if j < len(y) and y[j].isdigit():
                return -1
            if first:
                return first
        return 0
    (ea, ua, ra), (eb, ub, rb) = split(a), split(b)
    return (ea - eb) or verrev(ua, ub) or verrev(ra, rb)

APK = re.compile(r"(\d+(?:\.\d+)*)([a-z]?)((?:_(?:alpha|beta|pre|rc|cvs|svn|git|hg|p)\d*)*)(?:~[0-9a-f]+)?(?:-r(\d+))?")
APK_SUFFIX = {"alpha": 0, "beta": 1, "pre": 2, "rc": 3, "cvs": 5, "svn": 6, "git": 7, "hg": 8, "p": 9}   # 4 = none

def apk_key(v):   # apk version order: 1.2.3a_rc1-r2
    m = APK.fullmatch(v)
    if not m:
        raise ValueError(v)
    sufs = [(APK_SUFFIX[s], int(n or 0)) for s, n in re.findall(r"_([a-z]+)(\d*)", m.group(3))] + [(4, 0)]
    return [int(x) for x in m.group(1).split(".")], m.group(2), sufs, int(m.group(4) or 0)

SEMVER = re.compile(r"v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")

def semver_key(v):   # 1.2 == 1.2.0; a pre-release sorts before its release
    m = SEMVER.fullmatch(v)
    if not m:
        raise ValueError(v)
    core = [int(x) for x in m.group(1).split(".")]
    while len(core) > 1 and core[-1] == 0:
        core.pop()
    pre = m.group(2)
    ids = [] if pre is None else [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")]
    return core, pre is None, ids

def order_cmp(key, a, b):
    ka, kb = key(a), key(b)
    return (ka > kb) - (ka < kb)

def pep440_cmp(a, b):   # ImportError if packaging isn't installed; InvalidVersion is a ValueError
    from packaging.version import Version
    return order_cmp(Version, a, b)

def cmp_versions(typ, a, b):
    if typ == "deb":
        return dpkg_cmp(a, b)
    if typ == "apk":
        return order_cmp(apk_key, a, b)
    for f in ((pep440_cmp, lambda x, y: order_cmp(semver_key, x, y)) if typ == "pypi" else
              (lambda x, y: order_cmp(semver_key, x, y), pep440_cmp)):
        try:
            return f(a, b)
        except (ValueError, ImportError):
            pass
    raise ValueError(f"{a} / {b}")

if mode == "snapshot":
    project, out = sys.argv[4:6]
    snap = [dict(f, fullAnalysis=full_analysis(project, f)) for f in findings(project) if analysed(f)]
    with open(out, "w") as fh:
        json.dump(snap, fh)
    print(len(snap))
    sys.exit(0)

kind, src, dst, label, review_path = sys.argv[4:9]
old = {}
for f in (json.load(open(src)) if kind == "snapshot" else [f for f in findings(src) if analysed(f)]):
    old.setdefault(ident(f), f)
open(review_path, "w").close()
if not dst:
    print(len(old), 0, 0, 0, 0, 0, 0)
    sys.exit(0)
new = {}     # ident -> every matching finding (a package vendored twice is two components)
loose_new = {}
for f in findings(dst):
    new.setdefault(ident(f), []).append(f)
    lk, typ, ver = loose(f)
    loose_new.setdefault(lk, []).append((f, ver))
done = set()   # (component, vulnerability) written by this run

def free(n):
    return not analysed(n) and (n["component"]["uuid"], n["vulnerability"]["uuid"]) not in done

def body_for(f):
    a = f.get("analysis") or {}
    body = {"analysisState": a.get("state"), "isSuppressed": bool(a.get("isSuppressed"))}
    full = f.get("fullAnalysis")
    if full is None:
        try:
            full = full_analysis(src, f)
        except Exception:
            full = {}   # fall back to the state/suppression from the finding itself
    for field in FIELDS:
        if full.get(field) is not None:
            body[field] = full[field]
    body["isSuppressed"] = bool(full.get("isSuppressed", body["isSuppressed"]))
    return body

def put(n, body, comment, what):
    try:
        call("PUT", "/api/v1/analysis", dict(body, project=dst, component=n["component"]["uuid"],
                                             vulnerability=n["vulnerability"]["uuid"], comment=comment))
        done.add((n["component"]["uuid"], n["vulnerability"]["uuid"]))
        return True
    except Exception as e:
        print(f"could not copy {what}: {e}", file=sys.stderr)
        return False

copied = present = gone = failed = carried = 0
review = []
for k, f in old.items():
    if k in new:   # pass 1: the same finding
        targets = [n for n in new[k] if free(n)]
        if not targets:
            present += 1
        for n in targets:
            if put(n, body_for(f), f"copied from version {label} by sbom-scan.sh", k):
                copied += 1
            else:
                failed += 1
        continue
    lk, typ, old_ver = loose(f)   # pass 2: the same package at another version
    cands = loose_new.get(lk, [])
    if not cands:
        gone += 1
        continue
    if not any(free(n) for n, _ in cands):
        present += 1
        continue
    a = f.get("analysis") or {}
    new_ver = ", ".join(sorted({v for _, v in cands}))
    why = None
    if len(cands) > 1:
        why = f"{len(cands)} candidates"
    elif not (a.get("isSuppressed") and a.get("state") in CARRY_STATES):
        why = f"{a.get('state')}{'' if a.get('isSuppressed') else ' (not suppressed)'} is not carried across a version change"
    else:
        try:
            if cmp_versions(typ, new_ver, old_ver) < 0:
                why = "older version"
        except ValueError:
            why = "versions not comparable"
    if why:
        review.append(f"{k[2]} {lk[0]}: {old_ver} -> {new_ver}: {why}")
        continue
    if put(cands[0][0], body_for(f), f"copied from {label}; version changed {old_ver}→{new_ver}, re-verify", k):
        carried += 1
    else:
        failed += 1
with open(review_path, "w") as fh:
    fh.write("".join(line + "\n" for line in review))
print(len(old), copied, present, gone, failed, carried, len(review))
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

# stored_prop UUID NAME -> the sbom-scan/NAME property of a version ("" if none)
stored_prop() {
    [[ "$(dt GET "/api/v1/project/${1}/property")" == 200 ]] || return 0
    json "next((p.get('propertyValue') for p in d if p.get('groupName') == 'sbom-scan' and p.get('propertyName') == '${2}'), '')"
}

# report_copy SRC DST LABEL NAME [project|snapshot] -> runs `analyses copy`
# (SRC is a version UUID or a snapshot file), logs, adds to the totals and
# collects the "needs review" items for the ntfy push.
# Returns 1 if the comparison or any copy failed: the caller must then keep
# SRC (the old version active, or the snapshot) so a re-run can retry it.
report_copy() {
    local out line n_src n_copied n_present n_gone n_failed n_carried n_review
    if [[ "$CAN_TRIAGE" == false ]]; then
        log "  ${4}: WARNING: no working DT_TRIAGE_API_KEY, analyses not checked (the clone normally carries them)"
        return
    fi
    if ! out=$(analyses copy "${5:-project}" "$1" "$2" "$3" "${WORK}/review" 2>"${WORK}/copy-err"); then
        fail "${4}: could not compare analyses with ${3}: $(tail -n 1 "${WORK}/copy-err" | cut -c1-200)"
        return 1
    fi
    read -r n_src n_copied n_present n_gone n_failed n_carried n_review <<<"$out"
    ANALYSES_SRC=$((ANALYSES_SRC + n_src)); ANALYSES_COPIED=$((ANALYSES_COPIED + n_copied))
    ANALYSES_PRESENT=$((ANALYSES_PRESENT + n_present)); ANALYSES_GONE=$((ANALYSES_GONE + n_gone))
    ANALYSES_CARRIED=$((ANALYSES_CARRIED + n_carried)); ANALYSES_REVIEW=$((ANALYSES_REVIEW + n_review))
    if [[ -z "$2" ]]; then
        log "  ${4}: ${n_src} analysis/analyses on ${3} to carry over"
        return
    fi
    COPY_RAN=true
    log "  ${4}: analyses from ${3}: ${n_src} total, ${n_copied} copied, ${n_carried} carried across version change, ${n_present} already present, ${n_review} need review, ${n_gone} for components no longer in the image"
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        log "  ${4}: needs review: ${line}"
        REVIEW+=("${4}: ${line}")
    done < "${WORK}/review"
    if (( n_failed > 0 )); then
        fail "${4}: ${n_failed} analysis/analyses could not be copied from ${3}"
        return 1
    fi
}

# converge CURRENT_UUID NAME -> copy the analyses of every other active
# version of NAME (latest first) into CURRENT, then deactivate those versions.
# If a copy failed they stay active so a re-run retries (both steps are
# idempotent). Sets CONVERGED to how many other versions were active. Returns
# 1 if the versions couldn't be listed or a copy failed.
converge() {
    local current="$1" name="$2" err uuid ver copy_ok=true
    CONVERGED=0
    if ! err=$(list_projects "$name"); then
        fail "${name}: could not list versions (${err})"
        return 1
    fi
    while read -r uuid ver; do
        [[ -n "$uuid" ]] || continue
        CONVERGED=$((CONVERGED + 1))
        if [[ "$DRY_RUN" == true ]]; then
            report_copy "$uuid" "" "$ver" "$name" || copy_ok=false
        else
            report_copy "$uuid" "$current" "$ver" "$name" || copy_ok=false
        fi
    done < <(python3 - "${WORK}/projects.json" "$current" <<'EOF'
import json, sys
others = [p for p in json.load(open(sys.argv[1])) if p["uuid"] != sys.argv[2] and p.get("active", True)]
for p in sorted(others, key=lambda p: not p.get("isLatest")):
    print(p["uuid"], p.get("version", ""))
EOF
)
    (( CONVERGED > 0 )) || return 0
    if [[ "$copy_ok" == false ]]; then
        log "  ${name}: old version(s) left active so a re-run can retry the analysis copy"
        return 1
    fi
    deactivate_superseded "$current" "$name"
}

# finish_migration STABLE_UUID NAME -> for a container already on "running":
# converge it (nothing to do after a clean migration), so a re-run of
# --migrate-stable completes one that died after the clone.
finish_migration() {
    converge "$1" "$2" || return
    (( CONVERGED > 0 )) || log "  ${2}: already on \"${STABLE_VERSION}\""
}

# snapshot_analyses UUID NAME FILE -> every analysed finding of version UUID
# into FILE, before a BOM is re-uploaded into it: a component whose version
# changes is replaced, and its analyses go with it. Returns 1 on failure.
snapshot_analyses() {
    local n
    if ! n=$(analyses snapshot "$1" "$3" 2>"${WORK}/copy-err"); then
        fail "${2}: could not snapshot the analyses, not re-uploaded: $(tail -n 1 "${WORK}/copy-err" | cut -c1-200)"
        return 1
    fi
    log "  ${2}: ${n} analysed finding(s) snapshotted before the upload"
}

# token_done TOKEN -> true once DT has finished with a BOM upload (or no
# longer knows the token).
token_done() {
    local code
    code=$(dt GET "/api/v1/event/token/${1}")
    [[ "$code" == 200 ]] || return 0
    [[ "$(json "d.get('status') or ('DONE' if not d.get('processing') else 'RUNNING')")" =~ ^(COMPLETED|FAILED|DONE)$ ]]
}

# keep_pending NAME SNAPSHOT LABEL TOKEN -> keep a snapshot that couldn't be
# replayed (BOM processing unfinished, or a copy failed) for the next run.
keep_pending() {
    mkdir -p "$PENDING_DIR"
    if [[ "$2" != "${PENDING_DIR}/${1}.json" ]]; then
        mv -f "$2" "${PENDING_DIR}/${1}.json" || { fail "${1}: could not keep the analysis snapshot"; return; }
    fi
    printf '%s\n%s\n' "$3" "${4:-}" > "${PENDING_DIR}/${1}.meta"
    log "  ${1}: analysis snapshot kept in ${PENDING_DIR}/${1}.json; a later run replays it"
}

# replay_pending NAME UUID -> replay a snapshot an earlier run kept, once DT
# has finished the BOM it was taken for (before that, the replaced component's
# new findings may not exist yet and its analyses would look "gone").
replay_pending() {
    local label token
    [[ -f "${PENDING_DIR}/${1}.json" && "$DRY_RUN" == false && "$CAN_TRIAGE" == true ]] || return 0
    { read -r label; read -r token; } < "${PENDING_DIR}/${1}.meta" 2>/dev/null
    if [[ -n "${token:-}" ]] && ! token_done "$token"; then
        log "  ${1}: kept analysis snapshot not replayed yet: DT is still processing that BOM"
        return 1
    fi
    log "  ${1}: replaying the analysis snapshot kept by an earlier run"
    if report_copy "${PENDING_DIR}/${1}.json" "$2" "${label:-an earlier scan}" "$1" snapshot; then
        rm -f -- "${PENDING_DIR:?}/${1:?}.json" "${PENDING_DIR:?}/${1:?}.meta"
    fi
}

declare -A SBOM_FOR_IMAGE=()   # image_id -> generated SBOM file (shared images scan once)

scan_container() {
    local name="$1" info tag digest image_id image_ref short label bom
    local stable_uuid="" stable_active=true src_uuid="" src_version="" code target_uuid="" token status cloned=false waited
    local legacy=false version="$STABLE_VERSION" new_uuid snap="" snap_label="" prev

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
        replay_pending "$name" "$stable_uuid"
        if [[ "$MIGRATE" == true ]]; then
            # Converge a half-done migration (a run that died after the clone):
            # copy analyses from any old version still active, then deactivate it.
            finish_migration "$stable_uuid" "$name"
            ALREADY=$((ALREADY + 1))
            SKIPPED=$((SKIPPED + 1))
            return
        fi
        if [[ "$FORCE" == false && "$(stored_prop "$stable_uuid" digest)" == "$digest" ]]; then
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
        # Only --migrate-stable migrates. Until then an unmigrated container
        # stays on the old model: one version "<tag>@<digest12>" per image.
        if [[ -n "$src_uuid" && "$MIGRATE" == false ]]; then
            legacy=true
            version="$label"
            code=$(dt GET /api/v1/project/lookup -G --data-urlencode "name=${name}" --data-urlencode "version=${label}")
            if [[ "$code" == 200 && "$FORCE" == false ]]; then
                SKIPPED=$((SKIPPED + 1))
                target_uuid=$(json "d.get('uuid')")
                if [[ "$(json "d.get('active', True) and d.get('isLatest')")" == True ]]; then
                    log "  ${name} ${label}: unchanged, skipping (old per-digest model; not migrated)"
                    # An older version left active because its analysis copy
                    # failed: retry the copy, then deactivate it.
                    if [[ "$DRY_RUN" == false && "$CAN_TRIAGE" == true && "$CAN_DEACTIVATE" == true ]]; then
                        converge "$target_uuid" "$name"
                    fi
                    return
                fi
                # Rolled back to an older image: its version exists but was
                # deactivated; make it the active latest again.
                if [[ "$DRY_RUN" == true ]]; then
                    log "  ${name}: would reactivate ${label} as latest (running again)"
                    return
                fi
                code=$(dt PATCH "/api/v1/project/${target_uuid}" -H 'Content-Type: application/json' \
                    -d '{"active": true, "isLatest": true}')
                if [[ "$code" == 200 || "$code" == 304 ]]; then
                    log "  ${name}: reactivated ${label} as latest (running again)"
                    deactivate_superseded "$target_uuid" "$name"
                else
                    log "  ${name}: WARNING: could not reactivate ${label} as latest (HTTP ${code})"
                fi
                return
            elif [[ "$code" != 200 && "$code" != 404 ]]; then
                fail "${name}: project lookup failed (HTTP ${code})"
                return
            fi
        fi
    fi

    if [[ "$DRY_RUN" == true ]]; then
        if [[ "$legacy" == true ]]; then
            log "  ${name} ${label}: would clone ${src_version} -> ${label}, scan ${image_id:7:12} and upload (old per-digest model; --migrate-stable moves it to \"${STABLE_VERSION}\")"
            [[ "$CAN_TRIAGE" == false ]] || report_copy "$src_uuid" "" "$src_version" "$name"
            deactivate_superseded "" "$name" "$label"
        elif [[ -n "$stable_uuid" ]]; then
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

    # A new version (migration to "running", or the next per-digest version
    # of an unmigrated container) starts as a clone of the latest one, so its
    # findings and audit decisions carry over and don't re-alert.
    target_uuid="$stable_uuid"
    if [[ -z "$target_uuid" && -n "$src_uuid" && "$src_version" != "$version" ]]; then
        code=$(dt POST "/api/v2/projects/${src_uuid}/clone" -H 'Content-Type: application/json' \
            -d "$(python3 -c 'import json, sys; print(json.dumps({"version": sys.argv[1], "version_is_latest": True,
                "includes": ["COMPONENTS", "FINDINGS", "FINDINGS_AUDIT_HISTORY", "POLICY_VIOLATIONS",
                             "POLICY_VIOLATIONS_AUDIT_HISTORY", "PROPERTIES", "TAGS", "ACL"]}))' "$version")")
        if [[ "$code" == 201 ]]; then
            target_uuid=$(json "d.get('uuid')")
            cloned=true
            log "  ${name}: cloned ${src_version} -> \"${version}\""
        else
            log "  ${name}: clone failed (HTTP ${code}), uploading as a fresh version instead (analyses copied afterwards)"
        fi
    fi

    # Re-upload into "running": DT replaces every component whose identity
    # (purl, so its version) changed, and its analyses go with it. Snapshot
    # them first; replayed below once the BOM is processed.
    if [[ -n "$stable_uuid" ]]; then
        if [[ "$CAN_TRIAGE" == true && -f "${PENDING_DIR}/${name}.json" ]]; then
            # Not replayed yet (see replay_pending): a new upload would replace
            # the components it still has to be matched against.
            log "  ${name}: not re-uploaded while an earlier analysis snapshot is pending"
            SKIPPED=$((SKIPPED + 1))
            return
        fi
        if [[ "$CAN_TRIAGE" == true ]]; then
            snap="${WORK}/${name}.analyses.json"
            prev=$(stored_prop "$stable_uuid" label)
            snap_label="\"${STABLE_VERSION}\" at ${prev:-the previous scan}"
            snapshot_analyses "$stable_uuid" "$name" "$snap" || return
        else
            log "  ${name}: WARNING: no working DT_TRIAGE_API_KEY, analyses of components whose version changes are not carried"
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
            # Don't leave a clone with the old BOM under the new version (it
            # would count, and a per-digest one would be skipped next run);
            # put the latest flag back on the old version.
            dt DELETE "/api/v1/project/${target_uuid}" >/dev/null
            dt PATCH "/api/v1/project/${src_uuid}" -H 'Content-Type: application/json' -d '{"isLatest": true}' >/dev/null
        fi
        return
    fi
    token=$(json "d.get('token')")
    new_uuid=$(json "d.get('projectUuid')")
    [[ -z "$new_uuid" ]] || target_uuid="$new_uuid"

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
            log "  ${name} ${label}: uploaded into \"${version}\" and analyzed (${waited}s)"
            UPLOADED=$((UPLOADED + 1)) ;;
        FAILED)
            fail "${name}: Dependency-Track failed to process the BOM (token ${token})"
            [[ -z "$snap" ]] || keep_pending "$name" "$snap" "$snap_label" "$token"
            return ;;
        *)
            log "  ${name} ${label}: uploaded; analysis still running after ${PROCESS_TIMEOUT}s"
            UPLOADED=$((UPLOADED + 1)) ;;
    esac

    if [[ -n "$snap" ]]; then
        if [[ "$status" != COMPLETED && "$status" != DONE ]]; then
            fail "${name}: BOM still processing after ${PROCESS_TIMEOUT}s, analysis snapshot not replayed yet"
            keep_pending "$name" "$snap" "$snap_label" "$token"
        elif ! report_copy "$snap" "$stable_uuid" "$snap_label" "$name" snapshot; then
            keep_pending "$name" "$snap" "$snap_label" "$token"
        fi
    fi

    if [[ "$legacy" == true ]]; then
        # Copy what the clone didn't carry (a package at another version)
        # before the old version is deactivated; a failed copy keeps it
        # active, and the next run retries.
        [[ -z "$target_uuid" ]] || converge "$target_uuid" "$name"
        return
    fi
    if [[ -z "$target_uuid" ]]; then
        fail "${name}: DT returned no project UUID for the upload; image properties not stored"
        return
    fi
    # Recorded only after a good upload: a failed one is retried next run.
    set_image_meta "$target_uuid" "$image_ref" "$digest" "$image_id" "$label" \
        || log "  ${name}: WARNING: image properties not stored; the next run uploads it again"
    if [[ -n "$src_uuid" ]]; then
        # Copy from every old version still active (the latest first), then
        # deactivate them; a failed copy keeps them active and a re-run of
        # --migrate-stable retries it (finish_migration).
        MIGRATED=$((MIGRATED + 1))
        converge "$target_uuid" "$name"
        return
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
    local current="${1:-}" name="${2:-}" next="${3:-$STABLE_VERSION}" err code uuid pname ver latest
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
        current="dry-run-${next}"
        python3 - "${WORK}/projects.json" "$name" "$next" > "${WORK}/superseded" <<'EOF' || return
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
