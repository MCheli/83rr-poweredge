# Homelab Infrastructure Context

## System Architecture

### Server Details
- **OS**: Ubuntu Server 24.04.3 LTS
- **Hostname**: 83rr-poweredge  
- **Local IP**: 192.168.1.179
- **User**: mcheli
- **Docker**: Latest with Docker Compose
- **Management**: Portainer CE at https://portainer-local.ops.markcheli.com

### Network Setup
- **Domain**: markcheli.com
- **Subdomains**: 
  - ops.markcheli.com (public services)
  - *.ops.markcheli.com (various services)
  - *-local.ops.markcheli.com (LAN-only admin interfaces)
- **SSL**: Let's Encrypt via Traefik HTTP-01 challenge
- **Certificate Storage**: `/home/mcheli/letsencrypt/acme.json`

## Current Services Stack

### 1. Traefik (Reverse Proxy)
- **Version**: v3.0
- **Container Name**: traefik
- **Ports**: 80, 443 (public), 8080 (dashboard, LAN only)
- **Dashboard**: https://traefik-local.ops.markcheli.com
- **Auth**: Basic auth (user: admin)
- **Networks**: traefik_default (all services must connect to this)
- **Stack ID in Portainer**: 10

### 2. JupyterHub (Data Science Platform)  
- **URL**: https://jupyter.ops.markcheli.com
- **Containers**:
  - jupyterhub (main hub)
  - jupyterhub-proxy (configurable HTTP proxy)
  - jupyterhub-db (PostgreSQL database)
- **Auth**: DummyAuthenticator with password
- **User Volumes**: jupyterhub-user-{username}
- **Shared Volume**: jupyterhub-shared
- **Stack ID in Portainer**: 8

### 3. Logging Stack
- **Components**:
  - Loki (logs-loki-1) - Log aggregation
  - Promtail (logs-promtail-1) - Log collection
  - Grafana (logs-grafana-1) - Visualization
- **Grafana URL**: https://grafana.ops.markcheli.com (if configured)
- **Stack ID in Portainer**: 34
- **Storage Path**: `/data/compose/34/logs/`

### 4. Portainer
- **URL**: https://portainer-local.ops.markcheli.com
- **Version**: CE latest
- **Data**: /var/lib/docker/volumes/portainer_data
- **Stacks Storage**: /data/compose/{stack_id}/

## Docker Networks
- **traefik_default**: External network for all services needing reverse proxy
- **jupyterhub-net**: Internal network for JupyterHub components
- **bridge**: Default Docker network

## Important Paths

### On Server (83rr-poweredge)
```
/home/mcheli/letsencrypt/          # SSL certificates
/var/lib/docker/volumes/            # Docker volumes
/data/compose/                      # Portainer stack configs (inside container)
  ├── 8/                           # JupyterHub
  ├── 10/                          # Traefik  
  └── 34/logs/                    # Logging stack
```

### On MacBook (Development)
```
~/homelab-claude/                   # Main project directory
  ├── .claude/                     # Claude Code context
  ├── infrastructure/              # Docker compose files
  ├── scripts/                     # Deployment scripts
  ├── backups/                     # Automatic backups
  └── logs/                        # Deployment logs
```

## Deployment Method
- **Primary**: Portainer API for stack deployment
- **Secondary**: SSH for debugging and log viewing
- **Backup**: Automatic before each deployment
- **Rollback**: Automatic on failure (configurable)

## Security Considerations
1. **LAN-only middleware**: Applied to all admin interfaces
2. **Basic Auth**: Required for Traefik dashboard
3. **SSL**: Enforced for all public services
4. **IP Allowlist**: 192.168.1.0/24,10.0.0.0/8,172.16.0.0/12
5. **HTTP→HTTPS**: Automatic redirect for all services

## Common Tasks

### Adding a New Service
1. Create docker-compose.yaml in infrastructure/{service}/
2. Add Traefik labels for routing
3. Include traefik_default network
4. Deploy via: `python scripts/deploy.py {service} infrastructure/{service}/docker-compose.yaml`

### Checking Service Health
```bash
ssh 83rr-poweredge "docker ps"
ssh 83rr-poweredge "docker logs {container_name}"
```

### Updating Existing Service
1. Edit local docker-compose.yaml
2. Run deployment script (auto-backs up current version)
3. Script auto-checks health and rollbacks if needed

## Known Issues & Quirks
1. Portainer adds number suffixes to containers (e.g., logs-loki-1)
2. Some services take 15-30 seconds to fully start
3. JupyterHub requires custom image rebuild for package changes
4. Let's Encrypt rate limits: 50 certs per week per domain

## Emergency Procedures

### Service Down
1. Check logs: `ssh 83rr-poweredge "docker logs {container}"`
2. Restart: `ssh 83rr-poweredge "docker restart {container}"`
3. Rollback: `python scripts/rollback.py {stack_name}`

### Traefik Not Routing  
1. Check certificate: `ssh 83rr-poweredge "cat /home/mcheli/letsencrypt/acme.json | jq"`
2. Check routing: Visit https://traefik-local.ops.markcheli.com/dashboard/
3. Restart: `ssh 83rr-poweredge "docker restart traefik"`

### Cannot Connect
1. Verify server is up: `ping 192.168.1.179`
2. Check SSH: `ssh mcheli@83rr-poweredge`
3. Check Docker: `ssh 83rr-poweredge "docker ps"`