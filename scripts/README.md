# Infrastructure Scripts Documentation

This directory contains all active infrastructure management scripts for the 83RR PowerEdge homelab.

**Last Updated:** November 1, 2026
**Infrastructure Version:** Phase 6 (NGINX + Cloudflare + Docker Compose)
**Architecture:** Local execution (Docker Compose + Makefile)

---

## 📋 Active Scripts

### 1. `test_infrastructure.py` ⭐ PRIMARY TESTING
**Purpose:** Comprehensive infrastructure health testing
**Size:** 28KB
**Language:** Python 3

**Description:**
Main testing script that validates all infrastructure components. Should be run before every git commit to ensure system health.

**Tests Performed:**
- DNS resolution for every public and `*.ops` hostname; `*.ops` records must point at `LOCAL_IP` (.env)
- Docker container status for all compose services (+ `healthy` where a healthcheck exists)
- OpenSearch cluster health, log indices, today's log ingestion
- SSL certificate validation, HTTP status, expected content and response time for public services (website, flask, cookbook, plex, seafile + `/notification/ping`, home assistant, tallied/tasks `/api/health`, uptime-kuma status page) and LAN services (grafana, daily-report, energy-monitor, openclaw)
- nginx basic-auth gate (`auth_basic "Ops Services"`) on logs/opensearch/prometheus/cadvisor `.ops` vhosts: without credentials, PASS only on a genuine nginx `401` + `WWW-Authenticate: Basic realm="Ops Services"` (labelled "Auth-gated"); set `OPS_BASIC_AUTH_USER` / `OPS_BASIC_AUTH_PASSWORD` in `.env` to test the upstreams end-to-end (expects 200 + content)
- Minecraft server TCP connection
- Backups: NAS mounted at `/mnt/nas` (WARN) and last `backup-heartbeat` from `backup.sh` in OpenSearch within 26h (FAIL otherwise)
- Git working tree / sync status

**Usage:**
```bash
source venv/bin/activate
python scripts/test_infrastructure.py
```

**Expected Results:**
- 0 failures; warnings only for uncommitted changes or a transiently unmounted NAS
- All critical services return HTTP 200 or proper redirects
- NO unexplained 4XX errors (the only accepted 401 is the verified nginx "Ops Services" gate)

**Referenced in:** CLAUDE.md (pre-commit checklist)

---

### 2. `quick_service_test.py` 🚀 QUICK VALIDATION
**Purpose:** Fast service health checks
**Size:** 2.0KB
**Language:** Python 3

**Description:**
Lightweight alternative to full test suite. Quick validation of critical services for rapid feedback during development.

**Tests:**
- Public services (www, flask, minecraft)
- LAN services (grafana, prometheus, logs, opensearch)
- Basic HTTP response codes

**Usage:**
```bash
source venv/bin/activate
python scripts/quick_service_test.py
```

**Use When:**
- Making small changes and need quick validation
- Don't need comprehensive testing
- Want fast feedback loop

---

### 3. `infrastructure_manager.py` 🏗️ DEPLOYMENT CONTROLLER
**Purpose:** Native Docker Compose infrastructure management
**Size:** 15KB
**Language:** Python 3

**Description:**
Master controller for infrastructure deployment using native Docker Compose (no Portainer dependency).

**Features:**
- Environment-aware deployment (development vs production)
- Auto-build and push for production deployments
- Health monitoring and validation
- Service availability testing
- Comprehensive logging

**Usage:**
```bash
source venv/bin/activate

# Deploy all services
python scripts/infrastructure_manager.py deploy-all

# Deploy specific service
python scripts/infrastructure_manager.py deploy <service_name>

# Health check all services
python scripts/infrastructure_manager.py health-check-all

# Run full tests
python scripts/infrastructure_manager.py run-tests
```

**Key Commands:**
- `deploy-all` - Deploy entire infrastructure
- `deploy <service>` - Deploy specific service
- `health-check-all` - Check health of all services
- `run-tests` - Run comprehensive test suite
- `logs recent` - View recent container logs
- `logs errors` - View error logs

---

### 4. `cloudflare_dns_manager.py` 🌐 DNS MANAGEMENT
**Purpose:** Cloudflare DNS record management
**Size:** 18KB
**Language:** Python 3

**Description:**
Manages DNS records in Cloudflare for both public and LAN services.

**Features:**
- List all DNS records
- Add new DNS records
- Delete DNS records
- Update existing records
- Audit current DNS configuration

