# Infrastructure Cleanup Plan
**Date**: January 2, 2026
**Status**: Ready for Review and Execution

## Executive Summary

After completing Phase 6 (migration to NGINX/Cloudflare/Docker Compose), the infrastructure contains significant obsolete files and configurations from the previous Traefik/Portainer/Let's Encrypt architecture. This document provides a comprehensive cleanup plan for both the repository and server.

**Scope**:
- **Repository**: ~35-40% of files need deletion or updates
- **Server Home Directory**: ~100MB of obsolete files (old configs, volumes, source code)
- **Docker Volumes**: 7 unused volumes from previous deployments

---

## Part 1: Repository Cleanup

### Phase 1 - CRITICAL (Delete Obsolete Scripts)

**Files to DELETE** (8 scripts):
```bash
rm scripts/portainer_stack_manager.py           # Portainer API management (replaced by Docker Compose)
rm scripts/infrastructure_manager.py             # Old master controller (replaced by infrastructure_manager_new.py)
rm scripts/registry_builder.py                  # Registry deployment for Portainer
rm scripts/github_registry_auth.py              # Registry authentication (no longer needed)
rm scripts/dns_manager.py                       # Squarespace DNS (replaced by Cloudflare)
rm scripts/setup_cloudflare_auth.py             # One-time setup (archive instead)
```

**Directories to DELETE**:
```bash
rm -rf infrastructure/traefik/                   # Traefik completely replaced by NGINX
rm infrastructure/flask-api/docker-compose.registry.yml
rm infrastructure/jupyter/docker-compose.registry.yml
rm infrastructure/personal-website/docker-compose.registry.yml
```

### Phase 2 - CRITICAL (Update Documentation)

