# Infrastructure Scripts Documentation

This directory contains all active infrastructure management scripts for the 83RR PowerEdge homelab.

**Last Updated:** January 4, 2026
**Infrastructure Version:** Phase 6 (NGINX + Cloudflare + Docker Compose)
**Architecture:** Local execution (Docker Compose + Makefile)

---

## 📋 Active Scripts

### 1. `test_infrastructure.py` ⭐ PRIMARY TESTING
**Purpose:** Comprehensive infrastructure health testing
**Size:** 20KB
**Language:** Python 3

**Description:**
Main testing script that validates all infrastructure components. Should be run before every git commit to ensure system health.

**Tests Performed:**
- DNS resolution (Cloudflare and local)
- SSL certificate validation
- HTTP/HTTPS endpoint availability
- Service health checks (all services)
- Docker container status
- Network connectivity
- Minecraft server connection
- Prometheus target health

**Usage:**
```bash
source venv/bin/activate
python scripts/test_infrastructure.py
```

**Expected Results:**
- 53+ of 56 tests should pass
- All critical services return HTTP 200 or proper redirects
- NO 4XX errors allowed (indicates real problems)

**Referenced in:** CLAUDE.md (pre-commit checklist)

---

### 2. `quick_service_test.py` 🚀 QUICK VALIDATION
**Purpose:** Fast service health checks
**Size:** 2.0KB
**Language:** Python 3

**Description:**
Lightweight alternative to full test suite. Quick validation of critical services for rapid feedback during development.

**Tests:**
- Public services (www, flask, jupyter, minecraft)
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
├── ssh_manager.py                   # ⚠️ Emergency SSH
├── one-time/                        # One-time setup scripts
│   ├── README.md
│   ├── setup_data_disk.sh
│   ├── migrate_docker_to_data_disk.sh
│   ├── restart_and_verify_docker.sh
│   └── cleanup_docker_backup.sh
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
- **DEPLOYMENT_STATUS.md** - Current deployment status
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