**Usage:**
```bash
source venv/bin/activate

# List all DNS records
python scripts/cloudflare_dns_manager.py list

# Add A record
python scripts/cloudflare_dns_manager.py add <subdomain> <ip_address>

# Delete record
python scripts/cloudflare_dns_manager.py delete <subdomain>

# Audit configuration
python scripts/cloudflare_dns_manager.py audit
```

**Environment Variables Required:**
- `CLOUDFLARE_API_TOKEN` - Cloudflare API token with DNS edit permissions
- `CLOUDFLARE_ZONE_ID` - Zone ID for markcheli.com

**Referenced in:** CLAUDE.md (DNS management section)

---

### 5. `opensearch_diagnostic.py` 📊 LOG DIAGNOSTICS
**Purpose:** OpenSearch cluster diagnostics and log analysis
**Size:** 11KB
**Language:** Python 3

**Description:**
Diagnostic tool for OpenSearch logging infrastructure. Runs locally using direct Docker commands (no SSH required).

**Features:**
- Cluster health monitoring
- Index listing and statistics
- Log searching with filters
- Recent log retrieval
- Error log analysis
- Test log injection

**Usage:**
```bash
source venv/bin/activate

# Check cluster health
python scripts/opensearch_diagnostic.py health

# List indices
python scripts/opensearch_diagnostic.py indices

# View recent logs (last hour)
python scripts/opensearch_diagnostic.py recent

# View recent logs (custom time)
python scripts/opensearch_diagnostic.py recent --hours 24

# Search for errors
python scripts/opensearch_diagnostic.py errors --hours 6

# Search for specific term
python scripts/opensearch_diagnostic.py search "connection failed"

# Add test log entry
python scripts/opensearch_diagnostic.py test-log
```

**Integration:**
- Can be called via `infrastructure_manager.py logs` commands
- Provides centralized log access across all containers

---

### 6. `renew-letsencrypt-certs.sh` 🔐 SSL RENEWAL
**Purpose:** Automated Let's Encrypt certificate renewal
**Size:** 1.2KB
**Language:** Bash

**Description:**
Automated renewal script for Let's Encrypt wildcard certificates (*.ops.markcheli.com). Configured to run via cron.

**What It Does:**
1. Runs `certbot renew` with Cloudflare DNS plugin
2. Copies renewed certificates to NGINX cert directory
3. Reloads NGINX to apply new certificates
4. Logs all operations

**Cron Schedule:**
```cron
0 3 * * * /home/mcheli/83rr-poweredge/scripts/renew-letsencrypt-certs.sh >> /var/log/letsencrypt-renewal.log 2>&1
```

**Manual Execution:**
```bash
./scripts/renew-letsencrypt-certs.sh
```

**Certificates Managed:**
- `*.ops.markcheli.com` - Wildcard for LAN services
- Auto-renews 30 days before expiration
- No manual intervention required

**Note:** Public services (*.markcheli.com) use Cloudflare Origin Certificates (15-year validity, no renewal needed)

---

### 7. `ssh_manager.py` ⚠️ ARCHIVED / EMERGENCY ONLY
**Purpose:** Emergency SSH operations (DEPRECATED - SSH no longer required)
**Size:** 3.7KB
**Language:** Python 3

**Description:**
Legacy SSH tool. **DEPRECATED:** All scripts now run locally without SSH. Keep for emergency remote troubleshooting only.

**Features:**
- Single SSH command execution
- Multiple command batching
- Session management
- Connection pooling

**Usage:**
```bash
source venv/bin/activate

# Single command
python scripts/ssh_manager.py run "docker ps"

# Multiple commands
python scripts/ssh_manager.py batch "docker ps" "docker stats --no-stream"
```

**When to Use:**
- Docker daemon issues
- Container accessibility problems
- Network troubleshooting
- System-level diagnostics

**When NOT to Use:**
- Normal deployments (use `docker compose` instead)
- Regular management (use `infrastructure_manager.py`)
- Log viewing (use `opensearch_diagnostic_ssh.py`)

**Note:** This is a fallback tool. Primary operations should use Docker Compose directly.

---

### 8. `emit_security_telemetry.sh` 🔐 SECURITY TELEMETRY

**Purpose:** Emit host security signals into OpenSearch for alerting
**Size:** ~3KB
**Language:** Bash

**Description:**
Cron collector (every 10 min, as `mcheli`) that ships two signals into
`logs-homelab-*` so the OpenSearch alerting monitors can fire:
- `security_unexpected_port` — a TCP port is LISTENing that is not in the
  script's `ALLOWED_PORTS` allowlist (rogue/new service, bad container publish).
