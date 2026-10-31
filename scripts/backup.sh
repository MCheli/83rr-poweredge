#!/bin/bash
# =============================================================================
# 83RR PowerEdge Backup Script
# =============================================================================
# Backs up critical data to NAS: //MarksNAS/Performance/83rr-backup/
#
# Usage:
#   ./backup.sh              # Run full backup
#   ./backup.sh --dry-run    # Show what would be backed up
#
# Schedule via cron (daily at 2:00 AM):
#   0 2 * * * /home/mcheli/83rr-poweredge/scripts/backup.sh >> /home/mcheli/83rr-poweredge/logs/backup.log 2>&1
#
# INTENTIONALLY NOT BACKED UP:
#   - /storage/media (Plex library, ~2.3 TB) — too large for the NAS;
#     content is re-rippable / re-downloadable. If a media-loss event
#     would matter to you, set up a separate large-volume backup target.
#   - OpenSearch / Fluent Bit / Marimo data — logs and ephemeral state.
#   - Docker images — all reproducible from ghcr.io / dockerhub.
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_ROOT="/mnt/nas/83rr-backup"
PROJECT_DIR="/home/mcheli/83rr-poweredge"
LOG_DIR="${PROJECT_DIR}/logs"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
DRY_RUN=false

# Load database credentials from .env
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    source <(grep -E '^(SEAFILE_DB_ROOT_PASSWORD|TALLIED_DB_PASSWORD|TASKS_DB_PASSWORD)=' "${PROJECT_DIR}/.env")
fi
SEAFILE_DB_PASS="${SEAFILE_DB_ROOT_PASSWORD:-}"
TALLIED_DB_PASS="${TALLIED_DB_PASSWORD:-}"
TASKS_DB_PASS="${TASKS_DB_PASSWORD:-}"

# Retention settings
DAILY_KEEP=7
WEEKLY_KEEP=4
MONTHLY_KEEP=3
# Database dumps: newest N compressed dumps kept PER SERVICE (seafile, tallied,
# tasks, energy_monitor, ...). Count-based on purpose: a long run of failed
# backups can never prune away the last good dumps.
DB_DUMPS_KEEP_PER_SERVICE=14
# Uncompressed *.sql files only exist when a dump failed midway (gzip never
# ran). Keep them this many days for forensics, then remove.
DB_PARTIAL_KEEP_DAYS=2

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}=== DRY RUN MODE ===${NC}"
fi

# Logging
mkdir -p "${LOG_DIR}"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

# --- Failure tracking ---------------------------------------------------------
# Any recorded failure makes the whole run exit non-zero, prints a loud
# summary, and SUPPRESSES the success heartbeat. The heartbeat is the
# canonical "backup OK" signal feeding the OpenSearch absence monitor, so
# suppressing it on failure is what turns a silent partial backup into an
# alert. (Root cause of the 2026-05-17 host lockup: a partial backup that
# still reported "completed successfully".)
BACKUP_FAILURES=0
FAILED_ITEMS=""
record_failure() {
    BACKUP_FAILURES=$((BACKUP_FAILURES + 1))
    FAILED_ITEMS="${FAILED_ITEMS}"$'\n'"  - $1"
    error "$1"
}

# --- Memory-capped rsync ------------------------------------------------------
# Hard ceiling on virtual memory for any rsync we spawn. A runaway rsync
# (e.g. following a self-referential Wine/Proton `dosdevices/z: -> /`
# symlink) builds its in-memory file list until it OOM-kills the host.
# With this cap it hits ENOMEM and dies in seconds instead. 8 GiB, in KiB.
# sudo does not reset RLIMIT_AS, so the rsync child inherits this limit.
RSYNC_VMEM_CAP_KB=8388608
safe_rsync() {
    ( ulimit -v "${RSYNC_VMEM_CAP_KB}"; "$@" )
}

# Check if NAS is mounted
check_nas_mount() {
    if ! mountpoint -q /mnt/nas; then
        error "NAS is not mounted at /mnt/nas"
        log "Attempting to mount NAS..."
        sudo mount /mnt/nas || {
            error "Failed to mount NAS. Backup aborted."
            exit 1
        }
        # mount can exit 0 even when mount.cifs fails (2026-10-18: "mount
        # error(113)" then a false "[OK] NAS mounted" and a confusing mkdir
        # failure). Trust the mount table, not the exit code.
        if ! mountpoint -q /mnt/nas; then
            error "NAS still not mounted after mount attempt (NAS down?). Backup aborted."
            exit 1
        fi
    fi
    success "NAS mounted"
}

