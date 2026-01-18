# Post-Reboot Verification Checklist

**Created**: January 18, 2026
**Purpose**: Verify all services and configurations after hardware reboot

---

## Quick Verification Commands

Run these commands to quickly verify the system:

```bash
cd ~/83rr-poweredge
source venv/bin/activate
python scripts/quick_service_test.py
```

---

## 1. Basic System Checks

- [ ] **SSH Access**: Can connect to server via SSH
- [ ] **System Time**: `date` shows correct time
- [ ] **Disk Space**: `df -h` shows adequate free space
- [ ] **Memory**: `free -h` shows expected memory

```bash
# Quick system check
uptime && date && df -h / && free -h
```

---

## 2. NAS Mount Persistence

**Critical**: Verify the NAS auto-mounted from `/etc/fstab`

- [ ] **Mount exists**: `/mnt/nas` is mounted
- [ ] **Backup directory accessible**: Can read/write to backup location
- [ ] **Permissions correct**: mcheli user can access files

```bash
# Check NAS mount
mount | grep nas
ls -la /mnt/nas/
ls -la /mnt/nas/83rr-backup/
```

**If NAS not mounted**:
```bash
sudo mount /mnt/nas
```

---

## 3. Docker Services

- [ ] **Docker daemon running**: `systemctl status docker`
- [ ] **All containers started**: Check with `docker ps`

```bash
# Check Docker status
systemctl status docker --no-pager

# List all containers (should all be "Up")
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Count running containers (expected: ~15-20)
docker ps -q | wc -l
```

### Expected Running Containers
| Container | Purpose |
|-----------|---------|
| nginx | Reverse proxy |
| personal-website | Main website |
| cookbook | Recipe website |
| flask-api | REST API |
| jupyterhub | Data science environment |
| jupyterhub-db | JupyterHub PostgreSQL |
| minecraft | Game server |
| plex | Media server |
| seafile | File sync |
| seafile-memcached | Seafile cache |
| seafile-mariadb | Seafile database |
| opensearch | Log storage |
| opensearch-dashboards | Log visualization |
| grafana | Metrics dashboards |
| prometheus | Metrics collection |
| cadvisor | Container monitoring |
| fluent-bit | Log shipper |
| node-exporter | Host metrics |
| nginx-exporter | NGINX metrics |

**If containers not running**:
```bash
cd ~/83rr-poweredge
docker compose up -d
```

---

## 4. Public Services (HTTPS)

Test from the server or external network:

- [ ] **Personal Website**: https://www.markcheli.com → HTTP 200
- [ ] **Cookbook**: https://cookbook.markcheli.com → HTTP 200
- [ ] **Flask API**: https://flask.markcheli.com → HTTP 200
- [ ] **JupyterHub**: https://data.markcheli.com → HTTP 200
- [ ] **Plex**: https://videos.markcheli.com → HTTP 401 (auth expected)
- [ ] **Seafile**: https://files.markcheli.com → HTTP 200
- [ ] **Home Assistant**: https://home.markcheli.com → HTTP 200

```bash
# Test public services
curl -sI https://www.markcheli.com | head -1
curl -sI https://cookbook.markcheli.com | head -1
curl -sI https://flask.markcheli.com | head -1
curl -sI https://data.markcheli.com | head -1
curl -sI https://videos.markcheli.com | head -1
curl -sI https://files.markcheli.com | head -1
curl -sI https://home.markcheli.com | head -1
```

---

## 5. LAN Services (Basic Auth Protected)

These should return HTTP 401 without credentials (expected behavior):

- [ ] **Grafana**: https://dashboard.ops.markcheli.com → HTTP 401
- [ ] **Prometheus**: https://prometheus.ops.markcheli.com → HTTP 401
- [ ] **cAdvisor**: https://cadvisor.ops.markcheli.com → HTTP 401
- [ ] **OpenSearch Dashboards**: https://logs.ops.markcheli.com → HTTP 401
- [ ] **OpenSearch API**: https://opensearch.ops.markcheli.com → HTTP 401

```bash
# Test LAN services (401 expected without auth)
curl -sI https://dashboard.ops.markcheli.com | head -1
curl -sI https://prometheus.ops.markcheli.com | head -1
curl -sI https://cadvisor.ops.markcheli.com | head -1
curl -sI https://logs.ops.markcheli.com | head -1
curl -sI https://opensearch.ops.markcheli.com | head -1

# Test with credentials (should return 200)
curl -sI -u admin:oKTMhb8B https://dashboard.ops.markcheli.com | head -1
curl -sI -u admin:oKTMhb8B https://prometheus.ops.markcheli.com | head -1
```

**Credentials**: `admin` / `oKTMhb8B`

---

## 6. Minecraft Server

- [ ] **Server responding**: Port 25565 accessible

```bash
# Check Minecraft port
nc -zv localhost 25565

# Check container logs for startup completion
docker logs minecraft --tail 20 | grep -i "done"
```

---

## 7. Security Services

### UFW Firewall
- [ ] **UFW active**: Firewall is enabled
- [ ] **Rules intact**: SMB restricted to LAN

```bash
sudo ufw status verbose
```

### fail2ban
- [ ] **Service running**: fail2ban active
- [ ] **SSH jail active**: Protecting SSH

```bash
sudo systemctl status fail2ban --no-pager
sudo fail2ban-client status sshd
```

---

## 8. Monitoring Health

### Prometheus Targets
- [ ] **All targets UP**: No targets in DOWN state

```bash
# Check Prometheus targets (with auth)
curl -s -u admin:oKTMhb8B https://prometheus.ops.markcheli.com/api/v1/targets | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join([f\"{t['labels']['job']}: {t['health']}\" for t in d['data']['activeTargets']]))"
```

### Grafana
- [ ] **Dashboards loading**: Can view metrics

---

## 9. Log Pipeline

- [ ] **Fluent Bit running**: Shipping logs to OpenSearch
- [ ] **OpenSearch healthy**: Cluster status green/yellow

```bash
# Check Fluent Bit logs
docker logs fluent-bit --tail 10

# Check OpenSearch cluster health (with auth)
curl -s -u admin:oKTMhb8B https://opensearch.ops.markcheli.com/_cluster/health | python3 -m json.tool
```

---

## 10. Backup System

- [ ] **Cron job exists**: Backup scheduled at 2:00 AM
- [ ] **Last backup exists**: Recent backup in NAS

```bash
# Check cron job
crontab -l | grep backup

# Check latest backup
ls -lt /mnt/nas/83rr-backup/daily/ | head -5
```

---

## Troubleshooting

### If Docker containers didn't start:
```bash
cd ~/83rr-poweredge
docker compose up -d
docker compose logs --tail 50
```

### If NAS didn't mount:
```bash
# Check credentials file
sudo cat /root/.nas-credentials

# Manual mount
sudo mount /mnt/nas

# Check fstab entry
grep nas /etc/fstab
```

### If services return 502/503:
```bash
# Check NGINX config
docker compose exec nginx nginx -t

# Check specific service logs
docker compose logs <service-name>
```

### If firewall blocking services:
```bash
sudo ufw status
sudo ufw allow <port>
```

---

## All-in-One Verification Script

Run this single command for a comprehensive check:

```bash
cd ~/83rr-poweredge && source venv/bin/activate && python scripts/quick_service_test.py
```

---

**Expected Result**: All public services return HTTP 200, all LAN services return HTTP 401 (auth working), Minecraft responds on port 25565, NAS is mounted, all Docker containers are running.