- `security_external_db_conn` — an ESTABLISHED connection to a sensitive
  backend port (OpenSearch 9200/9300, Postgres 5432, Grafana 3000) from a
  non-loopback, non-docker-bridge peer (firewall/NAT gap or lateral movement).

Read-only (`ss`), no sudo. Uses the same in-container OpenSearch `_doc`
endpoint as `emit_host_metrics.sh` / `backup.sh`. All failures non-fatal.

**Paired monitors** (`infrastructure/opensearch/config/alerting/monitors/`):
`security-unexpected-listen-port.json`, `security-external-db-conn.json`,
`docker-exec-into-sock-container.json` — apply via the loop in
`infrastructure/opensearch/config/alerting/README.md`.

**Usage:**
```bash
# Runs from cron; manual run:
/home/mcheli/83rr-poweredge/scripts/emit_security_telemetry.sh
```

**When to Use:**
- Runs automatically; run manually to seed/test telemetry after changes.

**Maintenance:** when you intentionally add a service/port, add the port to
`ALLOWED_PORTS` or the unexpected-port monitor will alert.

**Referenced in:** CLAUDE.md (security backlog E3)

---

### 9. `alert-test.sh` 🚀 ALERT PATH CHECK

**Purpose:** Prove that OpenSearch alerting and Uptime Kuma can still reach ntfy
**Size:** ~2KB
**Language:** Bash

