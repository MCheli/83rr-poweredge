# Claude Code Infrastructure Management Guide

This document provides Claude Code with comprehensive instructions for managing the 83RR PowerEdge homelab infrastructure.

## 🎯 CRITICAL: Registry-Based Infrastructure Management

**PRIMARY: All infrastructure uses registry-based deployment via Portainer API (NO SSH required)**
**FALLBACK: SSH available for emergency troubleshooting ONLY**

### Core Management Scripts (8 total - streamlined)

1. **`scripts/infrastructure_manager.py`** - MASTER infrastructure controller
   - Deploy entire infrastructure with `--registry` flag
   - Health monitoring and validation
   - Container image building and pushing
   - Registry authentication management
   - Migration and cleanup operations

2. **`scripts/portainer_stack_manager.py`** - UNIFIED Portainer API management
   - All CRUD operations for individual stacks
   - Direct Portainer API integration
   - Proper environment variable handling

3. **`scripts/registry_builder.py`** - Container registry deployment system
   - Build images locally with Docker build contexts
   - Push to GitHub Container Registry (ghcr.io)
   - Generate registry-based compose files
   - Multi-platform build support

4. **`scripts/github_registry_auth.py`** - ROBUST authentication management
   - Multiple authentication methods (GITHUB_TOKEN, PAT, credentials file)
   - Automatic credential validation and refresh
   - Server-side authentication setup
   - Security best practices implementation

5. **`scripts/test_infrastructure.py`** - Comprehensive health testing
   - Must pass before any commits
   - Tests all services, DNS, containers, and functionality
   - Includes Minecraft server connectivity testing

6. **`scripts/quick_service_test.py`** - Fast service health checks
   - Quick validation of critical services
   - Lightweight alternative to full test suite

7. **`scripts/dns_manager.py`** - DNS and SSL certificate management
   - Domain configuration and SSL automation
   - Certificate lifecycle management

8. **`scripts/ssh_manager.py`** - EMERGENCY troubleshooting ONLY
   - ⚠️  Use ONLY when Portainer API is unavailable
   - Server connectivity testing and emergency operations

## 🐍 CRITICAL: Python Environment Setup

**IMPORTANT**: Always use the local virtual environment for Python development.

### Setup Commands:
```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

### Running Python Scripts:
Always activate the virtual environment before running any Python scripts:
```bash
source venv/bin/activate && python script_name.py
```

**All script examples in this document assume the virtual environment is activated.**

## 📋 Standard Operating Procedures

### Deploying Individual Stacks

```bash
# Smart deploy (create or update automatically)
python scripts/portainer_stack_manager.py deploy <stack_name> <compose_file>

# Examples:
python scripts/portainer_stack_manager.py deploy minecraft infrastructure/minecraft/docker-compose.yml
python scripts/portainer_stack_manager.py deploy flask-api infrastructure/flask-api/docker-compose.yml

# Create new stack only
python scripts/portainer_stack_manager.py create minecraft infrastructure/minecraft/docker-compose.yml

# Update existing stack only
python scripts/portainer_stack_manager.py update minecraft infrastructure/minecraft/docker-compose.yml
```

### Managing Complete Infrastructure

```bash
# 🚀 PREFERRED: Registry-based deployment (NO SSH required)
python scripts/infrastructure_manager.py deploy-all --registry --clean

# Registry authentication management
python scripts/infrastructure_manager.py test-registry-auth        # Test authentication
python scripts/infrastructure_manager.py setup-registry-auth      # Setup server authentication

# Build and push container images
python scripts/infrastructure_manager.py build-images              # Build images
python scripts/infrastructure_manager.py push-images               # Push to registry
python scripts/infrastructure_manager.py build-and-push           # Combined build+push

# Health monitoring
python scripts/infrastructure_manager.py health-check-all          # Health check all stacks
python scripts/infrastructure_manager.py run-tests                 # Comprehensive tests

