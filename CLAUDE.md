# Claude Code Infrastructure Management Guide

This document provides Claude Code with comprehensive instructions for managing the 83RR PowerEdge homelab infrastructure.

## 🎯 Current Architecture (Phase 6 - January 2026)

**Deployment Method**: Native Docker Compose
**Reverse Proxy**: NGINX
**SSL Certificates**: Cloudflare Origin Certificates (15-year validity)
**DNS Provider**: Cloudflare
**Container Runtime**: Docker on Ubuntu 22.04 LTS

### Core Principles
- **Native Docker Compose**: All services deployed via `docker compose` commands
- **Direct Management**: No SSH or API intermediaries required
- **Long-lived Certificates**: Cloudflare Origin Certificates valid until 2040
- **Minimal Complexity**: Straightforward deployment without orchestration layers

---

## 🐍 Python Environment Setup

**IMPORTANT**: Always use the local virtual environment for Python development.

### Setup Commands
```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

### Running Python Scripts
Always activate the virtual environment before running any Python scripts:
```bash
source venv/bin/activate && python script_name.py
```

**All script examples in this document assume the virtual environment is activated.**

---

## 📋 Standard Operating Procedures

### Deploy All Services
```bash
# Navigate to project directory
cd ~/83rr-poweredge

# Deploy all services (production configuration)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Deploy specific service
docker compose up -d <service_name>

# Check deployment status
docker ps
```

### Update Existing Service
```bash
# Pull latest changes
git pull

# Rebuild specific service (if code changed)
docker compose build <service_name>

# Restart service with new configuration
docker compose up -d <service_name>

# Verify service is healthy
docker ps | grep <service_name>
```

### View Logs
```bash
# View logs for specific service
docker compose logs -f <service_name>

# View logs for all services
docker compose logs -f

# View last 100 lines
docker compose logs --tail 100 <service_name>

# Search logs for errors
docker compose logs <service_name> | grep -i error
```

### Stop/Restart Services
```bash
# Stop specific service
docker compose stop <service_name>

# Restart specific service
docker compose restart <service_name>

# Stop all services
docker compose down

# Stop all services and remove volumes (⚠️  DANGER: deletes data)
docker compose down -v
```

---

## 🏗️ Infrastructure Architecture

### Active Services
1. **nginx** - Reverse proxy and SSL termination
2. **personal-website** - Nuxt.js personal portfolio
3. **flask-api** - Python Flask REST API
4. **jupyterhub** - Multi-user JupyterLab data science environment (password-protected)
5. **minecraft** - Minecraft Java Edition server
6. **opensearch** - Log aggregation and search
7. **opensearch-dashboards** - OpenSearch visualization
8. **grafana** - Metrics visualization dashboards (5 provisioned dashboards)
9. **prometheus** - Metrics collection and storage
10. **cadvisor** - Container resource monitoring
11. **fluent-bit** - Log shipper (Docker logs → OpenSearch)
12. **node-exporter** - Host system metrics (CPU, memory, disk)
13. **nginx-exporter** - NGINX metrics for Prometheus

### Service Dependencies
- **nginx** must start first (other services proxy through it)
- **prometheus** should start before **grafana** (datasource dependency)
- All other services are independent

### Environment Variables
Each service can use `.env` files from its infrastructure directory:
- `infrastructure/minecraft/.env` - Minecraft server configuration
- `infrastructure/flask-api/.env` - Flask API secrets
- Root `.env` - Cloudflare credentials and global settings

---

## 📊 Service Endpoints

### Public Services (HTTPS via Cloudflare)
- **https://www.markcheli.com** - Personal website
- **https://flask.markcheli.com** - Flask API
- **https://jupyter.markcheli.com** - JupyterHub (password-protected, multi-user data science environment)
- **minecraft.markcheli.com:25565** - Minecraft server

### LAN-Only Services (HTTPS with Let's Encrypt)
- **https://grafana-local.ops.markcheli.com** - Grafana dashboards (admin/admin123)
- **https://prometheus-local.ops.markcheli.com** - Prometheus metrics
- **https://cadvisor-local.ops.markcheli.com** - Container monitoring
- **https://logs-local.ops.markcheli.com** - OpenSearch Dashboards
- **https://opensearch-local.ops.markcheli.com** - OpenSearch API

### NGINX Routing
All HTTPS traffic is handled by NGINX:
- **Public routes**: Defined in `infrastructure/nginx/conf.d/production.conf`
- **LAN routes**: Defined in `infrastructure/nginx/conf.d/local.conf`
- **SSL certificates**: Located in `infrastructure/nginx/certs/`

---

## 🔐 SSL Certificate Management

### Cloudflare Origin Certificates
This infrastructure uses **Cloudflare Origin Certificates** (not Let's Encrypt):

**Benefits**:
- ✅ **15-year validity** (expires 2040) - no 90-day renewals
- ✅ **Automatic HTTPS** - Cloudflare handles public SSL
- ✅ **Origin protection** - Certificates only work through Cloudflare proxy

**Certificate Files**:
```
infrastructure/nginx/certs/
├── wildcard-markcheli.crt       # Certificate for *.markcheli.com
├── wildcard-markcheli.key       # Private key for *.markcheli.com
├── wildcard-ops-markcheli.crt   # Certificate for *.ops.markcheli.com
└── wildcard-ops-markcheli.key   # Private key for *.ops.markcheli.com
```

### Certificate Renewal (Every 15 Years)
```bash
# When certificates approach expiration (2039-2040):
source venv/bin/activate
python scripts/cloudflare_ssl_manager.py create-wildcards

