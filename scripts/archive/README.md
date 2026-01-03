# Archived Scripts

This directory contains scripts that are no longer actively used but are preserved for historical reference.

**Archive Date:** January 2, 2026
**Reason:** Phase 6 infrastructure migration completed (NGINX + Cloudflare + Docker Compose)

---

## Why These Scripts Were Archived

The infrastructure underwent a major migration from Phase 5 (Traefik + Let's Encrypt + Portainer) to Phase 6 (NGINX + Cloudflare Origin Certificates + Native Docker Compose). These scripts were part of that migration or are no longer needed with the new architecture.

---

## Archived Scripts (18 total)

### Cloudflare SSL Management (Obsolete - Replaced by Static Origin Certs)

1. **cloudflare_ssl_manager.py** (23KB)
   - **Purpose:** Dynamic SSL certificate creation via Cloudflare API
   - **Why Archived:** Public services now use static Cloudflare Origin Certificates (15-year validity)
   - **Replacement:** Manual Origin Cert download from Cloudflare dashboard (one-time)

2. **cloudflare_ssl_permissions_guide.py** (6.3KB)
   - **Purpose:** Guide for setting up Cloudflare API permissions
   - **Why Archived:** One-time setup completed, no longer needed
   - **Replacement:** None (setup complete)

3. **debug_cloudflare_auth.py** (3.8KB)
   - **Purpose:** Debug Cloudflare API authentication issues
   - **Why Archived:** Authentication working, debugging no longer needed
   - **Replacement:** None

4. **setup_cloudflare_auth.py** (6.6KB)
   - **Purpose:** Initial Cloudflare authentication setup
   - **Why Archived:** One-time setup completed
   - **Replacement:** None (setup complete)

5. **set_cloudflare_env.py** (4.0KB)
   - **Purpose:** Set Cloudflare environment variables
   - **Why Archived:** Environment configured, no longer needed
   - **Replacement:** Variables in `.env` file

6. **test_cloudflare_ssl_api.py** (4.3KB)
   - **Purpose:** Test Cloudflare SSL API functionality
   - **Why Archived:** API working, testing complete
   - **Replacement:** None

7. **test_csr_generation.py** (3.0KB)
   - **Purpose:** Test CSR (Certificate Signing Request) generation
   - **Why Archived:** Origin Certs don't require CSRs
   - **Replacement:** None

8. **test_ssl_creation.py** (2.8KB)
   - **Purpose:** Test automated SSL certificate creation
   - **Why Archived:** Using static certificates now
   - **Replacement:** None

### Let's Encrypt Manual Setup (Obsolete - Replaced by Automated Renewal)

9. **setup_manual_wildcard_ssl.sh** (9.7KB)
   - **Purpose:** Manual Let's Encrypt wildcard certificate setup
   - **Why Archived:** Replaced by automated renewal via cron
   - **Replacement:** `renew-letsencrypt-certs.sh` (automated)

10. **generate_dev_certificates.sh** (2.1KB)
    - **Purpose:** Generate self-signed certificates for development
    - **Why Archived:** Using real Let's Encrypt certificates for all environments
    - **Replacement:** Let's Encrypt certificates (*.ops.markcheli.com)

### Migration Scripts (Completed - No Longer Needed)

11. **traefik_to_nginx_migration.py** (9.4KB)
    - **Purpose:** Migrate from Traefik reverse proxy to NGINX
    - **Why Archived:** Migration completed successfully
    - **Replacement:** Native Docker Compose + NGINX configuration
    - **Note:** Keep for reference in case of rollback needs

12. **deploy.sh** (8.4KB)
    - **Purpose:** Legacy SSH-based deployment script
    - **Why Archived:** Replaced by native Docker Compose deployment
    - **Replacement:** `docker compose` commands and `infrastructure_manager.py`

### Testing/Validation Scripts (One-Time Use)

13. **test_local_environment.py** (5.4KB)
    - **Purpose:** Test local development environment
    - **Why Archived:** One-time testing completed
    - **Replacement:** `test_infrastructure.py` for ongoing testing

14. **test_nginx_config.py** (9.0KB)
    - **Purpose:** Validate NGINX configuration during migration
    - **Why Archived:** Migration complete, NGINX config validated
    - **Replacement:** `test_infrastructure.py` includes NGINX tests

15. **validate_environment.py** (6.8KB)
    - **Purpose:** Validate infrastructure environment setup
    - **Why Archived:** Environment validated, ongoing checks in main test suite
    - **Replacement:** `test_infrastructure.py`

### OpenSearch Setup Scripts (One-Time Use)

16. **opensearch_diagnostic.py** (13KB)
    - **Purpose:** OpenSearch diagnostics (local version)
    - **Why Archived:** Replaced by SSH version with more features
    - **Replacement:** `opensearch_diagnostic_ssh.py`

17. **setup_opensearch_dashboards.py** (5.8KB)
    - **Purpose:** Initial OpenSearch Dashboards setup
    - **Why Archived:** One-time setup completed
    - **Replacement:** None (setup complete)

18. **fix_opensearch_index_patterns.py** (4.4KB)
    - **Purpose:** Fix index patterns in OpenSearch
    - **Why Archived:** Index patterns fixed, no longer needed
    - **Replacement:** None

---

## Can These Scripts Be Deleted?

**Recommendation:** Keep archived for now (at least 6-12 months)

**Reasons to Keep:**
- Historical reference for how migration was done
- Rollback capability if needed
- Learning resource for future migrations
- Troubleshooting reference

**Consider Deleting After:**
- Phase 6 infrastructure stable for 6+ months
- No rollback needs identified
- Migration fully documented elsewhere

**If Deleting:**
1. Ensure migration is fully documented in git history
2. Verify all functionality replicated in new scripts
3. Create summary document of what was learned
4. Delete via git (preserves history): `git rm scripts/archive/*`

---

## Restoration Process

If you need to restore an archived script:

1. **Copy back to scripts directory:**
   ```bash
   cp scripts/archive/script_name.{py,sh} scripts/
   ```

2. **Update SCRIPTS.md:**
   - Add script documentation
   - Explain why it was restored

3. **Test thoroughly:**
   ```bash
   python scripts/test_infrastructure.py
   ```

4. **Commit changes:**
   ```bash
   git add scripts/script_name.{py,sh} scripts/SCRIPTS.md
   git commit -m "Restore script_name.{py,sh}: [reason]"
   ```

---

## Related Documentation

- **../SCRIPTS.md** - Active scripts documentation
- **CLAUDE.md** - Infrastructure management guide
- **docs/archive/** - Archived infrastructure documentation

---

**Last Updated:** January 2, 2026