# Create backup directories
setup_backup_dirs() {
    local dirs=(
        "${BACKUP_ROOT}/daily"
        "${BACKUP_ROOT}/weekly"
        "${BACKUP_ROOT}/monthly"
        "${BACKUP_ROOT}/databases"
        "${BACKUP_ROOT}/latest"
    )

    for dir in "${dirs[@]}"; do
        if [[ "$DRY_RUN" == false ]]; then
            mkdir -p "$dir"
        fi
    done
    success "Backup directories ready"
}

# Dump Seafile MariaDB database
backup_seafile_db() {
    log "Backing up Seafile database..."
    local dump_file="${BACKUP_ROOT}/databases/seafile_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Seafile MariaDB to ${dump_file}"
        return
    fi

    docker exec seafile-db mysqldump -u root -p"${SEAFILE_DB_PASS}" \
        --all-databases --single-transaction --quick --lock-tables=false \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Seafile database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Seafile database backed up: ${dump_file}.gz"
}

# Dump Tallied PostgreSQL database
backup_tallied_db() {
    log "Backing up Tallied database..."
    local dump_file="${BACKUP_ROOT}/databases/tallied_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Tallied PostgreSQL to ${dump_file}"
        return
    fi

    docker exec tallied-db pg_dump -U tallied tallied \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Tallied database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Tallied database backed up: ${dump_file}.gz"
}

# Dump Tasks PostgreSQL database
backup_tasks_db() {
    log "Backing up Tasks database..."
    local dump_file="${BACKUP_ROOT}/databases/tasks_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Tasks PostgreSQL to ${dump_file}"
        return
    fi

    docker exec tasks-db pg_dump -U tasks tasks \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Tasks database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Tasks database backed up: ${dump_file}.gz"
}

# Dump Energy Monitor PostgreSQL database
backup_energy_monitor_db() {
    log "Backing up Energy Monitor database..."
    local dump_file="${BACKUP_ROOT}/databases/energy_monitor_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Energy Monitor PostgreSQL to ${dump_file}"
        return
    fi

    docker exec energy-monitor-db pg_dump -U panel_tool panel_tool \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Energy Monitor database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Energy Monitor database backed up: ${dump_file}.gz"
}

# Dump Dependency-Track PostgreSQL database (all DT state: projects,
# findings, audit decisions, alert rules, encrypted secrets). The KEK that
# decrypts those secrets is in the deptrack_data volume, backed up below.
backup_deptrack_db() {
    log "Backing up Dependency-Track database..."
    local dump_file="${BACKUP_ROOT}/databases/deptrack_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Dependency-Track PostgreSQL to ${dump_file}"
        return
    fi

    docker exec deptrack-db pg_dump -U dtrack dtrack \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Dependency-Track database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Dependency-Track database backed up: ${dump_file}.gz"
}

