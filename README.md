# 83RR PowerEdge Homelab Infrastructure

A comprehensive Docker-based homelab infrastructure management system with automated deployment tools and monitoring.

## Project Structure

```
├── infrastructure/           # Local copies of stack configurations
│   ├── jupyter/             # JupyterHub data science environment
│   ├── traefik/             # Reverse proxy with SSL termination
│   ├── opensearch/          # OpenSearch logging stack
│   ├── personal-website/    # Mark Cheli's personal website (Vue3/NuxtJS + Flask API)
│   ├── flask-api/           # Separate Flask API backend service
│   └── minecraft/           # Minecraft Java Edition server
├── scripts/                 # Management and utility scripts
├── .env                     # Environment configuration (secrets)
├── requirements.txt         # Python dependencies
└── venv/                    # Python virtual environment
```

## Quick Start

### 1. Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Available Management Scripts

```bash
# CRITICAL: Comprehensive infrastructure health test (run before commits)
python scripts/test_infrastructure.py

# Test connectivity to server and Portainer API
python scripts/test_connectivity.py

# List all running containers and their status
python scripts/get_containers.py

# List all Portainer stacks
python scripts/list_stacks.py

# Pull all stack configurations from Portainer
python scripts/pull_stack_configs.py

# Deploy individual stack (FIXED: Single SSH session)
python scripts/deploy_via_ssh.py <stack_name> <compose_file_path>

# Deploy all services (Uses single SSH session per stack)
python scripts/deploy_all_services.py
```

## Current Infrastructure

### Active Services
- **Traefik** - Reverse proxy with SSL termination (ports 80, 443, 25565, 8080, 8443)
- **Personal Website** - Mark Cheli's interactive terminal-style website with Flask API backend
  - **Main Site**: https://www.markcheli.com - Vue3/NuxtJS terminal interface
  - **Flask API**: https://flask.markcheli.com - Python API with weather endpoint
  - **Dev Site**: https://www-dev.ops.markcheli.com - Development environment (LAN-only)
- **JupyterHub** - https://jupyter.markcheli.com - Multi-user data science environment with collaboration features
- **Minecraft Server** - https://minecraft.markcheli.com - Java Edition server (Game: minecraft.markcheli.com:25565)
- **OpenSearch Stack** - Log aggregation, search and visualization (OpenSearch + Dashboards + Logstash + Filebeat)
- **Portainer** - Container management interface
- **Home Assistant** - https://home.markcheli.com - Smart home automation

### Server Details
- **Host**: 83rr-poweredge
- **User**: mcheli
- **Portainer**: https://portainer-local.ops.markcheli.com
- **Management**: 4 active stacks, 13 healthy containers

## Configuration Management

All infrastructure configurations are pulled from the live Portainer instance and stored locally in the `infrastructure/` directory. Each stack includes:

- `docker-compose.yml` - Current stack configuration
- `stack-metadata.json` - Stack details and timestamps
- Additional configuration files and documentation

## Environment Variables

Required variables in `.env`:
- `PORTAINER_URL` - Portainer instance URL
- `PORTAINER_API_KEY` - API authentication key
- `SSH_HOST` - Server hostname
- `SSH_USER` - SSH username
- `PORTAINER_ENDPOINT_ID` - Endpoint identifier

## Development

See `CLAUDE.md` for detailed development instructions and script management policies.

### SSH Connection Management (FIXED)

**Critical Issue Resolved**: The deployment scripts were creating up to 8 simultaneous SSH connections, exceeding the server's MaxSessions=2 limit. This has been completely fixed:

- ✅ **Single SSH Session**: All deployments now use exactly 1 SSH connection
- ✅ **Tar-based Transfer**: Files packaged locally and transferred via stdin
- ✅ **Atomic Operations**: Transfer, extraction, and deployment in one session
- ✅ **No More Connection Refused**: Deployment reliability dramatically improved

See `docs/SSH_CONNECTION_FIX.md` for complete technical details.

## SSL Certificate Management

This project uses **manual wildcard SSL certificates** from Let's Encrypt to avoid rate limiting issues:

- **Wildcard Coverage**: `*.markcheli.com` and `*.ops.markcheli.com`
- **Manual DNS Verification**: Certificates obtained via `certbot` with manual DNS-01 challenges
- **Traefik Integration**: Certificates loaded via file provider for automatic SSL termination
- **Renewal**: Manual process every 90 days (see `scripts/setup_manual_wildcard_ssl.sh`)

### SSH Session Management

**CRITICAL**: The server has a limit of **2 concurrent SSH sessions**. All deployment scripts have been **completely rewritten** to:
- **Single SSH Session**: `deploy_via_ssh.py` now uses only 1 SSH connection for entire deployment
- **Tar-based Transfer**: Files are packaged locally and transferred via stdin to avoid multiple SCP connections
- **Atomic Operations**: File transfer, extraction, and deployment happen in one SSH session
- **Connection Limits Respected**: No more "Connection refused" errors due to MaxSessions limit
- **Improved Reliability**: Proper connection timeouts and keep-alive settings

### Troubleshooting

**Traefik Routing Issues**: If services are healthy but not accessible via HTTPS:
- Ensure `traefik.docker.network=traefik_default` label is present on all services
- Verify middleware references use `@docker` suffix (e.g., `secure-headers@docker`)
- Check that services are connected to the `traefik_default` network
- Use `scripts/test_service_availability.py` to verify all endpoints

## Security

- All secrets managed via environment variables
- Virtual environment isolation for Python dependencies
- SSH key-based authentication for server access
- API key authentication for Portainer access
- Manual wildcard SSL certificates for secure connections
