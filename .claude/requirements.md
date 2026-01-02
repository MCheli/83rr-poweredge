# Claude Code Requirements for Homelab Management

## Project Overview
You are managing a homelab infrastructure running on Ubuntu Server 24.04.3. The server uses Docker Compose for container management and NGINX as a reverse proxy. Your role is to help maintain, deploy, and troubleshoot services.

## Core Principles
1. **Safety First**: Always verify changes before applying
2. **Test Incrementally**: Deploy one change at a time
3. **Verify Success**: Check logs and health after every deployment
4. **Document Changes**: Commit to git with clear messages
5. **Monitor Services**: Use Docker Compose and NGINX logs for troubleshooting

## Workflow for ANY Configuration Change

### Standard Deployment Process
```bash
# 1. Navigate to project directory
cd ~/83rr-poweredge

# 2. Make your changes to docker-compose.yml or service configuration
# Edit files as needed

# 3. Test configuration syntax
docker compose -f docker-compose.yml -f docker-compose.prod.yml config

# 4. Deploy changes
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 5. Check service status
docker ps
docker compose logs -f <service_name>

# 6. Verify service endpoints
curl -I https://<service_domain>
```

### Quick Commands Reference

#### Check Service Status
```bash
# See all running containers
docker ps --format 'table {{.Names}}\t{{.Status}}'

# Check specific service
docker ps --filter name=<service_name>

# Service health from Docker Compose
docker compose ps
```

#### View Logs
```bash
# Live logs for all services
docker compose logs -f

# Live logs for specific service
docker compose logs -f <service_name>

# Last 100 lines
docker compose logs --tail 100 <service_name>

# With timestamps
docker compose logs -t --tail 50 <service_name>
```

#### Service Control
```bash
# Restart a service
docker compose restart <service_name>

# Stop a service
docker compose stop <service_name>

# Start a service
docker compose start <service_name>

# Rebuild and restart
docker compose up -d --build <service_name>
```

#### Test Endpoints
```bash
# Test NGINX health
curl http://localhost/health

# Test public service
curl -I https://www.markcheli.com

# Test LAN service (from LAN)
curl -I https://grafana-local.ops.markcheli.com

# Test Flask API
curl https://flask.markcheli.com/health
```

## Service-Specific Guidelines

### NGINX Configuration
When modifying NGINX:
1. **Configuration File**: `infrastructure/nginx/conf.d/production.conf`
2. **Test syntax**: `docker compose exec nginx nginx -t`
3. **Reload config**: `docker compose exec nginx nginx -s reload`
4. **Always include** SSL configuration for all services
5. **LAN services** must use IP-based access control

### SSL Certificate Management

**Public Services** (*.markcheli.com):
- Cloudflare Origin Certificates (15-year validity)
- Location: `infrastructure/nginx/certs/wildcard-markcheli.{crt,key}`
- No renewal required until 2040

**LAN Services** (*.ops.markcheli.com):
- Let's Encrypt certificates (90-day validity)
- Location: `infrastructure/nginx/certs/letsencrypt-ops-markcheli.{crt,key}`
- Auto-renewal via cron (daily at 3:00 AM)
- Manual renewal: `bash scripts/renew-letsencrypt-certs.sh`

## Service Access Policies

**Default Rule**: All infrastructure services should be **LAN-only** unless explicitly designated as public.

### LAN-Only Services (Default)
Use for admin interfaces, management tools, and internal services:
- **Naming**: `{service}-local.ops.markcheli.com`
- **SSL**: Let's Encrypt wildcard certificate
- **Access**: Restricted to 192.168.1.0/24
- **Examples**: Grafana, Prometheus, OpenSearch Dashboards, cAdvisor

### Public Services (Explicit Only)
Use only for services intended for internet access:
- **Naming**: `{service}.markcheli.com`
- **SSL**: Cloudflare Origin Certificate
- **Access**: Public internet
- **Examples**: Personal website, Flask API, JupyterLab
- **Requirement**: Must have explicit justification

### Adding a New Service

**IMPORTANT**: By default, all new services should be **LAN-only** for security.

1. Edit `docker-compose.yml` to add service definition
2. Create service-specific configuration files if needed
3. **Add NGINX server block** to `infrastructure/nginx/conf.d/production.conf`:
   - Use `-local.ops.markcheli.com` subdomain for LAN services
   - Use `.markcheli.com` subdomain only if public access required