# Backup Docker volumes
backup_docker_volumes() {
    log "Backing up Docker volumes..."
    local volumes_dir="${BACKUP_ROOT}/latest/docker-volumes"

    # List of important volumes to backup
    local volumes=(
        "83rr-poweredge_grafana_data"
        "83rr-poweredge_prometheus_data"
        "83rr-poweredge_minecraft_data_local"   # the live world: docker-compose.override.yml mounts minecraft_data_local
        "83rr-poweredge_plex_config"
        "83rr-poweredge_tallied_db_data"
        "83rr-poweredge_tasks_db_data"
        "83rr-poweredge_energy_monitor_db_data"
        "83rr-poweredge_energy_monitor_data"
        "83rr-poweredge_asa_server_files"
        "83rr-poweredge_uptime_kuma_data"       # monitors, notifications, status page (SQLite)
        "83rr-poweredge_ntfy_data"              # ntfy users, access rules, tokens (user.db)
        "83rr-poweredge_deptrack_data"          # Dependency-Track KEK keyset (decrypts DB secrets) + file storage
    )

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would backup volumes to ${volumes_dir}:"
        for vol in "${volumes[@]}"; do
            echo "    - ${vol}"
        done
        return
    fi

    mkdir -p "${volumes_dir}"

    for vol in "${volumes[@]}"; do
        local vol_path="/var/lib/docker/volumes/${vol}/_data"
        local dest="${volumes_dir}/${vol}"

        if [[ -d "${vol_path}" ]] || sudo test -d "${vol_path}" 2>/dev/null; then
            log "  Backing up volume: ${vol}"
            mkdir -p "${dest}"
            # -L derefs symlinks (CIFS can't store them). The ASA volume
            # carries a Proton/Wine prefix at steamapps/compatdata/<id>/ —
            # purely regenerable Wine state (registry, fake C: drive, fonts,
            # system DLLs). With -L its `dosdevices/z: -> /` recursed the
            # whole filesystem infinitely and OOM-killed the host (incident
            # 2026-05-17); it also holds hundreds of dangling symlinks that
            # make rsync exit 23. The real ARK data (ShooterGame/Saved/...)
            # lives OUTSIDE compatdata, so exclude the whole prefix — same
            # "regenerable cache" rationale as the other excluded asa_* vols.
            # --safe-links + the 8 GiB safe_rsync cap are belt-and-suspenders.
            # NOTE: keep `-aL --delete` as the literal leading args — the
            # NOPASSWD rule in /etc/sudoers.d/backup matches
            # `/usr/bin/rsync -aL --delete *`, so any flag inserted before
            # --delete breaks passwordless sudo for the (mcheli) cron run.
            local rsync_opts=(-aL --delete --safe-links
                --exclude 'steamapps/compatdata')
            # rsync exit 24 = source files vanished mid-copy (benign on live
            # volumes/DBs). Treat 0 and 24 as success; anything else fails.
            local rc=0
            safe_rsync sudo rsync "${rsync_opts[@]}" "${vol_path}/" "${dest}/" 2>&1 || rc=$?
            if [[ $rc -ne 0 && $rc -ne 24 ]]; then
                log "  Retrying ${vol} (rsync exit ${rc})..."
                sleep 5
                rc=0
                safe_rsync sudo rsync "${rsync_opts[@]}" "${vol_path}/" "${dest}/" 2>&1 || rc=$?
            fi
            if [[ $rc -ne 0 && $rc -ne 24 ]]; then
                record_failure "Docker volume: ${vol} (rsync exit ${rc})"
                continue
            fi
        else
            log "  Volume not found, skipping: ${vol}"
        fi
    done

    success "Docker volumes backed up"
}

# Backup configuration files
backup_configs() {
    log "Backing up configuration files..."
    local config_dir="${BACKUP_ROOT}/latest/config"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would backup configs to ${config_dir}"
        return
    fi

    mkdir -p "${config_dir}"

    # Project directory (excludes node_modules, venv, etc.)
    # Use -L to follow symlinks (CIFS doesn't support symlinks)
    rsync -aL --delete \
        --exclude 'node_modules' \
        --exclude 'venv' \
        --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.nuxt' \
        --exclude '.output' \
        "${PROJECT_DIR}/" "${config_dir}/83rr-poweredge/"

    # Let's Encrypt certificates
    if [[ -d "/home/mcheli/letsencrypt" ]]; then
        rsync -aL --delete "/home/mcheli/letsencrypt/" "${config_dir}/letsencrypt/"
    fi

    # NAS credentials — root-owned (referenced in /etc/fstab). Without these
    # you cannot remount the NAS in DR, which would block reading any of
    # this backup. NOPASSWD rsync is already granted in /etc/sudoers.d/backup.
    # Also save the contents to a password manager off-host as a true offline copy.
    if sudo rsync -aL --delete /root/.nas-credentials "${config_dir}/nas-credentials" 2>/dev/null; then
        chmod 600 "${config_dir}/nas-credentials" 2>/dev/null || true
        success "NAS credentials backed up"
    else
        log "  NAS credentials at /root/.nas-credentials not backed up (sudo rsync failed)"
    fi

    success "Configuration files backed up"
}

# Backup Seafile data
backup_seafile_data() {
    log "Backing up Seafile data..."
    local seafile_dir="${BACKUP_ROOT}/latest/seafile"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would backup /storage/seafile to ${seafile_dir}"
        return
    fi

    if [[ -d "/storage/seafile" ]]; then
        mkdir -p "${seafile_dir}"
        # Use sudo for root-owned Seafile data, exclude logs
        sudo rsync -aL --delete \
            --exclude 'logs' \
            "/storage/seafile/" "${seafile_dir}/" 2>/dev/null || {
            error "Failed to backup Seafile data (may need sudo)"
            return 1
        }
        success "Seafile data backed up"
    else
        log "  Seafile data directory not found, skipping"
    fi
}