# LEGACY: Deploy without registry (hybrid SSH + API - deprecated)
python scripts/infrastructure_manager.py deploy-all --clean

# Migration and cleanup
python scripts/infrastructure_manager.py migrate-to-portainer      # Migrate to Portainer
```

### Monitoring and Troubleshooting

```bash
# List all Portainer stacks
python scripts/portainer_stack_manager.py list

# Check specific stack status
python scripts/portainer_stack_manager.py status minecraft

# Health check specific stack
python scripts/portainer_stack_manager.py health minecraft

# Test registry authentication
python scripts/github_registry_auth.py test

# Quick service testing
python scripts/quick_service_test.py
```

## 🏗️ Infrastructure Architecture

### Stack Deployment Order
The system deploys stacks in dependency order:
1. **traefik** - Reverse proxy (must be first)
2. **jupyter** - Data science environment
3. **opensearch** - Logging infrastructure
4. **personal-website** - Web services
5. **flask-api** - API services
6. **minecraft** - Game services
7. **monitoring** - System and container monitoring (Prometheus/Grafana)

### Environment Variables
Each stack automatically loads `.env` files from its infrastructure directory:
- `infrastructure/minecraft/.env`
- `infrastructure/flask-api/.env`
- etc.

### Portainer Integration
All stacks are managed through Portainer API ensuring:
- Proper visibility in Portainer UI
- Centralized management
- Environment variable persistence
- Update/rollback capabilities

## 🚨 Critical Rules for Claude Code

### NEVER Do These:
1. **NEVER** use `ssh ... docker compose` commands directly
2. **NEVER** deploy stacks via SSH that bypass Portainer
3. **NEVER** commit without running `test_infrastructure.py` first
4. **NEVER** use SSH deployment as primary method
5. **NEVER** ignore or dismiss 4XX HTTP errors as "expected" or "normal"
6. **NEVER** accept authentication failures as acceptable behavior

### ALWAYS Do These:
1. **ALWAYS** use `--registry` flag for deployments when possible
2. **ALWAYS** use `portainer_stack_manager.py` for stack operations
3. **ALWAYS** run health checks after deployments
4. **ALWAYS** verify all stacks show up in `list` command
5. **ALWAYS** run full tests before commits
6. **ALWAYS** prefer registry-based deployment over SSH fallbacks
7. **ALWAYS** investigate and fix 4XX HTTP errors - they indicate real problems
8. **ALWAYS** ensure all services return proper HTTP 200 responses or appropriate redirects

### Pre-Commit Checklist:
```bash
# 1. Test all infrastructure
source venv/bin/activate && python scripts/test_infrastructure.py

# 2. Verify all stacks are Portainer-managed
python scripts/portainer_stack_manager.py list

# 3. Health check all stacks
python scripts/infrastructure_manager.py health-check-all

# 4. Verify all services return proper HTTP responses (NO 4XX errors allowed)
python scripts/quick_service_test.py

