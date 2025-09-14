# One-Time Setup Scripts

This directory contains scripts that are designed to be run once during initial setup or major infrastructure changes. These scripts should not be run repeatedly.

## Scripts in this directory:

### Disk Management
- **`setup_data_disk.sh`** - Initial setup of second disk for data storage
- **`migrate_docker_to_data_disk.sh`** - Migrate Docker data to the new disk
- **`restart_and_verify_docker.sh`** - Restart services after Docker migration
- **`cleanup_docker_backup.sh`** - Clean up Docker backup directories after migration

## Usage Warning

⚠️ **These scripts are for one-time use only!** Running them multiple times could cause issues or data loss.

## Execution Order

If setting up from scratch, run in this order:
1. `setup_data_disk.sh` (with sudo)
2. `migrate_docker_to_data_disk.sh` (with sudo)
3. `restart_and_verify_docker.sh` (with sudo)
4. `cleanup_docker_backup.sh` (with sudo) - only after verifying migration success

## Prerequisites

- All scripts require sudo access
- Docker must be installed and running (except for setup_data_disk.sh)
- Second disk (/dev/sdb) must be available for setup_data_disk.sh