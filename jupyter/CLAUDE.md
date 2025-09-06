# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains Docker-based configuration for a personal JupyterHub server that replicates "batteries included" environments like DataLore or DeepNote. The goal is to create a production-ready docker-compose.yaml for homelab deployment with real-time collaboration, SQL integration, and comprehensive data analysis tools.

## Key Architecture Components

### Multi-Service Stack
- **Configurable HTTP Proxy (CHP)**: Load balancer with Traefik integration
- **JupyterHub**: Central hub with PostgreSQL backend for user management
- **DockerSpawner**: Isolates each user in their own container
- **PostgreSQL**: Persistent storage for hub state and user data

### Reference Implementation
- `original-docker-compose.yaml`: Working JupyterHub setup (DO NOT MODIFY)
- Uses `jupyter/datascience-notebook:python-3.11` as base image
- Runtime installation of collaboration packages via DockerSpawner command override

## Documentation Management

**Critical Documentation Files:**
- `requirements.md`: Comprehensive feature requirements and current status
- `README.md`: User-facing documentation with deployment and usage instructions

**Documentation Update Requirements:**
- Always keep `requirements.md` synchronized with any changes to project scope or implementation decisions
- **MUST update `README.md` whenever changes would affect user instructions** in any of these sections:
  - Docker deployment steps
  - Environment configuration 
  - JupyterHub setup process
  - Feature usage guides
  - Authentication methods
  - Troubleshooting procedures
  - Security considerations

## Essential Features Target

**Core Capabilities:**
- Real-time collaborative editing with `jupyter-collaboration` and `ypy-websocket`
- SQL blocks via `jupyterlab-sql-editor` and `jupysql` with database connectivity
- Pre-installed data science stack (pandas, plotly, scikit-learn, etc.)
- Enhanced DataFrame support with rich previews and statistics
- AI assistance integration with Claude and ChatGPT via `jupyter-ai` and API clients

## Development Commands

### Docker Operations with Portainer

**Building the Custom Image:**
Since you're using Portainer to deploy, you need to build the custom single-user image on your server first:

1. SSH to your server and navigate to the project directory
2. Build the custom image:
   ```bash
   docker build -t personal-jupyter-singleuser:latest .
   ```
3. Verify the image was created:
   ```bash
   docker images | grep personal-jupyter-singleuser
   ```

**Deploying via Portainer:**
1. Upload the `docker-compose.yaml` to Portainer
2. Deploy the stack - it will now use `personal-jupyter-singleuser:latest`

**Alternative - Local Docker Operations (if not using Portainer):**
```bash
# Build custom single-user image
./build.sh

# Or manually:
docker-compose --profile build build singleuser
docker-compose --profile build build --no-cache singleuser  # Force rebuild

# Deploy the stack
docker-compose up -d
docker-compose logs -f jupyterhub
```

### Environment Setup & Security
**CRITICAL: Never commit secrets to version control.**

Use `example-stack.env` as a template to create your own `stack.env` file:
- `CONFIGPROXY_AUTH_TOKEN`: Proxy authentication (generate with `openssl rand -hex 32`)
- `JUPYTER_PASSWORD`: Dummy auth password  
- `JUPYTER_ADMIN_USER`: Admin username
- `POSTGRES_PASSWORD`: Database password (generate with `openssl rand -base64 32`)
- `JUPYTER_DOMAIN`: External domain for Traefik
- `TZ`: Timezone setting
- `OPENAI_API_KEY`: OpenAI API key for ChatGPT integration (optional)
- `ANTHROPIC_API_KEY`: Anthropic API key for Claude integration (optional)

**Security Requirements:**
- Always use `example-stack.env` as template, never put secrets in docker-compose files
- Keep `example-stack.env` updated when new environment variables are added
- Generate strong, unique secrets for each deployment
- Use restrictive file permissions (600) on your `stack.env` file

## Implementation Patterns

### Package Installation Strategy
**Pre-built Docker image approach (Best Practice):**
- Custom `Dockerfile` based on `jupyter/datascience-notebook:python-3.11`
- All packages and extensions pre-installed during image build
- Fast, reliable container startup with no runtime installation
- Build with `./build.sh` or `docker-compose --profile build build singleuser`

**Previous approach (deprecated):** Runtime installation via DockerSpawner was unreliable and slow.

**AI Integration Packages:**
- `jupyter-ai jupyterlab-ai`: Core Jupyter AI extension
- `openai anthropic`: Direct API clients for AI services
- `langchain langchain-openai langchain-anthropic`: Advanced AI workflows

### User Persistence
- Individual volumes per user: `jupyterhub-user-{username}`
- Mounted at `/home/jovyan` in containers
- Hub data persisted in `jupyterhub_data` volume

### Network Architecture
- Internal `jupyterhub-net` bridge network for service communication
- External `traefik_default` network for reverse proxy integration
- CHP routes traffic to individual user containers