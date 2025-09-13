# Claude Code Instructions

## Python Environment Setup

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

## Project Structure

- `scripts/deploy.sh` - Main deployment script (Python, despite .sh extension)
- `scripts/` - Utility scripts for server management
- `infrastructure/` - Local copies of docker-compose configurations from Portainer
- `requirements.txt` - Python dependencies
- `.env` - Environment configuration (contains API keys and URLs)
- `venv/` - Local Python virtual environment (do not commit to git)

## Script Management Policy

**IMPORTANT**: When Claude creates utility scripts that successfully interact with the server/APIs:

1. **DO NOT DELETE** successful scripts after use
2. **SAVE** them in the `scripts/` directory with descriptive names
3. **DOCUMENT** them in this file under "Available Scripts"
4. **ADD** usage examples and descriptions

This builds a library of useful tools for future sessions and tasks.

## Available Scripts

### Connectivity Testing
```bash
# Test SSH and Portainer API connectivity
source venv/bin/activate && python scripts/test_connectivity.py
```

### Container Management
```bash
# List all running containers and their status
source venv/bin/activate && python scripts/get_containers.py
```

### Stack Management
```bash
# List all Portainer stacks
source venv/bin/activate && python scripts/list_stacks.py

# Pull all stack configurations from Portainer to local infrastructure/ directory
source venv/bin/activate && python scripts/pull_stack_configs.py

# Deploy updated stack configuration to Portainer (API method)
source venv/bin/activate && python scripts/deploy_stack.py <stack_name> <compose_file_path>

# Deploy updated stack configuration via SSH (copies .env file automatically)
source venv/bin/activate && python scripts/deploy_via_ssh.py <stack_name> <compose_file_path>

# Deploy all services with SSL verification and health checks
source venv/bin/activate && python scripts/deploy_all_services.py
```

### Infrastructure Health Testing
```bash
# MANDATORY: Run before ANY git commit or when verifying system health
source venv/bin/activate && python scripts/test_infrastructure.py

# Comprehensive test suite includes:
# - DNS resolution for all services
# - Docker container health and status
# - OpenSearch cluster health and log ingestion
# - Web service HTTPS connectivity and performance
# - Backup file integrity
# - Git repository status
```

### DNS Management (Squarespace Domains)
```bash
# IMPORTANT: Squarespace does not offer a public DNS API
# These scripts provide guided manual DNS management

# Audit all infrastructure DNS records
source venv/bin/activate && python scripts/infrastructure_dns.py audit

# Setup DNS for a specific service (provides manual instructions)
source venv/bin/activate && python scripts/infrastructure_dns.py setup <service_name>

# Verify deployment after DNS changes
source venv/bin/activate && python scripts/infrastructure_dns.py verify <service_name>

# Generate deployment checklist for service
source venv/bin/activate && python scripts/infrastructure_dns.py checklist <service_name>

# Manual DNS record management
source venv/bin/activate && python scripts/dns_manager.py add <subdomain> [ip]
source venv/bin/activate && python scripts/dns_manager.py check <subdomain>
source venv/bin/activate && python scripts/dns_manager.py wait <subdomain> <expected_ip>
source venv/bin/activate && python scripts/dns_manager.py test <subdomain>
```

### SSL Certificate Management
```bash
# Setup manual wildcard SSL certificates (one-time setup)
source venv/bin/activate && bash scripts/setup_manual_wildcard_ssl.sh

# IMPORTANT: Manual certificate renewal every 90 days
# 1. Run setup script again when certificates are near expiration
# 2. Follow DNS verification prompts for both wildcard domains
# 3. Restart Traefik after certificate renewal: scripts/deploy_via_ssh.py traefik infrastructure/traefik/docker-compose.yml
```

### SSH Session Management
```bash
# CRITICAL: Server limit of 2 concurrent SSH sessions

# All deployment scripts automatically manage SSH sessions:
# - Connection timeouts (30 seconds)
# - Keep-alive settings (10 second intervals)
# - Proper session cleanup after completion

# Never run multiple deployment scripts simultaneously
# Wait for completion before starting next deployment
```

## Environment Variables Required

The following environment variables must be set in `.env`:
- `PORTAINER_URL` - Portainer instance URL
- `PORTAINER_API_KEY` - API key for Portainer authentication
- `SSH_HOST` - Target server hostname
- `SSH_USER` - SSH username
- `PORTAINER_ENDPOINT_ID` - Portainer endpoint ID (default: 3)