# 5. If ANY 4XX errors found, investigate and fix before proceeding
```

### 🔍 4XX Error Investigation Workflow:
When 4XX errors are found:

1. **HTTP 401 (Unauthorized)**:
   - Check authentication configuration
   - Verify credentials and tokens
   - Review middleware configuration

2. **HTTP 403 (Forbidden)**:
   - Check authorization rules
   - Verify user permissions
   - Review access control configuration

3. **HTTP 404 (Not Found)**:
   - Verify service is running and healthy
   - Check routing configuration in Traefik
   - Verify DNS resolution
   - Check container port mappings
   - Review service discovery configuration

## 🔧 Common Operations

### Fix "Stack not in Portainer" Issues:
```bash
# Migrate SSH-deployed stacks to Portainer
python scripts/infrastructure_manager.py migrate-to-portainer
```

### Deploy New Service:
1. Create `infrastructure/<service>/docker-compose.yml`
2. Create `infrastructure/<service>/.env` (if needed)
3. Deploy: `python scripts/portainer_stack_manager.py deploy <service> infrastructure/<service>/docker-compose.yml`
4. Test: `python scripts/portainer_stack_manager.py health <service>`

### Update Existing Service:
1. Modify `infrastructure/<service>/docker-compose.yml`
2. Update: `python scripts/portainer_stack_manager.py update <service> infrastructure/<service>/docker-compose.yml`
3. Test: `python scripts/portainer_stack_manager.py health <service>`

### Troubleshoot Service Issues:
1. Check status: `python scripts/portainer_stack_manager.py status <service>`
2. Health check: `python scripts/portainer_stack_manager.py health <service>`
3. View all stacks: `python scripts/portainer_stack_manager.py list`
4. Full test suite: `python scripts/test_infrastructure.py`

## 📊 Service Endpoints

### Public Services (HTTPS with SSL):
- https://www.markcheli.com - Personal website
- https://flask.markcheli.com - Flask API
- https://jupyter.markcheli.com - JupyterHub
- minecraft.markcheli.com:25565 - Minecraft server

### LAN-Only Services:
- https://portainer-local.ops.markcheli.com - Portainer
- https://traefik-local.ops.markcheli.com - Traefik dashboard
- https://logs-local.ops.markcheli.com - OpenSearch dashboards
- https://www-dev.ops.markcheli.com - Development website
- https://flask-dev.ops.markcheli.com - Development Flask API

### Monitoring Services:
- https://grafana-local.ops.markcheli.com - Grafana dashboards (admin/admin123)
- https://prometheus-local.ops.markcheli.com - Prometheus metrics database
- https://cadvisor-local.ops.markcheli.com - Container resource monitoring

## 🔑 Environment Configuration

Required variables in `.env`:
```bash
PORTAINER_URL=https://portainer-local.ops.markcheli.com
PORTAINER_API_KEY=your_api_key_here
PORTAINER_ENDPOINT_ID=3
SSH_HOST=192.168.1.179
SSH_USER=mcheli

# GitHub Container Registry Authentication (for registry-based deployments)
GITHUB_TOKEN=your_github_token_here          # Preferred for CI/CD
GITHUB_USERNAME=your_github_username         # GitHub username
# OR use personal access token:
GITHUB_PAT=your_personal_access_token        # Alternative to GITHUB_TOKEN
```

## 🔐 GitHub Container Registry Authentication

### Robust Authentication System
The system uses `scripts/github_registry_auth.py` for secure, reliable authentication following GitHub best practices:

#### Authentication Methods (in preference order):
1. **GITHUB_TOKEN** (recommended for CI/CD environments)
2. **Personal Access Token** (`GITHUB_PAT` or `CR_PAT`)
3. **Credentials File** (`~/.github_registry_credentials`)
4. **Interactive Setup** (with guided instructions)

#### Authentication Commands:
```bash
# Test current authentication status
python scripts/github_registry_auth.py test

# Setup/refresh authentication
python scripts/github_registry_auth.py authenticate

# Setup server-side authentication via SSH
python scripts/github_registry_auth.py setup-server

# Force refresh authentication
python scripts/github_registry_auth.py authenticate --force
```

#### Integrated Authentication (via infrastructure_manager.py):
```bash
# Test authentication
python scripts/infrastructure_manager.py test-registry-auth

