# 83RR PowerEdge Homelab Infrastructure

A comprehensive Docker-based homelab infrastructure running on Ubuntu Server with NGINX reverse proxy, Cloudflare SSL, and comprehensive monitoring.

## Project Structure

```
├── infrastructure/           # Service configurations
│   ├── nginx/               # NGINX reverse proxy
│   ├── jupyter/             # JupyterHub data science environment
│   ├── opensearch/          # OpenSearch logging stack
│   ├── personal-website/    # Nuxt.js personal website
│   ├── flask-api/           # Flask API backend service
│   ├── minecraft/           # Minecraft server
│   ├── plex/                # Plex Media Server
│   ├── seafile/             # Seafile file sync service
│   ├── monitoring/          # Prometheus/Grafana monitoring
│   └── fluent-bit/          # Log shipper configuration
├── scripts/                 # Management and utility scripts
├── docker-compose.yml       # Base service definitions
├── docker-compose.prod.yml  # Production overrides
├── Makefile                 # Common operations (make help)
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

### 2. Deploy Infrastructure
```bash
# Navigate to project directory
cd ~/83rr-poweredge

# Deploy all services (using Makefile)
make up

# Or use docker compose directly
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check service status
make status

# View logs
make logs
```

### 3. Verify Deployment
```bash
# Run health checks on all services
make health

# Or test manually
curl http://localhost/health
curl -I https://www.markcheli.com
curl https://flask.markcheli.com/health
```

## Current Infrastructure

### Active Services

**Public Services:**
- **Personal Website** - https://www.markcheli.com, https://markcheli.com
  - Nuxt.js terminal-style interactive website
  - Communicates with Flask API backend
- **Flask API** - https://flask.markcheli.com
  - Python API with weather endpoint and profile data
  - Health check: `/health`
- **JupyterHub** - https://jupyter.markcheli.com
  - Multi-user data science environment
  - Real-time collaboration, SQL integration, AI assistance
- **Plex Media Server** - https://plex.markcheli.com
  - Media streaming for movies, TV shows, and music
  - Personal media library management
- **Seafile** - https://seafile.markcheli.com
  - Self-hosted file sync and share (Dropbox alternative)
  - File storage, sync, and collaboration
- **Minecraft Server** - minecraft.markcheli.com:25565
  - Java Edition server (port 25565)

**LAN-Only Services** (*.ops.markcheli.com):
- **Grafana** - https://grafana-local.ops.markcheli.com
  - Monitoring dashboards (login: admin/admin123)
  - 5 provisioned dashboards (System, Infrastructure, Docker, NGINX, Containers)
- **Prometheus** - https://prometheus-local.ops.markcheli.com
  - Metrics database with 30-day retention
- **cAdvisor** - https://cadvisor-local.ops.markcheli.com
  - Container resource metrics
- **OpenSearch Dashboards** - https://logs-local.ops.markcheli.com
  - Log visualization and search
- **Flask API Dev** - https://flask-dev.ops.markcheli.com
  - Development API environment

**Infrastructure Services:**
- **NGINX** - Reverse proxy with SSL termination
  - Ports: 80 (HTTP), 443 (HTTPS), 25565 (Minecraft)
- **OpenSearch** - Log aggregation and search engine
- **Fluent Bit** - Log shipper (Docker logs → OpenSearch)
- **Node Exporter** - Host system metrics (CPU, memory, disk)
- **NGINX Exporter** - NGINX metrics for Prometheus
- **Seafile DB** - MariaDB database backend for Seafile
- **Seafile Memcached** - Cache server for Seafile performance

### Server Details
- **Host**: 83rr-poweredge
- **OS**: Ubuntu Server 24.04.3 LTS
- **User**: mcheli
- **Local IP**: 192.168.1.179
- **Public IP**: 173.48.98.211
- **Management**: Docker Compose (native)

## Architecture

### Reverse Proxy
- **NGINX** with Cloudflare Origin Certificates and Let's Encrypt
- Configuration: `infrastructure/nginx/conf.d/production.conf`
- SSL Certificates:
  - Public services: Cloudflare Origin Certificates (15-year validity)
  - LAN services: Let's Encrypt wildcard (90-day, auto-renewal)

### SSL/TLS Configuration
- **Public Services** (*.markcheli.com):
  - Cloudflare Origin Certificates (valid until 2040)
  - Cloudflare SSL Mode: Full (Strict)
  - Automatic HTTPS redirects
- **LAN Services** (*.ops.markcheli.com):
  - Let's Encrypt wildcard certificates
  - Auto-renewal via cron (daily at 3:00 AM)
  - Cloudflare DNS-01 challenge

### Deployment Method
- **Native Docker Compose** - All services managed via Docker Compose CLI
- **No SSH Required** - Claude runs directly on server
- **Environment-Aware** - Base config + production overrides
- **Local Builds** - Services build from Dockerfiles on server

## Service Management

### Makefile Commands (Recommended)

```bash
# View all available commands
make help

# Start all services (production)
make up

# Stop all services
make down

# Restart all or specific service
make restart
make restart s=nginx

# Build services
make build
make build s=personal-website

# View logs
make logs
make logs s=grafana

# Check status and health
make status
make health
```

### Direct Docker Compose Commands

```bash
# Start all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Stop all services
docker compose down

# Restart a specific service
docker compose restart <service_name>

# Rebuild and restart a service
docker compose up -d --build <service_name>