4. Include necessary networks (usually `infrastructure`)
5. Deploy: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d <service_name>`
6. Test service endpoint
7. **Only make public if explicitly required and justified**
8. Commit changes to git

**Security Checklist**:
- [ ] Service uses appropriate subdomain naming
- [ ] LAN services restricted to local network
- [ ] Public access justified if applicable
- [ ] SSL certificates configured
- [ ] Health checks configured

## Error Resolution Playbook

### Deployment Fails
1. **Check Docker Compose logs**: `docker compose logs <service_name>`
2. **Verify configuration syntax**: `docker compose config`
3. **Check for port conflicts**: `netstat -tulpn | grep <port>`
4. **Check Docker status**: `systemctl status docker`
5. **Review recent changes**: `git diff HEAD~1`

### Service Won't Start
1. **Check resources**: `df -h; free -h`
2. **Check Docker**: `systemctl status docker`
3. **Inspect container**: `docker inspect <container_name>`
4. **Check events**: `docker events --since 10m`
5. **Review service logs**: `docker compose logs <service_name>`

### Network Issues
1. **Verify networks**: `docker network ls`
2. **Inspect network**: `docker network inspect infrastructure`
3. **Check connectivity**: `docker exec <container> ping <other_container>`
4. **Check NGINX routing**: `docker compose logs nginx | grep <service>`

### SSL Certificate Problems

**Public Services**:
1. Verify Cloudflare Origin Certificates in place
2. Check file permissions: `ls -la infrastructure/nginx/certs/`
3. Test NGINX configuration: `docker compose exec nginx nginx -t`
4. Reload NGINX: `docker compose exec nginx nginx -s reload`

**LAN Services**:
1. Check Let's Encrypt renewal logs: `cat ~/letsencrypt/logs/renewal.log`
2. Test renewal manually: `bash scripts/renew-letsencrypt-certs.sh`
3. Verify certificate copied to NGINX: `ls -la infrastructure/nginx/certs/letsencrypt-*`
4. Reload NGINX: `docker compose exec nginx nginx -s reload`

## Git Workflow

### After Successful Deployment
```bash
# Add changes
git add .

# Commit with descriptive message
git commit -m "feat(service): description of change

- What was changed
- Why it was changed
- Any important notes

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push to remote
git push
```

### After Failed Deployment
```bash
# Revert changes if needed
git checkout -- <file>

# Or stash for later analysis
git stash save "failed: {description}"

# Review what changed
git diff HEAD
```

## Important Warnings

### NEVER DO
- ❌ Delete volumes without backup
- ❌ Change network names of running stacks
- ❌ Deploy without testing compose syntax
- ❌ Expose admin interfaces publicly without authentication
- ❌ Ignore SSL certificate expiration warnings (Let's Encrypt)
- ❌ Remove IP-based access control from LAN services

### ALWAYS DO
- ✅ Keep .env file secure and out of git
- ✅ Test configuration with `docker compose config` first
- ✅ Wait for services to stabilize before checking health
- ✅ Document any manual changes in git commits
- ✅ Use descriptive commit messages
- ✅ Review logs after deployment
- ✅ Verify SSL certificates are working
- ✅ Check that services return proper HTTP 200 responses

## Performance Considerations
- JupyterLab containers can take 30-60 seconds to start
- NGINX configuration reloads are instant (no downtime)
- Database containers need 10-15 seconds to be ready
- Always wait appropriate time before health checks
- Monitor Let's Encrypt certificate renewal (90-day expiry)

## Resource Limits
- Let's Encrypt: Rate limits apply (50 certificates per week per domain)
- Docker logs: Can grow large, consider log rotation
- Cloudflare Origin Certificates: No rate limits (15-year validity)

## Quick Troubleshooting Decision Tree

```
Service Issue?
├── Won't Start?
│   ├── Check logs → Fix config → Redeploy
│   └── Resource issue → Free resources → Redeploy
├── Not Accessible?
│   ├── Check NGINX logs → Fix routing → Reload NGINX
│   └── Check DNS → Verify resolution
└── Unstable/Crashing?
    ├── Check health endpoint → Fix health check
    └── Review resource limits → Adjust limits → Redeploy
```

## Deployment Workflow Summary

### For Configuration Changes
1. Edit configuration files
2. Test syntax: `docker compose config`
3. Deploy: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
4. Verify: Check logs and test endpoints
5. Commit: Git commit with clear message

### For Service Updates
1. Edit docker-compose.yml or Dockerfile
2. Test syntax: `docker compose config`
3. Rebuild: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build <service>`
4. Verify: Check logs and test endpoints
5. Commit: Git commit with clear message

### For NGINX Routing Changes
1. Edit `infrastructure/nginx/conf.d/production.conf`
2. Test syntax: `docker compose exec nginx nginx -t`
3. Reload: `docker compose exec nginx nginx -s reload`
4. Verify: Test service endpoint
5. Commit: Git commit with clear message

## Getting Help
1. Check Docker Compose logs: `docker compose logs <service_name>`
2. Review this requirements.md file
3. Check NGINX logs for routing issues: `docker compose logs nginx`
4. View container status: `docker ps`
5. Search logs for error messages: `docker compose logs | grep -i error`
