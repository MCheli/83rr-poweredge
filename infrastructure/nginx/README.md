# NGINX Reverse Proxy

NGINX serves as the main reverse proxy and SSL termination point for all services in the 83RR PowerEdge infrastructure.

## Overview

- **Role**: Reverse proxy, SSL termination, load balancing
- **Ports**: 80 (HTTP), 443 (HTTPS), 25565 (Minecraft TCP passthrough)
- **Image**: nginx:alpine (custom Dockerfile)

## Architecture

```
                                    ┌─────────────────────────────────────┐
                                    │           NGINX Container           │
                                    │                                     │
Internet ──► Cloudflare ──► Port 443 ──► SSL Termination ──► Upstream Services
                           Port 80  ──► Redirect to HTTPS
                           Port 25565 ──► TCP Passthrough ──► Minecraft
                                    │                                     │
                                    └─────────────────────────────────────┘
```

## Directory Structure

```
nginx/
├── Dockerfile           # Custom NGINX image with SSL support
├── .dockerignore        # Build exclusions
├── conf.d/              # NGINX configuration files
│   └── production.conf  # Main routing configuration
├── certs/               # SSL certificates (production)
│   ├── wildcard-markcheli.crt      # Cloudflare Origin Cert (*.markcheli.com)
│   ├── wildcard-markcheli.key      # Private key
│   ├── letsencrypt-ops-markcheli.crt  # Let's Encrypt (*.ops.markcheli.com)
│   └── letsencrypt-ops-markcheli.key  # Private key
├── dev-certs/           # Self-signed certificates (development)
└── logs/                # NGINX logs (legacy, now uses stdout)
```

## Configuration

### Upstream Services

The following upstreams are defined in `conf.d/production.conf`:

| Upstream | Target | Description |
|----------|--------|-------------|
| `personal_website` | personal-website:3000 | Nuxt.js website |
| `flask_api` | flask-api:5000 | Flask REST API |
| `jupyter` | jupyterhub-proxy:8000 | JupyterHub |
| `grafana` | grafana:3000 | Grafana dashboards |
| `prometheus` | prometheus:9090 | Prometheus metrics |
| `cadvisor` | cadvisor:8080 | Container metrics |
| `opensearch_dashboards` | opensearch-dashboards:5601 | Log visualization |

### Public Services (*.markcheli.com)

| Domain | Backend | SSL |
|--------|---------|-----|
| www.markcheli.com | personal_website | Cloudflare Origin |
| flask.markcheli.com | flask_api | Cloudflare Origin |
| jupyter.markcheli.com | jupyter | Cloudflare Origin |
| minecraft.markcheli.com:25565 | TCP passthrough | N/A |

### LAN Services (*.ops.markcheli.com)

| Domain | Backend | SSL |
|--------|---------|-----|
| grafana-local.ops.markcheli.com | grafana | Let's Encrypt |
| prometheus-local.ops.markcheli.com | prometheus | Let's Encrypt |
| cadvisor-local.ops.markcheli.com | cadvisor | Let's Encrypt |
| logs-local.ops.markcheli.com | opensearch_dashboards | Let's Encrypt |

## SSL Certificates

### Cloudflare Origin Certificates (Public Services)
- **Validity**: 15 years (expires 2040)
- **Mode**: Full (Strict) in Cloudflare dashboard
- **Files**: `wildcard-markcheli.crt`, `wildcard-markcheli.key`

### Let's Encrypt Certificates (LAN Services)
- **Validity**: 90 days (auto-renewal)
- **Challenge**: DNS-01 via Cloudflare API
- **Files**: `letsencrypt-ops-markcheli.crt`, `letsencrypt-ops-markcheli.key`
- **Renewal**: Daily cron job at 3:00 AM

## Management Commands

```bash
# Test configuration
make nginx-test
# or: docker compose exec nginx nginx -t

# Reload configuration (no downtime)
make nginx-reload
# or: docker compose exec nginx nginx -s reload

# View logs
make logs s=nginx
# or: docker compose logs -f nginx

# Rebuild after Dockerfile changes
docker compose build nginx
docker compose up -d --force-recreate nginx
```

## Metrics & Monitoring

NGINX exposes metrics via the stub_status endpoint:

- **Endpoint**: `http://nginx:80/nginx_status` (internal only)
- **Exporter**: nginx-prometheus-exporter scrapes this endpoint
- **Dashboard**: Grafana "NGINX" dashboard

Available metrics:
- Active connections
- Requests per second
- Reading/Writing/Waiting connections
- Total accepted/handled connections

## Health Check

NGINX includes a health check endpoint:

```bash
curl http://localhost/health
# Returns: healthy
```

The Docker health check verifies this endpoint every 30 seconds.

## Adding a New Service

1. **Add upstream** in `conf.d/production.conf`:
   ```nginx
   upstream new_service {
       server new-service:8080;
   }
   ```

2. **Add server block**:
   ```nginx
   server {
       listen 443 ssl;
       http2 on;
       server_name new-service.markcheli.com;

       ssl_certificate /etc/nginx/certs/wildcard-markcheli.crt;
       ssl_certificate_key /etc/nginx/certs/wildcard-markcheli.key;

       location / {
           proxy_pass http://new_service;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. **Test and reload**:
   ```bash
   make nginx-test
   make nginx-reload
   ```

## Security Features

- **HSTS**: Strict-Transport-Security header on all HTTPS responses
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
- **HTTP to HTTPS Redirect**: All HTTP traffic redirected to HTTPS
- **Internal Metrics**: stub_status only accessible from Docker networks

## Troubleshooting

### 502 Bad Gateway
```bash
# Check if upstream service is running
docker ps | grep <service_name>

# Check NGINX can reach upstream
docker exec nginx wget -qO- http://<upstream>:<port>/

# Reload NGINX to refresh DNS
docker compose exec nginx nginx -s reload
```

### SSL Certificate Issues
```bash
# Check certificate files exist
ls -la infrastructure/nginx/certs/

# Verify certificate validity
openssl x509 -in infrastructure/nginx/certs/wildcard-markcheli.crt -text -noout

# Test SSL connection
openssl s_client -connect www.markcheli.com:443 -servername www.markcheli.com
```

### Configuration Errors
```bash
# Test configuration syntax
docker compose exec nginx nginx -t

# View detailed error logs
docker compose logs nginx | grep error
```

---

Part of the 83RR PowerEdge homelab infrastructure.