**Description:**
Sends one test alert through OpenSearch alerting (a one-off monitor run via
`infrastructure/opensearch/config/alerting/wire-ntfy.py --test-only`, the same
path a real alert takes) and one through Uptime Kuma's own ntfy provider
(`infrastructure/ntfy/kuma-ntfy.js test`), then checks that both landed in
ntfy's message cache (topic `homelab`). Prints `ALERT TEST OK` / `ALERT TEST
FAILED` and exits non-zero on failure. Reads no secrets itself. Each run sends
two pushes to Mark's phone.

Exists because alerting silently failed from 2026-09-04 to 2026-10-31 (SendGrid
out of credits) and nothing noticed.

**Usage:**
```bash
~/83rr-poweredge/scripts/alert-test.sh
```

**When to Use:**
- Weekly: the Mac mini's homelab-weekly-check runs it (`act.sh alert-test`).
- After touching ntfy, the `ntfy-homelab` channel, monitors or Kuma notifications.

**Referenced in:** infrastructure/opensearch/config/alerting/README.md

---

### 10. `sbom-scan.sh` 🔐 SBOM / CVE SCAN

**Purpose:** Nightly SBOM of every running container, uploaded to Dependency-Track
**Size:** ~17KB
**Language:** Bash (+ python3 for JSON)

**Description:**
For each running container: resolves image ID, tag and registry digest, makes
a CycloneDX SBOM of that exact image with Syft (`~/.local/bin/syft`), and
uploads it to Dependency-Track as project `<container>`, version
`<tag>@<digest12>`, marked latest. Existing versions are skipped (idempotent);
when an image changes, the previous latest is cloned first so old findings
and audit decisions carry over and only new findings alert. After each upload
every non-latest version of that project is deactivated (not deleted), so the
portfolio metrics count only what runs; needs `PORTFOLIO_MANAGEMENT`, else it
warns and continues. Talks to `deptrack-apiserver` on the docker bridge (no nginx),
reads `DT_API_KEY` / `NTFY_PUBLISH_TOKEN` from `.env`, logs to
`logs/sbom-scan.log`, sends one ntfy push (topic `homelab`) only on failure.
No sudo; needs the docker group.

**Usage:**
```bash
scripts/sbom-scan.sh                  # what cron runs (03:30)
scripts/sbom-scan.sh --dry-run        # list what would be uploaded
scripts/sbom-scan.sh --only plex      # one container
scripts/sbom-scan.sh --force          # re-upload unchanged images too
scripts/sbom-scan.sh --deactivate-superseded-only [--dry-run]   # no scan: deactivate all non-latest versions
scripts/sbom-scan.sh --deactivate-missing [--dry-run]            # no scan: deactivate projects whose container is gone (after removing a service; not in cron)
```

**When to Use:**
- Runs from mcheli's crontab: `30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1`
- Manually after bumping an image, to see its findings before the next night.
- `--deactivate-missing` once, by hand, after removing a service: sets `active=false` on every version of each `sbom-scan`-tagged project whose name matches no existing container, running or stopped (refuses if `docker ps -a` is empty). If the container returns, the nightly run reactivates its version as latest.

**Referenced in:** docs/dependency-track.md

---

### 11. `install-syft.sh` 🔐 SUPPLY CHAIN

**Purpose:** Install the pinned, verified Syft release used by `sbom-scan.sh`
**Size:** ~4KB
**Language:** Bash

**Description:**
Downloads `syft_<ver>_linux_amd64.tar.gz` and checks it against the sha256
pinned in the script (taken from the release's `checksums.txt` after its
Sigstore signature was verified with cosign). Also checks the published
checksums file agrees, and re-verifies the signature when cosign is
installed. Installs to `~/.local/bin/syft`; no-op if that version is already
there. Trivy is intentionally not used (March 2026 release compromise).

**Usage:**
```bash
scripts/install-syft.sh            # install / no-op
scripts/install-syft.sh --force    # reinstall
```

**When to Use:**
- Once at deploy; again after bumping `SYFT_VERSION` + `SYFT_SHA256` (steps in the script header).

**Referenced in:** docs/dependency-track.md

---

### 12. `deptrack-setup.sh` 🏗️ DEPLOYMENT

**Purpose:** First boot and idempotent configuration of Dependency-Track
**Size:** ~27KB
**Language:** Bash (+ python3 for JSON)

**Description:**
`init-admin` replaces the default admin/admin password with a random one in a
0600 file (for 1Password). `apply` sets the base URL, enables OSV + NVD
(GitHub Advisories only with `DT_GITHUB_TOKEN`) and starts mirrors, stores the
ntfy token as a DT secret, installs the `ntfy` webhook publisher with
`infrastructure/dependency-track/ntfy-template.peb`, creates the alert policy
(CEL: any KEV finding, or HIGH/CRITICAL with EPSS >= 0.1 in an internet-exposed
project, list in `INTERNET_PROJECTS`) and the push rule that fires only on
that policy's violations (created disabled; renames the old severity rule in
place), adds the weekly digest (scheduled `NEW_VULNERABILITIES_SUMMARY` rule,
Saturdays 13:00 UTC), and creates team `sbom-scanner` with an API key written
to `.env` as `DT_API_KEY`. `triage-key` creates team `triage`
(VIEW_PORTFOLIO, VIEW_VULNERABILITY, VULNERABILITY_ANALYSIS) and writes its
key to `.env` as `DT_TRIAGE_API_KEY`. Every step checks state first;
re-running is safe.

**Usage:**
```bash
scripts/deptrack-setup.sh init-admin
scripts/deptrack-setup.sh apply
scripts/deptrack-setup.sh triage-key    # key for the weekly sweep -> DT_TRIAGE_API_KEY
scripts/deptrack-setup.sh status        # mirrors, projects, rules on/off, policy
scripts/deptrack-setup.sh alerts on|off # push rule only; the digest keeps running
scripts/deptrack-setup.sh test-alert    # push + digest test, verified in ntfy's cache
```

**When to Use:**
- Deploy (see the runbook in docs/dependency-track.md), after rotating the ntfy token or scanner key, and after changing which services are internet-exposed (`INTERNET_PROJECTS`).

**Referenced in:** docs/dependency-track.md

---

## 📁 Directory Structure

```
scripts/
├── README.md                         # This file (documentation)
├── test_infrastructure.py            # ⭐ Main testing script
├── quick_service_test.py            # 🚀 Quick health checks
├── infrastructure_manager.py        # 🏗️ Deployment controller
├── cloudflare_dns_manager.py        # 🌐 DNS management
├── opensearch_diagnostic_ssh.py     # 📊 Log diagnostics
├── renew-letsencrypt-certs.sh       # 🔐 SSL renewal (automated)
├── alert-test.sh                    # 🚀 Weekly alert path check (ntfy)
├── sbom-scan.sh                     # 🔐 Nightly container SBOMs -> Dependency-Track
├── install-syft.sh                  # 🔐 Pinned, verified Syft install
├── deptrack-setup.sh                # 🏗️ Dependency-Track first boot / config
├── ssh_manager.py                   # ⚠️ Emergency SSH
├── one-time/                        # One-time setup scripts
│   ├── README.md
│   ├── setup_data_disk.sh
│   ├── migrate_docker_to_data_disk.sh
│   ├── restart_and_verify_docker.sh
│   ├── cleanup_docker_backup.sh
│   └── seafile_conf_migrate.py      # Seafile 11→12→13 config edits (docs/seafile-upgrade-2026-11.md)
└── archive/                         # Obsolete/migration scripts
    ├── (18 archived scripts from Phase 5 migration)
    └── README.md