**CLAUDE.md** - HIGHEST PRIORITY
- Remove all Portainer stack manager references
- Remove "registry-based deployment" instructions
- Replace with native Docker Compose commands
- Update "Core Management Scripts" section (remove 5 obsolete scripts)
- Remove SSH deployment as primary method
- Update SSL management (Cloudflare, not Let's Encrypt)
- Update service endpoints (remove Traefik dashboard)
- Update pre-commit checklist (remove Portainer commands)

**README.md**
- Update architecture section: NGINX/Cloudflare/Docker Compose
- Replace Portainer references with Docker Compose
- Update SSL management section (15-year Cloudflare certs)
- Remove SSH connection limit discussion
- Update quick start commands

**DEPLOYMENT_STATUS.md**
- Update to reflect 8/10 services running
- Remove Traefik references
- Confirm NGINX migration complete

### Phase 3 - Update Test Suites

**test_infrastructure.py**
- Remove Traefik dashboard health checks
- Remove Portainer API health checks
- Update to test NGINX endpoints
- Verify against current service list

**quick_service_test.py**
- Remove Traefik dashboard endpoint
- Remove Portainer dashboard endpoint
- Update for NGINX-based routing

**validate_environment.py**
- Remove PORTAINER_* environment checks
- Add CLOUDFLARE_* environment checks
- Verify Docker Compose instead of Portainer API

### Phase 4 - Archive Completed Migration Docs

**Move to `docs/archive/`**:
```bash
mkdir -p docs/archive
mv INFRASTRUCTURE_MODERNIZATION_PLAN.md docs/archive/
mv NGINX_MIGRATION_CHECKLIST.md docs/archive/
mv DOMAIN_TRANSFER_GUIDE.md docs/archive/
mv docs/WILDCARD_SSL_SETUP.md docs/archive/          # Google Domains DNS-01
mv docs/MANUAL_WILDCARD_SSL_SETUP.md docs/archive/   # Let's Encrypt 90-day
mv docs/SSH_SESSION_MANAGEMENT.md docs/archive/      # Old SSH deployment
```

### Phase 5 - Rename/Reorganize Active Scripts

```bash
mv scripts/infrastructure_manager_new.py scripts/infrastructure_manager.py
# Update all references in documentation
```

---

## Part 2: Server Home Directory Cleanup

### Files/Directories to DELETE from ~/

**Old Infrastructure Directories** (Safe to delete - 29MB total):
```bash
rm -rf ~/infrastructure/          # 24KB - replaced by ~/83rr-poweredge/infrastructure/
rm -rf ~/traefik/                 # 36KB - Traefik replaced by NGINX
rm -rf ~/personal-website/        # 29MB - Source code now in ~/83rr-poweredge/infrastructure/personal-website/
rm -rf ~/letsencrypt/             # 56KB - Let's Encrypt replaced by Cloudflare
```

**One-Time Setup Scripts** (Safe to delete):
```bash
rm ~/cleanup_docker_backup.sh                    # One-time disk migration cleanup
rm ~/migrate_docker_to_data_disk.sh             # One-time disk migration
rm ~/restart_and_verify_docker.sh               # One-time disk migration verification
rm ~/setup_data_disk.sh                         # One-time disk setup
```

**Old Package Files**:
```bash
rm ~/webmin_2.105_all.deb                       # Old installer (33MB)
rm ~/srvadmin-idracadm8.deb                     # Empty file
```

**Old Environment File** (Review first):
```bash
# Review ~/.env for any important variables, then:
rm ~/.env  # Old environment variables (replaced by ~/83rr-poweredge/.env)
```

**Total Space to Recover**: ~62MB

---

## Part 3: Docker Volume Cleanup

### Unused Docker Volumes (Backup First!)

**Old Minecraft Volume** (1 volume):
- `minecraft_minecraft_data` (replaced by `83rr-poweredge_minecraft_data`)

**Old Jupyter Volumes** (6 volumes):
- `jupyter_hub_db_data`
- `jupyter_jupyterhub-shared`
- `jupyter_jupyterhub_data`
- `jupyterhub-shared`
- `jupyterhub-user-mark`
- `jupyterhub-user-mcheli`

### Backup Process

**Step 1: Create backup directory**
```bash
mkdir -p ~/volume-backups/$(date +%Y%m%d)
cd ~/volume-backups/$(date +%Y%m%d)
```

**Step 2: Backup Minecraft data**
```bash
docker run --rm -v minecraft_minecraft_data:/data -v $(pwd):/backup alpine tar czf /backup/minecraft_old_$(date +%Y%m%d).tar.gz /data
```

**Step 3: Backup Jupyter volumes**
```bash
for vol in jupyter_hub_db_data jupyter_jupyterhub-shared jupyter_jupyterhub_data jupyterhub-shared jupyterhub-user-mark jupyterhub-user-mcheli; do
  docker run --rm -v $vol:/data -v $(pwd):/backup alpine tar czf /backup/${vol}_$(date +%Y%m%d).tar.gz /data
done
```

**Step 4: Verify backups**
```bash
ls -lh ~/volume-backups/$(date +%Y%m%d)/
# Should show 7 .tar.gz files
```

**Step 5: Remove old volumes** (ONLY after backup verification)
```bash
docker volume rm minecraft_minecraft_data
docker volume rm jupyter_hub_db_data jupyter_jupyterhub-shared jupyter_jupyterhub_data jupyterhub-shared jupyterhub-user-mark jupyterhub-user-mcheli
```

---

## Part 4: Execution Checklist

### Pre-Cleanup Verification
- [ ] All services are running and healthy (`docker ps`)
- [ ] Recent git commit exists (rollback safety)
- [ ] Docker volume backups completed and verified
- [ ] Current `.env` file reviewed for important variables

### Repository Cleanup Execution Order
1. [ ] **Phase 1**: Delete obsolete scripts (8 files + directories)
2. [ ] **Phase 2**: Update CLAUDE.md (CRITICAL - blocks future work)
3. [ ] **Phase 3**: Update README.md and DEPLOYMENT_STATUS.md
4. [ ] **Phase 4**: Update test_infrastructure.py and quick_service_test.py
5. [ ] **Phase 5**: Archive completed migration docs
6. [ ] **Phase 6**: Rename infrastructure_manager_new.py
7. [ ] **Phase 7**: Update FUTURE_TODOS.md (remove obsolete tasks)

### Server Cleanup Execution Order
1. [ ] Backup Docker volumes (Minecraft + Jupyter)
2. [ ] Verify backups created successfully
3. [ ] Delete old directories (~/, ~29MB)
4. [ ] Delete one-time setup scripts
5. [ ] Delete old package files (~33MB)
6. [ ] Review and delete old .env file
7. [ ] Remove unused Docker volumes (7 volumes)

### Post-Cleanup Verification
- [ ] Run `test_infrastructure.py` - all tests pass
- [ ] Run `docker compose up -d` - all services start
- [ ] Check service endpoints - all respond correctly
- [ ] Verify CLAUDE.md reflects current architecture
- [ ] Git status shows only intended deletions/modifications

---

## Part 5: Risk Assessment

### Low Risk (Safe to Execute)
- Deleting Portainer/Traefik scripts (no longer used)
- Deleting old infrastructure directories in ~/ (duplicates in repo)
- Deleting one-time setup scripts (already executed)
- Removing unused Docker volumes (after backup)

### Medium Risk (Review Carefully)
- Updating CLAUDE.md (critical for future Claude Code work)
- Updating test suites (must verify tests still pass)
- Deleting `~/.env` (must verify no unique variables)

### High Risk (Requires Verification)
- Renaming infrastructure_manager_new.py (update all references)
- Removing Docker volumes (backup MUST be verified first)

---

## Part 6: Rollback Plan

### If Repository Changes Cause Issues
```bash
cd ~/83rr-poweredge
git stash  # Save current changes
git reset --hard HEAD~1  # Revert to previous commit
```

### If Server Cleanup Causes Issues
```bash
# Restore Docker volume from backup (example):
docker volume create minecraft_minecraft_data
docker run --rm -v minecraft_minecraft_data:/data -v ~/volume-backups/20260102:/backup alpine tar xzf /backup/minecraft_old_20260102.tar.gz -C /
```

### If Services Stop Working
```bash
cd ~/83rr-poweredge
docker compose down
docker compose up -d
# Check logs: docker compose logs -f <service_name>
```

---

## Part 7: Expected Outcomes

### Repository
- **Removed**: ~18 obsolete files
- **Updated**: ~17 files with current architecture
- **Cleaner codebase**: 35-40% reduction in technical debt
- **Accurate documentation**: CLAUDE.md reflects NGINX/Cloudflare/Docker Compose

### Server
- **Space recovered**: ~62MB from home directory
- **Simplified structure**: Only active project directory (`~/83rr-poweredge`)
- **Docker volumes**: Only active volumes retained
- **Backup safety**: 7 volume backups created

### Development Experience
- **No confusion**: Scripts match current architecture
- **Faster development**: Clear which tools to use
- **Better maintenance**: Documentation matches implementation
- **Ready for commits**: Clean git status

---

## Part 8: Post-Cleanup Commits

### Commit 1: Delete Obsolete Files
```
feat: Remove Portainer/Traefik scripts after NGINX migration

- Remove portainer_stack_manager.py, infrastructure_manager.py (old)
- Remove registry_builder.py, github_registry_auth.py
- Remove infrastructure/traefik/ directory
- Remove docker-compose.registry.yml files (3)
- Archive one-time setup scripts

Part of Phase 6 cleanup after successful NGINX/Cloudflare migration.
```

### Commit 2: Update Documentation
```
docs: Update CLAUDE.md and README for NGINX/Cloudflare architecture

- Replace Portainer references with Docker Compose commands
- Update SSL management section (Cloudflare 15-year certs)
- Remove Traefik dashboard from service endpoints
- Update pre-commit checklist
- Archive completed migration documentation

Reflects current state: NGINX reverse proxy, Cloudflare Origin Certificates,
native Docker Compose deployment.
```

### Commit 3: Update Test Suites
```
test: Update test suites for NGINX architecture

- Remove Traefik/Portainer health checks from test_infrastructure.py
- Update quick_service_test.py endpoint list
- Update validate_environment.py for Docker Compose
- Verify tests pass with NGINX routing

All tests updated to match current infrastructure.
```

---

## Summary Statistics

| Category | Count | Details |
|----------|-------|---------|
| **Scripts to Delete** | 8 | Portainer, registry, old DNS management |
| **Scripts to Update** | 8 | Tests, validators, new manager |
| **Docs to Delete/Archive** | 9 | Old migration guides, Let's Encrypt docs |
| **Docs to Update** | 7 | CLAUDE.md, README, deployment status |
| **Directories to Delete (repo)** | 1 + 3 files | infrastructure/traefik/, registry compose files |
| **Directories to Delete (server)** | 4 | ~/infrastructure, ~/traefik, ~/personal-website, ~/letsencrypt |
| **Docker Volumes to Remove** | 7 | Old minecraft and jupyter volumes |
| **Space to Recover (server)** | ~62MB | Old files and packages |
| **Estimated Time** | 3-4 hours | Careful review and testing |

---

## Next Steps

1. **Review this plan** with the user
2. **Create volume backups** before any destructions
3. **Execute repository cleanup** in phases
4. **Execute server cleanup** after backups
5. **Run full test suite** to verify
6. **Create git commits** with clean history

This cleanup will modernize the codebase to match the current NGINX/Cloudflare/Docker Compose architecture, removing ~35-40% of obsolete technical debt from the previous Traefik/Portainer/Let's Encrypt setup.