### DNS Configuration Variables (for reference):
- `PUBLIC_IP` - Server's public IP address (173.48.98.211)
- `LOCAL_IP` - Server's local network IP (192.168.1.179)
- `DOMAIN` - Base domain name (ops.markcheli.com)

## DNS Management Workflow

### **Important Limitation**: Squarespace DNS API
Squarespace does not provide a public API for DNS record management. All DNS changes must be made manually through the Squarespace dashboard. The scripts provided offer guided assistance and validation.

### **Service Deployment with DNS**
When deploying a new service that requires DNS:

1. **Deploy the service/container**
2. **Request DNS setup**: `python scripts/infrastructure_dns.py setup <service_name>`
3. **Manually add DNS record** in Squarespace dashboard using provided instructions
4. **Wait for propagation**: 5-15 minutes
5. **Verify deployment**: `python scripts/infrastructure_dns.py verify <service_name>`

### **DNS Record Types by Service Category**
- **Public Services** (internet-accessible): Point to `173.48.98.211`
  - `jupyter.markcheli.com` - JupyterHub (moved from ops subdomain)
  - `www.markcheli.com` - Personal website
  - `flask.markcheli.com` - Flask API
  - `ops.markcheli.com` - Base domain (whoami)

- **Local Services** (LAN-only): Point to `192.168.1.179`
  - `traefik-local.ops.markcheli.com` - Traefik dashboard
  - `portainer-local.ops.markcheli.com` - Portainer management
  - `logs-local.ops.markcheli.com` - OpenSearch Dashboards
  - `opensearch-local.ops.markcheli.com` - OpenSearch API

### **Manual DNS Steps in Squarespace**
1. Login to Squarespace account
2. Go to Settings → Domains
3. Click on "ops.markcheli.com"
4. Click "DNS" in left sidebar
5. Scroll to "Custom Records"
6. Click "Add Record" → "A Record"
7. Enter Host (subdomain) and Points to (IP)
8. Save and wait for propagation

### **DNS Troubleshooting Commands**
```bash
# Check if DNS record exists
dig jupyter.ops.markcheli.com A +short

# Check DNS propagation from multiple servers
dig @8.8.8.8 jupyter.ops.markcheli.com A +short
dig @1.1.1.1 jupyter.ops.markcheli.com A +short

# Test service connectivity after DNS resolves
curl -I https://jupyter.ops.markcheli.com
```

## Git Usage and Security

### Security Requirements
**CRITICAL**: Never commit secrets or sensitive information to git.

- All environment files (`.env`, `stack.env`) are in `.gitignore`
- API keys, passwords, and tokens must only exist in environment files
- Review all changes before committing to ensure no secrets are included
- Use `git diff --cached` to review staged changes before committing

### Git Workflow with Claude

**Pre-commit Security Check:**
```bash
# Always check what will be committed
git status
git diff --cached

# Scan for potential secrets (if tools available)
rg -i "api[_-]?key|secret|password|token" --type-not=log .
```

**Safe Commit Process:**
```bash
# Stage files (Claude will do this automatically)
git add .

# Claude will create commits with this format:
# - Descriptive commit message explaining changes
# - Includes file/function references where appropriate
# - Ends with Claude signature for traceability
```

**Commit Message Format:**
Claude follows this commit message format:
- Clear, descriptive summary (50 chars or less)
- Detailed explanation of changes and reasoning
- References to specific files/functions modified
- Signed with Claude attribution

### Recovery and Rollback

**View Recent Changes:**
```bash
# View recent commits
git log --oneline -10

# See changes in specific commit
git show <commit-hash>

# Compare with previous version
git diff HEAD~1
```

**Rollback Changes:**
```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Revert specific files
git checkout -- <file-path>

# Create revert commit
git revert <commit-hash>
```

### Ignore Patterns

The `.gitignore` includes these security patterns:
- Environment files: `.env`, `stack.env`, `*.env.*`
- Secrets directories: `secrets/`, `**/secrets/`
- Certificates: `*.key`, `*.pem`, `*.p12`, `*.keystore`
- Virtual environments: `venv/`
- Logs and backups: `logs/`, `backups/`, `*.log`