# Create dated snapshot
create_snapshot() {
    local snapshot_type="$1"
    local dest_dir="${BACKUP_ROOT}/${snapshot_type}/${DATE}"

    log "Creating ${snapshot_type} snapshot..."

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would create snapshot at ${dest_dir}"
        return
    fi

    # Use hard links to save space (like rsnapshot)
    if [[ -d "${BACKUP_ROOT}/latest" ]]; then
        mkdir -p "${dest_dir}"
        cp -al "${BACKUP_ROOT}/latest/"* "${dest_dir}/" 2>/dev/null || true
        success "${snapshot_type^} snapshot created: ${dest_dir}"
    fi
}

# Print every path the retention policy would prune, one per line.
# cleanup_old_backups uses this for both the real run and --dry-run, so the
# dry run always shows exactly what a real run would delete.
# Listing errors are logged, never fatal, and never add paths to the list.
list_prunable_backups() {
    local dbdir="${BACKUP_ROOT}/databases"
    local ts_re='[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}'

    # Snapshots. Note on find semantics: -mtime +N matches only entries at least
    # N+1 full days old, so on disk you will see N+1 to N+2 snapshots per tier.
    local tier keep_days
    for tier in daily weekly monthly; do
        case "$tier" in
            daily)   keep_days=${DAILY_KEEP} ;;
            weekly)  keep_days=$((WEEKLY_KEEP * 7)) ;;
            monthly) keep_days=$((MONTHLY_KEEP * 30)) ;;
        esac
        [[ -d "${BACKUP_ROOT}/${tier}" ]] || continue
        find "${BACKUP_ROOT}/${tier}" -mindepth 1 -maxdepth 1 -type d -mtime +"${keep_days}" -print \
            || error "Could not list ${tier}/ snapshots (continuing)"
    done

    [[ -d "${dbdir}" ]] || return 0

    # Database dumps: keep the newest DB_DUMPS_KEEP_PER_SERVICE per service.
    # Service name = filename minus the trailing _YYYY-MM-DD_HH-MM-SS.sql.gz.
    # The exact-name regex means a service never counts another service's
    # dumps (e.g. "tasks" vs a future "tasks_archive"), and hand-named files
    # such as seafile_before-upgrade.sql.gz are never touched.
    local svc
    while IFS= read -r svc; do
        [[ -n "$svc" ]] || continue
        find "${dbdir}" -maxdepth 1 -type f -regextype posix-extended \
                -regex ".*/${svc}_${ts_re}\.sql\.gz" -printf '%T@ %p\n' \
            | sort -rn | tail -n +$((DB_DUMPS_KEEP_PER_SERVICE + 1)) | cut -d' ' -f2- \
            || error "Could not list ${svc} dumps (continuing)"
    done < <(find "${dbdir}" -maxdepth 1 -type f -regextype posix-extended \
                -regex ".*/[A-Za-z0-9_]+_${ts_re}\.sql\.gz" -printf '%f\n' \
                | sed -E "s/_${ts_re}\.sql\.gz\$//" | sort -u)

    # Partial (uncompressed) dumps left by failed runs
    find "${dbdir}" -maxdepth 1 -type f -name '*.sql' -mtime +"$((DB_PARTIAL_KEEP_DAYS - 1))" -print \
        || error "Could not list partial *.sql dumps (continuing)"

    return 0
}

# Cleanup old backups based on retention policy
cleanup_old_backups() {
    log "Cleaning up old backups..."
    log "  Policy: snapshots older than ${DAILY_KEEP}d daily / $((WEEKLY_KEEP * 7))d weekly / $((MONTHLY_KEEP * 30))d monthly; newest ${DB_DUMPS_KEEP_PER_SERVICE} dumps per service; *.sql partials older than ${DB_PARTIAL_KEEP_DAYS}d"

    local -a prunable=()
    mapfile -t prunable < <(list_prunable_backups)

    local p rel count=0 failed=0
    for p in "${prunable[@]}"; do
        [[ -n "$p" ]] || continue
        rel="${p#"${BACKUP_ROOT}"/}"
        # Belt and braces: never rm -rf anything outside the backup root.
        if [[ "$p" != "${BACKUP_ROOT}/"* || "$rel" == "$p" || -z "$rel" ]]; then
            error "Refusing to remove path outside ${BACKUP_ROOT}: ${p}"
            failed=$((failed + 1))
            continue
        fi
        if [[ "$DRY_RUN" == true ]]; then
            echo "  Would remove ${rel}"
            count=$((count + 1))
        elif rm -rf -- "$p"; then
            log "  Removed ${rel}"
            count=$((count + 1))
        else
            error "Could not remove ${rel} (continuing)"
            failed=$((failed + 1))
        fi
    done

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would remove ${count} item(s) in total"
        return
    fi

    if [[ "$failed" -gt 0 ]]; then
        error "Cleanup removed ${count} item(s); ${failed} could not be removed"
    else
        success "Old backups cleaned up (${count} item(s) removed)"
    fi
}

