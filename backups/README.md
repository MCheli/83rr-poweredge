# Backups Directory

This directory stores infrastructure configuration backups.

## Purpose

Automated backups of critical infrastructure files are stored here to enable:
- Quick rollback if deployments fail
- Historical configuration tracking
- Disaster recovery

## Backup Files

Backup files follow the naming convention:
- `{service}-backup-{timestamp}.yml`
- `infrastructure-backup-{timestamp}.tar.gz`

## Retention Policy

- Keep backups for 30 days
- Backups older than 30 days can be safely deleted
- Critical milestones should be archived separately

## Automated Backups

Backups are created automatically by:
- `infrastructure_manager.py` before deployments
- Manual backups can be created as needed

## Restore Process

To restore from a backup:
```bash
# Copy backup file to original location
cp backups/service-backup-TIMESTAMP.yml infrastructure/service/docker-compose.yml

# Redeploy service
docker compose up -d service
```