# Update NGINX certificates
cp new-certs/*.crt infrastructure/nginx/certs/
cp new-certs/*.key infrastructure/nginx/certs/

# Reload NGINX
docker compose exec nginx nginx -s reload
```

### Cloudflare SSL Mode
**Required Setting**: "Full (Strict)" mode in Cloudflare dashboard
- Ensures end-to-end encryption
- Validates origin certificates
- Prevents SSL errors

---

## 🌐 DNS Management with Cloudflare

### DNS Configuration
All DNS records are managed in **Cloudflare Dashboard** (not via API/scripts):

**Public Services** (proxied through Cloudflare):
- `www.markcheli.com` → A record → `173.48.98.211` (public IP)
- `flask.markcheli.com` → A record → `173.48.98.211`
- `jupyter.markcheli.com` → A record → `173.48.98.211`
- `minecraft.markcheli.com` → A record → `173.48.98.211`

**LAN Services** (DNS-only, not proxied):
- `*.ops.markcheli.com` → A record → `192.168.1.179` (LAN IP)
- Used for internal services like Grafana, Prometheus, etc.

### DNS Management Scripts
```bash
# View current DNS records
python scripts/cloudflare_dns_manager.py list

# Add new DNS record
python scripts/cloudflare_dns_manager.py add <subdomain> <ip_address>

# Delete DNS record
python scripts/cloudflare_dns_manager.py delete <subdomain>
```

### DNS Troubleshooting
```bash
# Check DNS resolution
dig www.markcheli.com +short

# Check from specific DNS server
dig @1.1.1.1 www.markcheli.com +short

# Verify SSL certificate
openssl s_client -connect www.markcheli.com:443 -servername www.markcheli.com
```

---

## 📊 Monitoring with Prometheus & Grafana

### Access Monitoring Dashboards
**Grafana**: https://grafana-local.ops.markcheli.com
- **Login**: admin / admin123
- **Pre-configured datasource**: Prometheus
- **Recommended dashboards**: 193, 1860, 14282 (Docker monitoring)

**Prometheus**: https://prometheus-local.ops.markcheli.com
- Query interface for metrics
- 30-day retention policy

**cAdvisor**: https://cadvisor-local.ops.markcheli.com
- Real-time container resource monitoring
- Per-container CPU/memory/network stats

### Key Metrics Monitored
- **CPU usage** per container and total system
- **Memory usage** per container and total system
- **Network I/O** per container
- **Disk I/O** and usage
- **Container health** and restart counts

### Useful Prometheus Queries
```promql
# Container CPU usage (% of total system)
rate(container_cpu_usage_seconds_total{name!=""}[1m]) / scalar(count(count(node_cpu_seconds_total) by (cpu))) * 100

# Container memory usage (GB)
container_memory_usage_bytes{name!=""} / 1024 / 1024 / 1024

# System CPU usage (%)
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

---

## 🔧 Common Operations

### Add New Service
1. **Create service directory**:
   ```bash
   mkdir -p infrastructure/<service>
   ```

2. **Create docker-compose.yml**:
   ```yaml
   services:
     <service>:
       image: <image>
       container_name: <service>
       networks:
         - app-network
       # ... other config
   ```

3. **Add to main docker-compose.yml** (optional) or deploy standalone:
   ```bash
   docker compose -f infrastructure/<service>/docker-compose.yml up -d
   ```

4. **Add NGINX routing** (if web service):
   - Edit `infrastructure/nginx/conf.d/production.conf` or `local.conf`
   - Add upstream and server block
   - Reload NGINX: `docker compose exec nginx nginx -s reload`

5. **Add DNS record** in Cloudflare dashboard

### Update Service Configuration
1. **Edit configuration files** (docker-compose.yml, .env, etc.)
2. **Recreate service**:
   ```bash
   docker compose up -d <service>
   ```
3. **Verify**:
   ```bash
   docker ps | grep <service>
   docker compose logs <service>
   ```

### Troubleshoot Service Issues
```bash
# Check container status
docker ps -a | grep <service>

# View recent logs
docker compose logs --tail 50 <service>

# Check container resource usage
docker stats <service>

# Inspect container details
docker inspect <service>

# Get shell access to container
docker exec -it <service> /bin/bash  # or /bin/sh

# Restart problematic service
docker compose restart <service>
```

### NGINX Configuration Changes
```bash
# Test NGINX configuration
docker compose exec nginx nginx -t

# Reload NGINX (without downtime)
docker compose exec nginx nginx -s reload

# View NGINX error logs
docker compose logs nginx

# Check NGINX routing
docker compose exec nginx cat /etc/nginx/conf.d/production.conf
```

---

## 🚨 Critical Rules for Claude Code

### NEVER Do These
1. **NEVER** commit without running tests
2. **NEVER** ignore or dismiss 4XX/5XX HTTP errors as "expected"
3. **NEVER** delete Docker volumes without verified backups
4. **NEVER** modify production configs without testing locally first
5. **NEVER** assume services are working - always verify

### ALWAYS Do These
1. **ALWAYS** use `docker compose` commands for deployment
2. **ALWAYS** test configuration changes with `nginx -t` before reloading
3. **ALWAYS** check logs after deployment changes
4. **ALWAYS** verify services return HTTP 200 or proper redirects
5. **ALWAYS** run health checks after changes
6. **ALWAYS** investigate 4XX/5XX errors immediately
7. **ALWAYS** create backups before destructive operations
8. **ALWAYS** update `scripts/README.md` when adding or significantly modifying scripts

### Pre-Commit Checklist
```bash
# 1. Verify all services are running
docker ps

# 2. Test service health
curl -I https://www.markcheli.com
curl -I https://flask.markcheli.com
curl http://localhost:9090/-/healthy  # Prometheus

# 3. Check for errors in logs
docker compose logs --tail 100 | grep -i error

# 4. Verify NGINX config is valid
docker compose exec nginx nginx -t

# 5. Run infrastructure tests (if available)
python scripts/test_infrastructure.py
```

---

## 🚨 HTTP Status Code Standards

### Acceptable Responses
- **HTTP 200**: Service functioning correctly ✅
- **HTTP 301/302**: Proper redirects (HTTP→HTTPS) ✅

### Unacceptable Responses (Must Investigate)
- **HTTP 401**: Authentication problems ❌
- **HTTP 403**: Authorization problems ❌
- **HTTP 404**: Missing resources or routing issues ❌
- **HTTP 500+**: Server errors ❌

### Investigation Process
When encountering 4XX/5XX errors:

1. **Do NOT dismiss the error**
2. **Check container health**: `docker ps`
3. **View container logs**: `docker compose logs <service>`
4. **Verify NGINX routing**: Check conf.d files
5. **Test internal connectivity**: `docker exec nginx curl http://<service>:<port>`
6. **Fix the underlying issue**
7. **Re-test to confirm resolution**

---

## 🚨 Surgical Change Protocol

### Change Classification

**🟢 LEVEL 1: Configuration File Changes (90% of requests)**
- **Examples**: Add NGINX route, update environment variable
- **Method**: Edit file, reload service
- **Tools**: Direct file editing, `docker compose exec`
- **Time**: 1-3 minutes

**🟡 LEVEL 2: Container Updates (8% of requests)**
- **Examples**: Update single service, change image version
- **Method**: `docker compose up -d <service>`
- **Time**: 5-10 minutes

**🔴 LEVEL 3: Infrastructure Changes (2% of requests)**
- **Examples**: Add new service, major version upgrades
- **Method**: Full testing, staged rollout
- **Requires**: User approval + backup plan
- **Time**: 15+ minutes

### Minimal Change Principle

**For simple config changes (NGINX routing, env vars)**:
```bash
# ✅ CORRECT: Edit and reload
vim infrastructure/nginx/conf.d/production.conf
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
# Test: curl -I https://new-service.markcheli.com
```

**❌ WRONG: Rebuild everything**:
```bash
# DON'T DO THIS for simple changes
docker compose down
docker compose up -d --build
```

### Pre-Change Checklist
1. **Identify change level** (1, 2, or 3)
2. **Save current state** (git commit or backup)
3. **Plan rollback** (know how to undo)
4. **Make minimal change** (only what's needed)
5. **Test immediately** (verify change works)

---

## 📁 File Structure

```
~/83rr-poweredge/
├── docker-compose.yml              # Base service definitions
├── docker-compose.prod.yml         # Production overrides
├── docker-compose.override.yml     # Local development overrides
├── Makefile                       # Common operations (make help)
├── .env                           # Environment variables
├── CLAUDE.md                      # This document
├── README.md                      # Project overview
├── docs/                          # Documentation files
│
├── infrastructure/
│   ├── nginx/                     # NGINX reverse proxy
│   │   ├── conf.d/
│   │   │   ├── production.conf    # Public service routing
│   │   │   └── local.conf         # LAN service routing
│   │   └── certs/                 # SSL certificates
│   │       ├── wildcard-markcheli.crt
│   │       ├── wildcard-markcheli.key
│   │       ├── wildcard-ops-markcheli.crt
│   │       └── wildcard-ops-markcheli.key
│   │
│   ├── personal-website/          # Nuxt.js website
│   ├── flask-api/                 # Python Flask API
│   ├── jupyter/                   # JupyterHub
│   ├── minecraft/                 # Minecraft server
│   ├── opensearch/                # Log aggregation
│   ├── monitoring/                # Prometheus/Grafana
│   └── fluent-bit/                # Log shipper to OpenSearch
│
└── scripts/
    ├── README.md                         # Script documentation (update this when modifying scripts!)
    ├── test_infrastructure.py            # ⭐ Main testing script
    ├── quick_service_test.py            # 🚀 Quick health checks
    ├── infrastructure_manager.py        # 🏗️ Deployment controller
    ├── cloudflare_dns_manager.py        # 🌐 DNS management
    ├── opensearch_diagnostic_ssh.py     # 📊 Log diagnostics
    ├── renew-letsencrypt-certs.sh       # 🔐 SSL renewal (automated)
    ├── ssh_manager.py                   # ⚠️ Emergency SSH
    ├── one-time/                        # One-time setup scripts
    └── archive/                         # Obsolete/migration scripts
```

---

## 📜 Script Management Protocol

**IMPORTANT:** Claude Code must maintain `scripts/README.md` whenever scripts are modified.

### When to Update scripts/README.md

Update `scripts/README.md` when:
1. **Adding a new script** to the `scripts/` directory
2. **Significantly modifying** an existing script (functionality changes, not just bug fixes)
3. **Archiving a script** (move to `scripts/archive/`)
4. **Changing script usage patterns** or command-line interfaces

### What to Update

When updating scripts/README.md:
- Add/modify the relevant script section with:
  - Purpose and description
  - File size and language
  - Usage examples with actual commands
  - When to use / when not to use
  - Integration points with other scripts
- Update the "Last Updated" timestamp
- Maintain consistent formatting with existing entries
- Keep emoji indicators (⭐ PRIMARY, 🚀 QUICK, etc.)

### Update Format

```markdown
### N. `script_name.py` 🔧 PURPOSE TAG
**Purpose:** Brief one-line description
**Size:** XXkB
**Language:** Python 3

**Description:**
Detailed explanation of what this script does.

**Usage:**
\`\`\`bash
source venv/bin/activate
python scripts/script_name.py [options]
\`\`\`

**When to Use:**
- Bullet points

**Referenced in:** CLAUDE.md, README.md, etc.
```

### Script Categories

- ⭐ PRIMARY - Main infrastructure scripts (testing, deployment)
- 🚀 QUICK - Fast validation/checks
- 🏗️ DEPLOYMENT - Infrastructure deployment
- 🌐 DNS - DNS management
- 📊 DIAGNOSTICS - Troubleshooting and logs
- 🔐 SECURITY - SSL/TLS management
- ⚠️ EMERGENCY - Emergency/fallback tools

---

## 🎯 Success Criteria

Infrastructure is considered healthy when:
1. ✅ All services show as "Up" in `docker ps`
2. ✅ All public services return HTTP 200 or proper redirects
3. ✅ NGINX config passes validation: `nginx -t`
4. ✅ Monitoring dashboards are accessible (Grafana, Prometheus)
5. ✅ Minecraft server responds on port 25565
6. ✅ All Prometheus targets are "up" (prometheus, cadvisor, node-exporter, nginx-exporter)
7. ✅ Logs appearing in OpenSearch (via Fluent Bit)
8. ✅ No error messages in recent logs (`docker compose logs`)

---

## 🚀 Quick Reference Commands

### Makefile Commands (Recommended)
```bash
make help              # Show all available commands
make up                # Start all services (production)
make down              # Stop all services
make status            # Show container status
make health            # Run health checks on all services
make logs              # Follow all logs
make logs s=nginx      # Follow specific service logs
make restart s=nginx   # Restart specific service
make nginx-test        # Test NGINX configuration
make nginx-reload      # Reload NGINX configuration
make build s=NAME      # Build specific service
```

### Direct Docker Compose Commands
```bash
# Deploy everything
cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check status
docker ps

# View logs
docker compose logs -f <service>

# Restart service
docker compose restart <service>

# Reload NGINX config
docker compose exec nginx nginx -s reload

# Test NGINX config
docker compose exec nginx nginx -t

# Health check
curl -I https://www.markcheli.com
curl http://localhost:9090/-/healthy  # Prometheus

# Clean up unused resources
docker system prune -a --volumes  # ⚠️  DANGER: removes unused data
```

---

## 🔑 Environment Configuration

Required variables in `.env`:
```bash
# Cloudflare (for DNS and SSL management)
CLOUDFLARE_API_TOKEN=your_token_here
CLOUDFLARE_ZONE_ID=your_zone_id_here
CLOUDFLARE_EMAIL=your_email@example.com

# Optional: Service-specific configurations
# See infrastructure/<service>/.env files for service-specific vars
```

---

## 📖 Additional Documentation

- **docs/DEPLOYMENT_STATUS.md** - Current service status and deployment notes
- **Makefile** - Run `make help` for available commands
- **infrastructure/nginx/README.md** - NGINX configuration guide
- **infrastructure/monitoring/README.md** - Prometheus/Grafana monitoring guide
- **infrastructure/fluent-bit/README.md** - Fluent Bit log shipping guide
- **scripts/README.md** - Python script documentation

---

**Last Updated**: January 4, 2026
**Architecture Version**: Phase 6 (NGINX + Cloudflare + Docker Compose)
**Status**: Production-ready, all services operational
