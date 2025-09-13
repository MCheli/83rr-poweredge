# 83RR PowerEdge Homelab Infrastructure

A comprehensive Docker-based homelab infrastructure management system with automated deployment tools and monitoring.

## Project Structure

```
├── infrastructure/           # Local copies of stack configurations
│   ├── jupyter/             # JupyterHub data science environment
│   ├── traefik/             # Reverse proxy with SSL termination
│   ├── opensearch/          # OpenSearch logging stack
│   └── personal-website/    # Mark Cheli's personal website (Vue3/NuxtJS + Flask API)
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
```

## Current Infrastructure

### Active Services
- **Traefik** - Reverse proxy with SSL termination (ports 80, 443, 8080, 8443)
- **Personal Website** - Mark Cheli's interactive terminal-style website with Flask API backend
  - **Main Site**: https://www.markcheli.com - Vue3/NuxtJS terminal interface
  - **Flask API**: https://flask.markcheli.com - Python API with weather endpoint
  - **Dev Site**: https://www-dev.ops.markcheli.com - Development environment (LAN-only)
- **JupyterHub** - Multi-user data science environment with collaboration features
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

## Security

- All secrets managed via environment variables
- Virtual environment isolation for Python dependencies
- SSH key-based authentication for server access
- API key authentication for Portainer access