# Setup server authentication
python scripts/infrastructure_manager.py setup-registry-auth
```

### Authentication Setup Guide

#### Method 1: Environment Variables (Recommended)
```bash
export GITHUB_TOKEN=<your_github_token>
export GITHUB_USERNAME=<your_github_username>
```

#### Method 2: Credentials File
```bash
echo '{"username": "<username>", "token": "<token>"}' > ~/.github_registry_credentials
chmod 600 ~/.github_registry_credentials
```

#### GitHub Token Requirements:
- **Scopes needed**: `write:packages`, `read:packages`
- **Create at**: https://github.com/settings/tokens
- **Token type**: Personal Access Token (classic)

### Security Features:
- ✅ Uses `--password-stdin` for secure token input
- ✅ Automatic credential validation and refresh
- ✅ Multiple authentication fallbacks
- ✅ Server-side authentication setup
- ✅ Clear troubleshooting guidance

## 🌐 DNS Management Workflow

### **CRITICAL LIMITATION**: Squarespace DNS API
Squarespace does not provide a public API for DNS record management. All DNS changes must be made **manually** through the Squarespace dashboard. The scripts provided offer guided assistance and validation only.

### Service Deployment with DNS
When deploying a new service that requires DNS:

1. **Deploy the service/container first**
2. **Request DNS setup**: `python scripts/dns_manager.py setup <service_name>`
3. **Manually add DNS record** in Squarespace dashboard using provided instructions
4. **Wait for propagation**: 5-15 minutes
5. **Verify deployment**: `python scripts/dns_manager.py verify <service_name>`

### DNS Record Types by Service Category
- **Public Services** (internet-accessible): Point to `173.48.98.211`
  - `jupyter.markcheli.com` - JupyterHub
  - `www.markcheli.com` - Personal website
  - `flask.markcheli.com` - Flask API
  - `ops.markcheli.com` - Base domain

- **Local Services** (LAN-only): Point to `192.168.1.179`
  - `traefik-local.ops.markcheli.com` - Traefik dashboard
  - `portainer-local.ops.markcheli.com` - Portainer management
  - `logs-local.ops.markcheli.com` - OpenSearch Dashboards
  - `opensearch-local.ops.markcheli.com` - OpenSearch API

### Manual DNS Steps in Squarespace
1. Login to Squarespace account
2. Go to Settings → Domains
3. Click on "ops.markcheli.com"
4. Click "DNS" in left sidebar
5. Scroll to "Custom Records"
6. Click "Add Record" → "A Record"
7. Enter Host (subdomain) and Points to (IP)
8. Save and wait for propagation

### DNS Troubleshooting Commands
```bash
# Check if DNS record exists
dig jupyter.ops.markcheli.com A +short

# Check DNS propagation from multiple servers
dig @8.8.8.8 jupyter.ops.markcheli.com A +short
dig @1.1.1.1 jupyter.ops.markcheli.com A +short

# Test service connectivity after DNS resolves
curl -I https://jupyter.ops.markcheli.com
```

### SSL Certificate Management
This project uses **manual wildcard SSL certificates** from Let's Encrypt:

- ✅ **Wildcard Coverage**: `*.markcheli.com` and `*.ops.markcheli.com`
- 🔄 **Manual Renewal**: Every 90 days via `scripts/dns_manager.py`
- 📋 **DNS Verification**: Required for certificate renewal

**Certificate Renewal Process:**
1. Run: `python scripts/dns_manager.py renew-ssl`
2. Follow DNS verification prompts for both wildcard domains
3. Update certificates on server
4. Restart Traefik: `python scripts/portainer_stack_manager.py update traefik`

## 📊 System Monitoring with Prometheus/Grafana

### Overview
The monitoring stack provides comprehensive system and container metrics:

**Components:**
- **Prometheus** - Time-series metrics database with 30-day retention
- **Grafana** - Visualization dashboards and alerting
- **cAdvisor** - Container resource metrics collector (by Google)
- **Node Exporter** - Host system metrics collector

**Key Metrics Monitored:**
- CPU usage per container and total system
- Memory usage per container and total system
- Network I/O per container
- Disk I/O and usage
- Container restart counts and health status

### Deployment and Management

```bash
# Deploy monitoring stack
python scripts/portainer_stack_manager.py deploy monitoring infrastructure/monitoring/docker-compose.yml

# Health check monitoring services
python scripts/portainer_stack_manager.py health monitoring