# Emit a heartbeat doc to OpenSearch so we can alert on its absence.
# A monitor in OpenSearch fires if no heartbeat appears in 26h. This is
# the single canonical "did the backup run successfully?" signal.
emit_heartbeat() {
    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would emit backup heartbeat to OpenSearch"
        return
    fi

    # Hit OpenSearch via its docker network endpoint
    local now_iso=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
    local payload="{\"@timestamp\":\"${now_iso}\",\"container_name\":\"backup-heartbeat\",\"event_type\":\"backup_completed\",\"level\":\"INFO\",\"msg\":\"83rr-poweredge backup completed successfully\",\"backup_size\":\"$(du -sb "${BACKUP_ROOT}" 2>/dev/null | cut -f1 || echo 0)\"}"

    if docker exec opensearch curl -s -X POST \
        "http://localhost:9200/logs-homelab-$(date +%Y.%m.%d)/_doc" \
        -H 'Content-Type: application/json' \
        -d "${payload}" >/dev/null 2>&1; then
        success "Heartbeat emitted to OpenSearch"
    else
        log "Could not emit heartbeat (OpenSearch unreachable?) — non-fatal"
    fi
}

# Calculate backup size
report_backup_size() {
    log "Calculating backup size..."

    if [[ "$DRY_RUN" == true ]]; then
        return
    fi

    local total_size=$(du -sh "${BACKUP_ROOT}" 2>/dev/null | cut -f1)
    local latest_size=$(du -sh "${BACKUP_ROOT}/latest" 2>/dev/null | cut -f1)

    echo ""
    echo "=========================================="
    echo "Backup Summary"
    echo "=========================================="
    echo "Latest backup size: ${latest_size}"
    echo "Total backup size:  ${total_size}"
    echo "Backup location:    ${BACKUP_ROOT}"
    echo "=========================================="
}

# Main backup routine
main() {
    echo ""
    log "=========================================="
    log "Starting 83RR PowerEdge Backup"
    log "=========================================="
    echo ""

    # Pre-flight checks
    check_nas_mount
    setup_backup_dirs

    # Database backups (do these first while services are running)
    backup_seafile_db        || record_failure "Seafile DB dump"
    backup_tallied_db        || record_failure "Tallied DB dump"
    backup_tasks_db          || record_failure "Tasks DB dump"
    backup_energy_monitor_db || record_failure "Energy Monitor DB dump"
    backup_deptrack_db       || record_failure "Dependency-Track DB dump"

    # File backups
    backup_configs       || record_failure "Configuration files"
    backup_seafile_data  || record_failure "Seafile data"
    backup_docker_volumes

    # Create daily snapshot
    create_snapshot "daily"

    # Create weekly snapshot on Sundays
    if [[ $(date +%u) -eq 7 ]]; then
        create_snapshot "weekly"
    fi

    # Create monthly snapshot on 1st of month
    if [[ $(date +%d) -eq 01 ]]; then
        create_snapshot "monthly"
    fi

    # Cleanup old backups
    cleanup_old_backups

    # Report
    report_backup_size

    # Fail loudly: if anything failed, do NOT emit the success heartbeat —
    # its absence is what trips the OpenSearch alert.
    if [[ ${BACKUP_FAILURES} -gt 0 ]]; then
        echo ""
        log "=========================================="
        error "Backup completed WITH ${BACKUP_FAILURES} FAILURE(S):${FAILED_ITEMS}"
        error "Success heartbeat SUPPRESSED — OpenSearch absence monitor will alert."
        log "=========================================="
        exit 1
    fi

    # Emit heartbeat (after everything else succeeds)
    emit_heartbeat

    echo ""
    log "=========================================="
    log "Backup completed successfully!"
    log "=========================================="
}

# Run main
main "$@"
