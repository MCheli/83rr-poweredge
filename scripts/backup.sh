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
    source <(grep -E '^(SEAFILE_DB_ROOT_PASSWORD|POSTGRES_PASSWORD)=' "${PROJECT_DIR}/.env")
fi
SEAFILE_DB_PASS="${SEAFILE_DB_ROOT_PASSWORD:-}"
JUPYTERHUB_DB_PASS="${POSTGRES_PASSWORD:-}"

# Retention settings
DAILY_KEEP=7
WEEKLY_KEEP=4
MONTHLY_KEEP=3

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

# Check if NAS is mounted
check_nas_mount() {
    if ! mountpoint -q /mnt/nas; then
        error "NAS is not mounted at /mnt/nas"
        log "Attempting to mount NAS..."
        sudo mount /mnt/nas || {
            error "Failed to mount NAS. Backup aborted."
            exit 1
        }
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

# Dump JupyterHub PostgreSQL database
backup_jupyterhub_db() {
    log "Backing up JupyterHub database..."
    local dump_file="${BACKUP_ROOT}/databases/jupyterhub_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump JupyterHub PostgreSQL to ${dump_file}"
        return
    fi

    docker exec jupyterhub-db pg_dumpall -U jhub \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump JupyterHub database"
        return 1
    }

    gzip -f "${dump_file}"
    success "JupyterHub database backed up: ${dump_file}.gz"
}

# Backup Docker volumes
backup_docker_volumes() {
    log "Backing up Docker volumes..."
    local volumes_dir="${BACKUP_ROOT}/latest/docker-volumes"

    # List of important volumes to backup
    local volumes=(
        "83rr-poweredge_grafana_data"
        "83rr-poweredge_prometheus_data"
        "83rr-poweredge_minecraft_data"
        "83rr-poweredge_plex_config"
        "83rr-poweredge_jupyterhub_data"
        "83rr-poweredge_jupyterhub_shared"
        "jupyterhub-user-mcheli"
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
            # Retry once on failure (handles transient NAS issues)
            if ! sudo rsync -aL --delete "${vol_path}/" "${dest}/" 2>&1; then
                log "  Retrying ${vol}..."
                sleep 5
                sudo rsync -aL --delete "${vol_path}/" "${dest}/" 2>&1 || {
                    error "Failed to backup volume: ${vol}"
                    continue
                }
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

    # Note: NAS credentials at /root/.nas-credentials require manual backup with sudo

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

# Cleanup old backups based on retention policy
cleanup_old_backups() {
    log "Cleaning up old backups..."

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would remove backups older than retention policy"
        return
    fi

    # Cleanup daily backups
    find "${BACKUP_ROOT}/daily" -maxdepth 1 -type d -mtime +${DAILY_KEEP} -exec rm -rf {} \; 2>/dev/null || true

    # Cleanup weekly backups
    find "${BACKUP_ROOT}/weekly" -maxdepth 1 -type d -mtime +$((WEEKLY_KEEP * 7)) -exec rm -rf {} \; 2>/dev/null || true

    # Cleanup monthly backups
    find "${BACKUP_ROOT}/monthly" -maxdepth 1 -type d -mtime +$((MONTHLY_KEEP * 30)) -exec rm -rf {} \; 2>/dev/null || true

    # Cleanup old database dumps (keep last 7)
    ls -t "${BACKUP_ROOT}/databases/"*.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

    success "Old backups cleaned up"
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
    backup_seafile_db || true
    backup_jupyterhub_db || true

    # File backups
    backup_configs
    backup_seafile_data
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

    echo ""
    log "=========================================="
    log "Backup completed successfully!"
    log "=========================================="
}

# Run main
main "$@"