# Update monitoring configuration
python scripts/portainer_stack_manager.py update monitoring infrastructure/monitoring/docker-compose.yml
```

### Access and Configuration

**Grafana Dashboard:**
- URL: https://grafana-local.ops.markcheli.com
- Login: admin / admin123
- Pre-configured Prometheus datasource
- Import dashboard IDs: 193, 1860, 14282 for Docker monitoring

**Prometheus Queries:**
- URL: https://prometheus-local.ops.markcheli.com
- Container CPU: `rate(container_cpu_usage_seconds_total{name!=""}[1m]) / scalar(count(count(node_cpu_seconds_total) by (cpu))) * 100`
- Container Memory: `container_memory_usage_bytes{name!=""} / 1024 / 1024 / 1024`
- System CPU: `100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`

**cAdvisor Interface:**
- URL: https://cadvisor-local.ops.markcheli.com
- Real-time container metrics and drill-down views

### Custom Dashboard Setup

The monitoring stack includes a custom dashboard configuration at:
`infrastructure/monitoring/grafana-dashboard-*.json`

**Key Dashboard Features:**
- Container CPU usage (% of total system capacity)
- Container memory usage (MB and % of total)
- System overview with color-coded thresholds
- Network traffic per container
- Historical data with 30-second refresh

### Troubleshooting

**Common Issues:**
- **Permission errors**: Containers run as root (`user: "0"`) to access volumes
- **>100% CPU readings**: Normal on multi-core systems (shows CPU cores used)
- **404 errors**: Check Traefik routing and container health

**DNS Requirements:**
- grafana-local.ops.markcheli.com → 192.168.1.179
- prometheus-local.ops.markcheli.com → 192.168.1.179
- cadvisor-local.ops.markcheli.com → 192.168.1.179

## 📁 File Structure

```
infrastructure/
├── traefik/docker-compose.yml      # Reverse proxy
├── jupyter/docker-compose.yml      # JupyterHub
├── opensearch/docker-compose.yml   # Logging stack
├── personal-website/docker-compose.yml
├── flask-api/docker-compose.yml
├── minecraft/docker-compose.yml
└── monitoring/docker-compose.yml   # Prometheus/Grafana monitoring

scripts/
├── infrastructure_manager.py       # MASTER controller (with registry support)
├── portainer_stack_manager.py      # UNIFIED Portainer API management
├── registry_builder.py            # Container registry deployment system
├── github_registry_auth.py         # Robust authentication management
├── test_infrastructure.py          # Comprehensive testing
├── dns_manager.py                 # DNS and SSL management
├── quick_service_test.py           # Quick service availability testing
├── ssh_manager.py                 # EMERGENCY troubleshooting only
└── one-time/                      # One-time setup scripts (disk migration, etc.)
```

## 🎯 Success Criteria

Infrastructure is considered healthy when:
1. All 7 stacks show in `portainer_stack_manager.py list` (including monitoring)
2. `infrastructure_manager.py health-check-all` passes
3. `test_infrastructure.py` passes (53+ of 56 tests)
4. **ALL** services return proper HTTP responses (200, or appropriate redirects - NO 4XX errors)
5. Minecraft server responds on port 25565
6. Monitoring services accessible and collecting metrics

### 🚨 HTTP Error Response Guidelines:
- **HTTP 200**: Service is working correctly ✅
- **HTTP 301/302**: Proper redirects (e.g., HTTP → HTTPS) ✅
- **HTTP 401**: MUST be investigated - indicates authentication problems ❌
- **HTTP 403**: MUST be investigated - indicates authorization problems ❌
- **HTTP 404**: MUST be investigated - indicates missing resources or routing issues ❌
- **HTTP 5XX**: MUST be investigated - indicates server errors ❌

**4XX errors are NEVER acceptable and indicate real problems that must be fixed.**

## 🚀 Quick Reference Commands

```bash
# 🎯 PREFERRED: Registry-based deployment (NO SSH)
python scripts/infrastructure_manager.py deploy-all --registry --clean