```

---

## 🔄 Script Workflow

### Standard Deployment Workflow:
```bash
# 1. Make infrastructure changes
vim docker-compose.yml

# 2. Deploy services
python scripts/infrastructure_manager.py deploy-all

# 3. Run quick validation
python scripts/quick_service_test.py

# 4. Run comprehensive tests
python scripts/test_infrastructure.py

# 5. Commit if tests pass
git add -A && git commit -m "Your changes"
```

### Troubleshooting Workflow:
```bash
# 1. Quick service check
python scripts/quick_service_test.py

# 2. Check container health
python scripts/infrastructure_manager.py health-check-all

# 3. View recent logs
python scripts/infrastructure_manager.py logs recent

# 4. Search for errors
python scripts/infrastructure_manager.py logs errors

# 5. Deep dive with OpenSearch
python scripts/opensearch_diagnostic_ssh.py errors --hours 24
```

---

## 📝 Maintenance Instructions

### Adding a New Script

When adding a new script to this directory:

1. **Create the script** with proper shebang and documentation
2. **Add executable permissions** (if shell script): `chmod +x script_name.sh`
3. **Update this file** (`README.md`) with:
   - Script name and purpose
   - Size and language
   - Comprehensive description
   - Usage examples
   - When to use / when not to use
4. **Update CLAUDE.md** if script changes standard workflows
5. **Add to git**: `git add scripts/script_name.{py,sh} scripts/README.md`
6. **Commit with description**: Explain what the script does and why it's needed

### Modifying an Existing Script

When significantly modifying a script:

1. **Make your changes** to the script
2. **Update this file** (`README.md`) to reflect:
   - New features or functionality
   - Changed usage patterns
   - Updated examples
   - New dependencies or requirements
3. **Test thoroughly**: Run both the script and `test_infrastructure.py`
4. **Update CLAUDE.md** if workflows change
5. **Commit with details**: Explain what changed and why

### Archiving a Script

When a script becomes obsolete:

1. **Move to archive**: `mv scripts/script_name.{py,sh} scripts/archive/`
2. **Update archive/README.md**: Document why it was archived
3. **Remove from this file** (`README.md`)
4. **Update CLAUDE.md**: Remove references to archived script
5. **Commit**: Explain why script is no longer needed

---

## 🎯 Quick Reference

**Makefile Commands (Recommended):**
```bash
make help              # Show all available commands
make up                # Start all services
make status            # Show container status
make health            # Run health checks
make logs s=nginx      # View specific service logs
```

**Before Every Commit:**
```bash
make health
# or: python scripts/test_infrastructure.py
```

**After Infrastructure Changes:**
```bash
make up                # Deploy all services
make health            # Verify health
```

**View Logs:**
```bash
make logs              # All logs
make logs s=grafana    # Specific service
python scripts/opensearch_diagnostic.py recent --hours 24
```

**DNS Changes:**
```bash
python scripts/cloudflare_dns_manager.py list
python scripts/cloudflare_dns_manager.py add <subdomain> <ip>
```

**Emergency Troubleshooting:**
```bash
make status            # Check containers
docker ps -a           # All containers including stopped
python scripts/infrastructure_manager.py health-check-all
```

---

## ⚙️ Environment Setup

All Python scripts require the virtual environment:

```bash
# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

**Required Environment Variables:**
- `CLOUDFLARE_API_TOKEN` - For DNS management
- `CLOUDFLARE_ZONE_ID` - For DNS management
- `SSH_HOST` - Server IP (192.168.1.179)
- `SSH_USER` - Server username (mcheli)

**Load from .env:**
```bash
# .env file in project root is auto-loaded by scripts
cat .env | grep CLOUDFLARE
```

---

## 📚 Related Documentation

- **CLAUDE.md** - Complete infrastructure management guide with SOPs
- **README.md** - Project overview and quick start
- **docs/DEPLOYMENT_STATUS.md** - Current deployment status
- **scripts/one-time/README.md** - One-time setup scripts documentation
- **scripts/archive/README.md** - Archived scripts documentation

---

**🤖 Auto-Update Instruction:**

Claude Code should automatically update this file whenever:
- A new script is added to the `scripts/` directory
- An existing script is significantly modified (functionality changes, not just bug fixes)
- A script is moved to archive
- Script usage patterns change

Update format: Add/modify the relevant section with current information, update "Last Updated" date, maintain consistent formatting with existing entries.
