# Claude Code Requirements for Homelab Management

## Project Overview
You are managing a homelab infrastructure running on Ubuntu Server 24.04.3. The server uses Docker with Portainer for container management and Traefik as a reverse proxy. Your role is to help maintain, deploy, and troubleshoot services.

## Core Principles
1. **Safety First**: Always backup before making changes
2. **Test Incrementally**: Deploy one change at a time
3. **Verify Success**: Check logs and health after every deployment
4. **Document Changes**: Commit to git with clear messages
5. **Rollback on Failure**: Automatically revert if deployment fails

## Workflow for ANY Configuration Change

### Standard Deployment Process
```bash
# 1. Activate environment (if not already active)
source venv/bin/activate

# 2. Make your changes to the docker-compose.yaml file
edit infrastructure/{service}/docker-compose.yaml

# 3. Deploy with automatic validation
python scripts/deploy.py {service} infrastructure/{service}/docker-compose.yaml

# The script automatically:
# - Creates backup
# - Deploys via Portainer API  
# - Waits for stabilization
# - Checks container health
# - Shows logs if issues
# - Rolls back on failure
# - Retries if configured
```

### Quick Commands Reference

#### Check Service Status
```bash
# See all running containers
ssh 83rr-poweredge "docker ps --format 'table {{.Names}}\t{{.Status}}'"

# Check specific service
ssh 83rr-poweredge "docker ps --filter name=traefik"
```

#### View Logs
```bash
# Live logs
ssh 83rr-poweredge "docker logs -f {container_name}"

# Last 100 lines
ssh 83rr-poweredge "docker logs --tail 100 {container_name}"

# With timestamps
ssh 83rr-poweredge "docker logs -t --tail 50 {container_name}"
```

#### Manual Service Control
```bash
# Restart a service
ssh 83rr-poweredge "docker restart {container_name}"

# Stop a service
ssh 83rr-poweredge "docker stop {container_name}"

# Start a service
ssh 83rr-poweredge "docker start {container_name}"
```

#### Test Endpoints
```bash
# Test Traefik dashboard (LAN only)
curl -u admin:password https://traefik-local.ops.markcheli.com/api/overview

# Test public service
curl -I https://ops.markcheli.com

# Test Portainer API
curl -H "X-API-Key: $PORTAINER_API_KEY" $PORTAINER_URL/api/stacks
```

## Service-Specific Guidelines

### Traefik Configuration
When modifying Traefik:
1. **Never remove** the LAN-only middleware from admin interfaces
2. **Always include** SSL configuration for public services
3. **Test locally** before deploying: `docker-compose -f infrastructure/traefik/docker-compose.yaml config`
4. **Check dashboard** after deployment: https://traefik-local.ops.markcheli.com

Required labels for new services behind Traefik:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.{service}.rule=Host(`{subdomain}.ops.markcheli.com`)"
  - "traefik.http.routers.{service}.entrypoints=websecure"
  - "traefik.http.routers.{service}.tls=true"
  - "traefik.http.routers.{service}.tls.certresolver=letsencrypt"
  - "traefik.http.services.{service}.loadbalancer.server.port={port}"
networks:
  - traefik_default