# View logs
docker compose logs -f <service_name>

# Check service status
docker ps
docker compose ps
```

### NGINX Management

```bash
# Test configuration
make nginx-test

# Reload configuration (no downtime)
make nginx-reload

# View NGINX logs
make logs s=nginx
```

### SSL Certificate Renewal

**Cloudflare Certificates** (public services):
- No renewal required until 2040

**Let's Encrypt Certificates** (LAN services):
- Auto-renewal: Daily cron job at 3:00 AM
- Manual renewal: `bash scripts/renew-letsencrypt-certs.sh`
- Check renewal logs: `cat ~/letsencrypt/logs/renewal.log`

## Configuration Management

All service configurations are managed in the repository:

- `docker-compose.yml` - Base service definitions
- `docker-compose.prod.yml` - Production overrides
- `infrastructure/*/` - Service-specific configurations
- `.env` - Environment variables and secrets

### Adding a New Service

1. Edit `docker-compose.yml` to add service definition
2. Create service configuration in `infrastructure/<service>/`
3. Add NGINX server block to `infrastructure/nginx/conf.d/production.conf`
4. Deploy: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d <service>`
5. Test endpoint and verify health
6. Commit changes to git

## Environment Variables

Required variables in `.env`:
```bash
# Cloudflare (for Let's Encrypt DNS-01 challenge)
CLOUDFLARE_API_TOKEN=your_api_token_here

# Infrastructure
INFRASTRUCTURE_ENV=production

# Optional: API keys for services
OPENWEATHER_API_KEY=your_openweather_key
```

## Monitoring & Health Checks

### Metrics Stack
- **Grafana Dashboard**: https://grafana-local.ops.markcheli.com
  - Pre-configured Prometheus datasource
  - 5 provisioned dashboards: Infrastructure Overview, System, Docker Services, Containers, NGINX
  - Login: admin/admin123
- **Prometheus**: https://prometheus-local.ops.markcheli.com
  - 30-day metric retention
  - Scrapes: cAdvisor, Node Exporter, NGINX Exporter
- **cAdvisor**: https://cadvisor-local.ops.markcheli.com
  - Real-time container resource metrics
- **Node Exporter**: Host system metrics (CPU, memory, disk, network)
- **NGINX Exporter**: NGINX connections and request metrics

### Logging Stack
- **Fluent Bit**: Log shipper collecting from all containers
  - Ships to OpenSearch with daily index rotation
- **OpenSearch**: Centralized log storage and search
- **OpenSearch Dashboards**: https://logs-local.ops.markcheli.com
  - Log visualization and search
  - Daily indices: `logs-homelab-YYYY.MM.DD`

## Security

- **SSL Everywhere**: All services use HTTPS
- **LAN Restrictions**: Admin interfaces restricted to 192.168.1.0/24
- **Cloudflare Protection**: Public services proxied through Cloudflare
- **Container Security**: Non-root users, isolated networks
- **Automatic Updates**: Security patches via Docker image updates

## Development

See `CLAUDE.md` for detailed development instructions and infrastructure management policies.

### Python Virtual Environment

Always use the virtual environment for Python scripts:
```bash
source venv/bin/activate
python scripts/<script_name>.py
```

### Git Workflow

```bash
# Make changes to configuration
# Test deployment
docker compose config
docker compose up -d

# Commit changes
git add .
git commit -m "feat: description of change"
git push
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker compose logs <service_name>

# Check Docker status
systemctl status docker

# Verify configuration
docker compose config

# Check resources
df -h
free -h
```

### NGINX Routing Issues
```bash
# Test configuration
docker compose exec nginx nginx -t

# Check routing logs
docker compose logs nginx | grep <service>

# Reload configuration
docker compose exec nginx nginx -s reload
```

### SSL Certificate Issues

**Public Services:**
```bash
# Verify certificates in place
ls -la infrastructure/nginx/certs/wildcard-markcheli.*

# Check Cloudflare dashboard SSL mode (should be "Full (Strict)")
```

**LAN Services:**
```bash
# Check renewal logs
cat ~/letsencrypt/logs/renewal.log

# Test manual renewal
bash scripts/renew-letsencrypt-certs.sh

# Verify certificates
ls -la infrastructure/nginx/certs/letsencrypt-ops-markcheli.*
```

### Network Issues
```bash
# Check Docker networks
docker network ls
docker network inspect infrastructure

# Test connectivity between containers
docker exec <container1> ping <container2>
```

## Documentation

### Project Documentation
- **CLAUDE.md** - Comprehensive infrastructure management guide for Claude Code
- **docs/DEPLOYMENT_STATUS.md** - Current deployment status and service health
- **Makefile** - Run `make help` for all available commands

### Infrastructure Documentation
- **infrastructure/nginx/README.md** - NGINX reverse proxy configuration
- **infrastructure/monitoring/README.md** - Prometheus/Grafana monitoring setup
- **infrastructure/fluent-bit/README.md** - Fluent Bit log shipping configuration
- **scripts/README.md** - Python script documentation

## Support & Maintenance

- **Health Checks**: All services include Docker health checks
- **Auto-Restart**: Services restart automatically on failure
- **Log Rotation**: Configured for all services
- **Certificate Renewal**: Automatic for Let's Encrypt certificates

---

Built with ❤️ by Mark Cheli | Powered by Docker, NGINX, and Cloudflare
