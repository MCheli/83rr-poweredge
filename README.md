# 83RR PowerEdge Homelab Infrastructure

A comprehensive Docker-based homelab infrastructure running on Ubuntu Server with NGINX reverse proxy, Cloudflare SSL, and comprehensive monitoring.

## Project Structure

```
├── infrastructure/           # Service configurations
│   ├── nginx/               # NGINX reverse proxy
│   ├── jupyter/             # JupyterLab data science environment
│   ├── opensearch/          # OpenSearch logging stack
│   ├── personal-website/    # Nuxt.js personal website
│   ├── flask-api/           # Flask API backend service
│   ├── minecraft/           # Minecraft server
│   └── monitoring/          # Prometheus/Grafana monitoring
├── scripts/                 # Management and utility scripts
├── docker-compose.yml       # Base service definitions
├── docker-compose.prod.yml  # Production overrides
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

# Deploy all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check service status
docker ps

# View logs
docker compose logs -f
```

### 3. Verify Deployment
```bash
# Test NGINX health
curl http://localhost/health

# Test service endpoints
curl -I https://www.markcheli.com
curl https://flask.markcheli.com/health
```

## Current Infrastructure

### Active Services (10/10 - 100% Operational)

**Public Services:**
- **Personal Website** - https://www.markcheli.com, https://markcheli.com
  - Nuxt.js terminal-style interactive website
  - Communicates with Flask API backend
- **Flask API** - https://flask.markcheli.com
  - Python API with weather endpoint and profile data
  - Health check: `/health`
- **JupyterLab** - https://jupyter.markcheli.com
  - Standalone data science environment
  - Real-time collaboration, SQL integration, AI assistance
- **Minecraft Server** - minecraft.markcheli.com:25565
  - Java Edition server (port 25565)

**LAN-Only Services** (*.ops.markcheli.com):
- **Grafana** - https://grafana-local.ops.markcheli.com
  - Monitoring dashboards (login: admin/admin123)
- **Prometheus** - https://prometheus-local.ops.markcheli.com
  - Metrics database with 30-day retention
- **cAdvisor** - https://cadvisor-local.ops.markcheli.com
  - Container resource metrics
- **OpenSearch Dashboards** - https://logs-local.ops.markcheli.com
  - Log visualization and search
- **Flask API Dev** - https://flask-dev.ops.markcheli.com
  - Development API environment

**Infrastructure:**
- **NGINX** - Reverse proxy with SSL termination
  - Ports: 80 (HTTP), 443 (HTTPS), 25565 (Minecraft)
- **OpenSearch** - Log aggregation and search engine

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

### Common Commands

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
docker compose exec nginx nginx -t

# Reload configuration (no downtime)
docker compose exec nginx nginx -s reload

# View NGINX logs
docker compose logs nginx
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

### Service Health
- **Grafana Dashboard**: https://grafana-local.ops.markcheli.com
  - Pre-configured Prometheus datasource
  - Container metrics and system monitoring
- **Prometheus**: https://prometheus-local.ops.markcheli.com
  - 30-day metric retention
  - Comprehensive service monitoring
- **cAdvisor**: https://cadvisor-local.ops.markcheli.com
  - Real-time container resource metrics

### Logging
- **OpenSearch**: Centralized log storage
- **OpenSearch Dashboards**: https://logs-local.ops.markcheli.com
  - Log visualization and search
  - Daily indices: `logs-homelab-YYYY.MM.dd`

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

- **CLAUDE.md** - Comprehensive infrastructure management guide for Claude Code
- **DEPLOYMENT_STATUS.md** - Current deployment status and service health
- **CLOUDFLARE_SSL_SETUP_GUIDE.md** - SSL certificate setup documentation
- **DOCUMENTATION_REVIEW_REPORT.md** - Documentation audit and update tracking

## Support & Maintenance

- **Health Checks**: All services include Docker health checks
- **Auto-Restart**: Services restart automatically on failure
- **Log Rotation**: Configured for all services
- **Certificate Renewal**: Automatic for Let's Encrypt certificates

---

Built with ❤️ by Mark Cheli | Powered by Docker, NGINX, and Cloudflare