```

### JupyterHub Updates
When modifying JupyterHub:
1. **Custom image changes** require rebuilding the Dockerfile
2. **User data** is preserved in named volumes
3. **Database** must stay healthy or users can't login
4. **Proxy** must be running for external access

### Adding a New Service
1. Create `infrastructure/{service}/docker-compose.yaml`
2. Include necessary networks (usually `traefik_default`)
3. Add Traefik labels if it needs web access
4. Create a README.md explaining the service
5. Deploy: `python scripts/deploy.py {service} infrastructure/{service}/docker-compose.yaml`
6. Add health checks to deploy.py if needed
7. Commit changes to git

## Container Naming Conventions

Portainer modifies container names. Here's the mapping:

| Service | Compose Name | Actual Container Name |
|---------|--------------|----------------------|
| Traefik | traefik | traefik |
| Whoami | whoami | whoami |
| JupyterHub | jupyterhub | jupyterhub |
| JupyterHub Proxy | chp | jupyterhub-proxy |
| JupyterHub DB | hub-db | jupyterhub-db |
| Loki | loki | logs-loki-1 |
| Promtail | promtail | logs-promtail-1 |
| Grafana | grafana | logs-grafana-1 |

## Error Resolution Playbook

### Deployment Fails
1. **Check the deployment log**: `cat logs/deployment_*.log`
2. **View container logs**: `ssh 83rr-poweredge "docker logs {container}"`
3. **Verify compose syntax**: `docker-compose -f {file} config`
4. **Check for port conflicts**: `ssh 83rr-poweredge "netstat -tulpn | grep {port}"`
5. **Manual rollback if needed**: `python scripts/rollback.py {service}`

### Service Won't Start
1. **Check resources**: `ssh 83rr-poweredge "df -h; free -h"`
2. **Check Docker**: `ssh 83rr-poweredge "systemctl status docker"`
3. **Inspect container**: `ssh 83rr-poweredge "docker inspect {container}"`
4. **Check events**: `ssh 83rr-poweredge "docker events --since 10m"`

### Network Issues
1. **Verify networks**: `ssh 83rr-poweredge "docker network ls"`
2. **Inspect network**: `ssh 83rr-poweredge "docker network inspect traefik_default"`
3. **Check connectivity**: `ssh 83rr-poweredge "docker exec {container} ping {other_container}"`

### SSL Certificate Problems
1. **Check acme.json**: `ssh 83rr-poweredge "ls -la /home/mcheli/letsencrypt/"`
2. **View Traefik logs**: `ssh 83rr-poweredge "docker logs traefik | grep acme"`
3. **Verify DNS**: `nslookup {subdomain}.ops.markcheli.com`
4. **Test HTTP challenge**: `curl http://{subdomain}.ops.markcheli.com/.well-known/acme-challenge/test`

## Git Workflow

### After Successful Deployment
```bash
# Add changes
git add infrastructure/{service}/

# Commit with descriptive message
git commit -m "feat(service): description of change

- What was changed
- Why it was changed
- Any important notes"

# Track deployment
git tag -a "deploy-{service}-$(date +%Y%m%d-%H%M%S)" -m "Deployed {service}"
```

### After Failed Deployment
```bash
# Save failed attempt for analysis
git stash save "failed: {description}"

# Or commit to a branch
git checkout -b fix/{issue}
git commit -m "debug: attempting to fix {issue}"
```

## Important Warnings

### NEVER DO
- ❌ Remove authentication from admin interfaces
- ❌ Expose Portainer publicly without VPN
- ❌ Delete volumes without backup
- ❌ Change network names of running stacks
- ❌ Deploy without testing compose syntax
- ❌ Ignore health check failures

### ALWAYS DO  
- ✅ Keep .env file secure and out of git
- ✅ Test configuration locally first
- ✅ Wait for services to stabilize before checking health
- ✅ Document any manual changes
- ✅ Use semantic commit messages
- ✅ Review logs after deployment

## Performance Considerations
- JupyterHub containers can take 30-60 seconds to start
- Traefik certificate generation can take 10-30 seconds
- Database containers need 10-15 seconds to be ready
- Always wait appropriate time before health checks

## Resource Limits
- Portainer API: No rate limits known
- Let's Encrypt: 50 certificates per week per domain
- SSH connections: Keep alive with ServerAliveInterval
- Docker logs: Can grow large, consider log rotation

## Quick Troubleshooting Decision Tree

```
Service Issue?
├── Won't Start?
│   ├── Check logs → Fix config → Redeploy
│   └── Resource issue → Free resources → Redeploy
├── Not Accessible?
│   ├── Check Traefik dashboard → Fix labels → Redeploy
│   └── Check DNS → Fix domain → Wait for propagation
└── Unstable/Crashing?
    ├── Check health endpoint → Fix health check
    └── Review resource limits → Adjust limits → Redeploy
```

## Getting Help
1. Check deployment logs in `logs/` directory
2. Review this requirements.md file
3. Check Traefik dashboard for routing issues
4. View Portainer UI for container status
5. Search container logs for error messages