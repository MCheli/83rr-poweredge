# Homelab Infrastructure Context

## System Architecture

### Server Details
- **OS**: Ubuntu Server 24.04.3 LTS
- **Hostname**: 83rr-poweredge
- **Local IP**: 192.168.1.179
- **Public IP**: 173.48.98.211
- **User**: mcheli
- **Docker**: Latest with Docker Compose
- **Management**: Native Docker Compose (no web UI)

### Network Setup
- **Primary Domain**: markcheli.com
- **Public Services**: *.markcheli.com (Cloudflare Origin Certificates)
- **LAN Services**: *.ops.markcheli.com (Let's Encrypt DNS-01)
- **DNS Management**: Cloudflare
- **SSL Public**: Cloudflare Origin Certificates (15-year validity, expires 2040)
- **SSL Local**: Let's Encrypt wildcard (90-day validity, auto-renewal via cron)

## Current Services Stack

### 1. NGINX (Reverse Proxy)
- **Version**: Latest
- **Container Name**: nginx
- **Ports**: 80 (HTTP), 443 (HTTPS), 25565 (Minecraft passthrough)
- **Config**: `/home/mcheli/83rr-poweredge/infrastructure/nginx/conf.d/production.conf`
- **Certificates**:
  - `/etc/nginx/certs/wildcard-markcheli.{crt,key}` (Cloudflare Origin)
  - `/etc/nginx/certs/letsencrypt-ops-markcheli.{crt,key}` (Let's Encrypt)
- **Networks**: infrastructure

### 2. Flask API (Backend Service)
- **URL**: https://flask.markcheli.com (public), https://flask-dev.ops.markcheli.com (LAN)
- **Container Name**: flask-api
- **Port**: 5000
- **Health Endpoint**: `/health`
- **Networks**: infrastructure
- **SSL**: Cloudflare Origin Certificate (public), Let's Encrypt (LAN)

### 3. Personal Website (Nuxt.js Frontend)
- **URL**: https://www.markcheli.com, https://markcheli.com
- **Container Name**: personal-website
- **Port**: 3000
- **Status**: ✅ RUNNING
- **Networks**: infrastructure

### 4. JupyterLab (Data Science Environment)
- **URL**: https://jupyter.markcheli.com
- **Container Name**: jupyter
- **Port**: 8888
- **Mode**: Standalone JupyterLab (not JupyterHub)
- **Auth**: Token-less (open access via domain)
- **Volume**: jupyter_data_local:/home/jovyan/work
- **Networks**: infrastructure
- **SSL**: Cloudflare Origin Certificate

### 5. OpenSearch Logging Stack
- **Components**:
  - OpenSearch (opensearch) - Search and analytics engine
  - OpenSearch Dashboards (opensearch-dashboards) - Web interface
- **OpenSearch Dashboards**: https://logs-local.ops.markcheli.com (LAN-only)
- **Security**: Disabled for simplicity
- **Networks**: infrastructure
- **SSL**: Let's Encrypt

### 6. Monitoring Stack
- **Grafana**: https://grafana-local.ops.markcheli.com (LAN-only)
  - Container: grafana
  - Port: 3000
  - Login: admin/admin123
  - Version: 12.3.1
- **Prometheus**: https://prometheus-local.ops.markcheli.com (LAN-only)
  - Container: prometheus
  - Port: 9090
  - Retention: 30 days
- **cAdvisor**: https://cadvisor-local.ops.markcheli.com (LAN-only)
  - Container: cadvisor
  - Port: 8080
  - Purpose: Container metrics collection
- **Networks**: infrastructure
- **SSL**: Let's Encrypt

### 7. Minecraft Server
- **Game Server**: minecraft.markcheli.com:25565
- **Container Name**: minecraft
- **Ports**: 25565 (TCP)
- **Volume**: minecraft_data
- **Networks**: infrastructure

## Docker Networks
- **infrastructure**: Bridge network for all services (created by docker-compose.yml)

## Important Paths

### On Server (83rr-poweredge)
```
/home/mcheli/83rr-poweredge/          # Main project directory
├── docker-compose.yml                 # Base service definitions
├── docker-compose.prod.yml            # Production overrides
├── infrastructure/
│   ├── nginx/
│   │   ├── conf.d/production.conf    # NGINX routing configuration
│   │   └── certs/                    # SSL certificates
│   ├── flask-api/                    # Flask API service
│   ├── personal-website/             # Nuxt.js frontend
│   ├── jupyter/                      # JupyterLab environment
│   ├── opensearch/                   # Logging stack
│   └── monitoring/                   # Prometheus/Grafana configs
├── scripts/                          # Management scripts
└── .env                              # Environment variables

/home/mcheli/letsencrypt/             # Let's Encrypt certificates
├── config/live/ops.markcheli.com/    # Local services certificates
├── work/                             # certbot working directory
└── logs/                             # certbot logs

/data/docker/volumes/                  # Docker volumes
├── 83rr-poweredge_grafana_data/
├── 83rr-poweredge_prometheus_data/
├── 83rr-poweredge_opensearch_data/
├── 83rr-poweredge_minecraft_data/
└── 83rr-poweredge_jupyter_data_local/
```

## Deployment Method
- **Primary**: Native Docker Compose on server
- **Commands**: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
- **No SSH Required**: Claude runs directly on server
- **No Portainer**: All management via Docker Compose CLI
- **No Registry**: Services build locally from Dockerfiles

## Security Considerations
1. **Public Services**: Protected by Cloudflare proxy and Origin Certificates
2. **LAN Services**: Protected by IP-based access control in NGINX
3. **SSL**: All services use HTTPS (Cloudflare or Let's Encrypt)
4. **IP Allowlist**: Local services restricted to 192.168.1.0/24
5. **HTTP→HTTPS**: Automatic redirect for all services

## Common Tasks

### Deploying All Services
```bash
cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Deploying Individual Service
```bash
cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d <service_name>
```

### Checking Service Health
```bash
docker ps
docker compose logs -f <service_name>
```

### Updating Existing Service
1. Edit docker-compose.yml or service configuration
2. Rebuild and deploy: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build <service_name>`
3. Check logs: `docker compose logs -f <service_name>`
4. Verify health: Test service endpoints

### Viewing Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f <service_name>

# Last 100 lines
docker compose logs --tail 100 <service_name>
```

## SSL Certificate Management

### Cloudflare Origin Certificates (Public Services)
- **Domains**: *.markcheli.com, markcheli.com
- **Validity**: 15 years (expires 2040-12-29)
- **Location**: `~/83rr-poweredge/infrastructure/nginx/certs/wildcard-markcheli.{crt,key}`
- **Renewal**: Not required until 2040
- **SSL Mode**: Full (Strict) ✅ ENABLED

### Let's Encrypt Certificates (LAN Services)
- **Domains**: *.ops.markcheli.com
- **Validity**: 90 days (auto-renewal via cron)
- **Location**: `~/83rr-poweredge/infrastructure/nginx/certs/letsencrypt-ops-markcheli.{crt,key}`
- **Source**: `~/letsencrypt/config/live/ops.markcheli.com/`
- **Renewal**: Automatic via cron job (daily at 3:00 AM)
- **Renewal Script**: `~/83rr-poweredge/scripts/renew-letsencrypt-certs.sh`
- **Method**: Cloudflare DNS-01 challenge

## Known Issues & Status

### Operational Services (10/10)
1. ✅ NGINX - Reverse proxy
2. ✅ Flask API - Backend service
3. ✅ Personal Website - Nuxt.js frontend
4. ✅ JupyterLab - Data science environment
5. ✅ OpenSearch - Log storage
6. ✅ OpenSearch Dashboards - Log visualization
7. ✅ Grafana - Monitoring dashboards
8. ✅ Prometheus - Metrics database
9. ✅ cAdvisor - Container metrics
10. ✅ Minecraft - Game server

### Current Status
- **Infrastructure**: ✅ 100% operational (all 10 services running)
- **SSL Configuration**: ✅ Cloudflare Full (Strict) mode enabled
- **Certificates**: ✅ All certificates valid and auto-renewing

## Emergency Procedures

### Service Down
1. Check logs: `docker compose logs <service_name>`
2. Restart: `docker compose restart <service_name>`
3. Full restart: `docker compose down && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

### NGINX Not Routing
1. Check configuration: `docker compose exec nginx nginx -t`
2. Check logs: `docker compose logs nginx`
3. Reload config: `docker compose exec nginx nginx -s reload`
4. Restart NGINX: `docker compose restart nginx`

### SSL Certificate Problems
1. **Public Services**: Check Cloudflare Origin Certificates are in place
2. **Local Services**: Check Let's Encrypt renewal logs: `cat ~/letsencrypt/logs/renewal.log`
3. **Test renewal**: `bash ~/83rr-poweredge/scripts/renew-letsencrypt-certs.sh`
4. **Reload NGINX**: After certificate update, reload NGINX configuration

### Cannot Connect
1. Verify server is up: `ping 192.168.1.179`
2. Check Docker: `docker ps`
3. Check NGINX: `docker compose logs nginx`
4. Test endpoints: `curl http://localhost/health`