# Authentication management
python scripts/infrastructure_manager.py test-registry-auth
python scripts/infrastructure_manager.py setup-registry-auth

# Build and push images for registry deployment
python scripts/infrastructure_manager.py build-images
python scripts/infrastructure_manager.py push-images
python scripts/infrastructure_manager.py build-and-push

# Health check
python scripts/infrastructure_manager.py health-check-all

# Individual stack deploy
python scripts/portainer_stack_manager.py deploy minecraft infrastructure/minecraft/docker-compose.yml

# Test everything
python scripts/test_infrastructure.py

# List all stacks
python scripts/portainer_stack_manager.py list

# Registry builder (standalone)
python scripts/registry_builder.py build-and-push personal-website
python scripts/registry_builder.py deploy personal-website
python scripts/github_registry_auth.py test
```

## 🐳 Registry-Based Deployment Architecture

### Overview
The registry-based approach eliminates SSH dependencies by:
1. **Building** images locally using Docker build contexts
2. **Pushing** to GitHub Container Registry (ghcr.io/mcheli/*)
3. **Deploying** via pure Portainer API using registry images

### Stack Types
- **Registry Stacks** (build-based): personal-website, flask-api, jupyter
- **Direct Stacks** (no building): traefik, opensearch, minecraft

### Registry Compose Files
Build-based stacks have two compose files:
- `docker-compose.yml` - Original with build contexts (SSH deployment)
- `docker-compose.registry.yml` - Registry images (Portainer API only)

### Deployment Workflow

#### One-time Setup (on machine with Docker):
```bash
# Setup authentication (multiple methods available)
python scripts/github_registry_auth.py test

# Build all images
python scripts/infrastructure_manager.py build-images

# Push to registry
python scripts/infrastructure_manager.py push-images

# OR combine build and push
python scripts/infrastructure_manager.py build-and-push

# Setup server-side authentication
python scripts/infrastructure_manager.py setup-registry-auth
```

#### Ongoing Deployment (from anywhere):
```bash
# Deploy using registry images (NO SSH required)
python scripts/infrastructure_manager.py deploy-all --registry --clean
```

### Benefits
✅ **Zero SSH dependencies** for deployment
✅ **All stacks managed** through Portainer UI
✅ **Faster deployments** (pre-built images)
✅ **Better security** (no SSH keys required)
✅ **Consistent deployment** method across all stacks

Remember: **Registry-based deployment is the preferred method. SSH is for emergency troubleshooting only.**

## 🚨 Critical Error Handling Guidelines

### HTTP Status Code Standards
Claude Code must adhere to strict HTTP status code standards:

**✅ ACCEPTABLE responses:**
- **200 OK**: Service functioning correctly
- **301/302 Redirect**: Proper redirects (HTTP→HTTPS, etc.)

**❌ UNACCEPTABLE responses (must be investigated and fixed):**
- **401 Unauthorized**: Authentication configuration problems
- **403 Forbidden**: Authorization/permission problems
- **404 Not Found**: Missing resources, broken routing, or container issues
- **500+ Server Errors**: Backend service failures

### Mandatory Investigation Process
When any 4XX/5XX error is encountered:

1. **Do NOT dismiss or ignore the error**
2. **Do NOT claim it's "expected" or "normal"**
3. **IMMEDIATELY investigate root cause**
4. **Check container health and logs**
5. **Verify routing configuration**
6. **Fix the underlying issue**
7. **Re-test to confirm resolution**

### Service-Specific Expectations
- **Public services** (*.markcheli.com): Must return HTTP 200 or proper redirects
- **LAN services** (*.ops.markcheli.com): Must return HTTP 200 or proper redirects
- **Authentication required services**: Should redirect to login, NOT return 404
- **Protected dashboards**: Should prompt for auth, NOT return 401 errors

**Every service must be fully functional. No exceptions.**