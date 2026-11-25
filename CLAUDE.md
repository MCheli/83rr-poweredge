# Claude Code Infrastructure Management Guide

This document provides Claude Code with comprehensive instructions for managing the 83RR PowerEdge homelab infrastructure.

## 🎯 Current Architecture (Phase 6, as of November 2026)

**Deployment Method**: Native Docker Compose
**Reverse Proxy**: NGINX
**SSL Certificates**: Cloudflare Origin Certificate for public sites (valid to 2040); Let's Encrypt for `*.ops` and the status page (auto-renewed)
**DNS Provider**: Cloudflare
**Container Runtime**: Docker on Ubuntu 24.04 LTS (Dell PowerEdge R630, 192.168.1.179; clock in UTC)

### Core Principles
- **Native Docker Compose**: All services deployed via `docker compose` commands
- **Direct Management**: No SSH or API intermediaries required
- **Long-lived Certificates**: Cloudflare Origin Certificate valid until 2040 for everything behind Cloudflare
- **Minimal Complexity**: Straightforward deployment without orchestration layers

---

## 🐍 Python Environment Setup

**IMPORTANT**: Always use the local virtual environment for Python development.

### Setup Commands
```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

### Running Python Scripts
Always activate the virtual environment before running any Python scripts:
```bash
source venv/bin/activate && python script_name.py
```

**All script examples in this document assume the virtual environment is activated.**

---

## 📋 Standard Operating Procedures

**On the server, always pass both production files**: `docker compose -f docker-compose.yml -f docker-compose.prod.yml ...`. A bare `docker compose` also loads `docker-compose.override.yml` (local development settings). The Makefile targets (`make deploy`, `make restart`, `make pull`, ...) and the deploy scripts (`scripts/cookbook-deploy.sh`, `scripts/tasks-deploy.sh`) already do this; only `make up-dev` uses the override file. The examples below write the long form as `$DC`:

```bash
DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
```

### Deploy All Services
```bash
# Navigate to project directory
cd ~/83rr-poweredge

# Deploy all services (production configuration)
$DC up -d                       # or: make up

# Deploy specific service
$DC up -d <service_name>

# Check deployment status
docker ps
```

Services in a compose profile (`homelab-mcp`: `mcp`, `house-transcriber`: `transcriber`) start only when the profile is on; the server's `.env` sets `COMPOSE_PROFILES=mcp,transcriber`. basic-memory, the Obsidian sync clients and OpenClaw have their own standalone compose files (`infrastructure/ai-context/`, `infrastructure/openclaw/`).

### Update Existing Service
```bash
# Pull latest changes
git pull --ff-only

# Pull a new image (GHCR apps) or rebuild (locally built: nginx, homelab-mcp)
$DC pull <service_name>
$DC build <service_name>

# Recreate the service with the new image/configuration
$DC up -d --no-deps <service_name>      # or: make deploy s=<service_name>

# Verify service is healthy
docker ps | grep <service_name>
```

### View Logs
```bash
# View logs for specific service
docker compose logs -f <service_name>

# View logs for all services
docker compose logs -f

# View last 100 lines
docker compose logs --tail 100 <service_name>

# Search logs for errors
docker compose logs <service_name> | grep -i error

# Search OpenSearch (all services, last N hours)
scripts/logq.sh errors 6
```

Read-only commands (`logs`, `exec`, `ps`) act on the running containers and work with or without the extra `-f` flags.

### Stop/Restart Services
```bash
# Stop specific service
$DC stop <service_name>

# Restart specific service
$DC restart <service_name>      # or: make restart s=<service_name>

# Stop all services
$DC down

# Stop all services and remove volumes (⚠️  DANGER: deletes data)
$DC down -v
```

### Merging changes
Pull requests are merged with the approved helper on the Mac mini, `~/.local/bin/gh-safe-merge MCheli/83rr-poweredge <PR> --squash` (it refuses a PR with failing checks, and one with pending checks unless `--auto` is given, so merge once CodeQL has passed; a raw `gh pr merge` is refused there). Then `git pull --ff-only` in the server checkout (`~/83rr-poweredge`) and check that `git status` is clean.

---

## 🏗️ Infrastructure Architecture

### Active Services
The main stack is `docker-compose.yml` + `docker-compose.prod.yml`; entries 27 and 31 have standalone compose files. Images marked digest-pinned are not watchtower-managed and are bumped deliberately; the `ghcr.io/mcheli/*` app images carry the Watchtower label and update themselves.

1. **nginx** - Reverse proxy and SSL termination, built from `infrastructure/nginx` (image `ghcr.io/mcheli/nginx`). `conf.d/` and `certs/` are bind-mounted (config edits need only `nginx -t` + reload); `nginx.conf` (log format) is baked into the image and needs a rebuild. On the `infrastructure`, `demo-proxy` and `openclaw_nginx-openclaw` networks.
2. **personal-website** - Nuxt.js personal portfolio (image from ghcr.io/mcheli/personal-website)
3. **cookbook** / **cookbook-db** - Cookbook app (FastAPI + Vue, image from ghcr.io/mcheli/cookbook, port 8000): public recipes, Google sign-in for anyone, weekly lists, Whole Foods cart, AI on each user's own Anthropic key (no server AI key). **cookbook-demo** / **cookbook-demo-db**: the read-only public demo (Claudius Banks seed, internal network for its DB, reached by nginx over `demo-proxy` and not on `infrastructure`, explicit env only; cron restarts it nightly). Deploy with checks: `scripts/cookbook-deploy.sh`
4. **flask-api** - Python Flask REST API (image from ghcr.io/mcheli/flask-api)
5. **minecraft** - Minecraft Java Edition server (Paper, `itzg/minecraft-server`, digest-pinned), port 25565 straight to the host (not proxied). The world is in the `minecraft_data_local` volume.
6. **asa** - ARK: Survival Ascended dedicated server (`mschnitzer/asa-linux-server`, Wine/Proton, digest-pinned). Game port 7777/udp forwarded from the internet, RCON 11520 on 127.0.0.1 only. The admin and join passwords come from `.env` and are rendered into `GameUserSettings.ini` at start (the template in `infrastructure/asa/config/` has placeholders only). ARK ignores SIGTERM, so the UPS shutdown saves the world over RCON first (`infrastructure/nut/pre-shutdown.sh`).
7. **plex** - Plex Media Server for streaming movies/TV/music
8. **seafile** - Self-hosted file sync and share (Dropbox alternative). 13.0 Docker layout (env-driven config) with `seafile-db` (MariaDB 10.11), `seafile-redis` (cache), `seafile-memcached` and `seafile-notification` (desktop sync push, edge-routed at `/notification`); digest-pinned, not watchtower-managed. Upgrades: `docs/seafile-upgrade-2026-11.md`
9. **opensearch** - Log aggregation and search (daily `logs-homelab-*` indices, 90-day retention, log-based alert monitors)
10. **opensearch-dashboards** - OpenSearch visualization (4 saved log dashboards)
11. **grafana** - Metrics dashboards (7 provisioned dashboards) and the Prometheus alert rules that push to ntfy (`infrastructure/monitoring/grafana/provisioning/`)
12. **prometheus** - Metrics collection and storage (30-day retention)
13. **cadvisor** - Container resource monitoring
14. **fluent-bit** - Log shipper: Docker logs, Docker events and the Plex, Seafile and fail2ban log files → OpenSearch
15. **node-exporter** - Host system metrics (CPU, memory, disk) plus textfile metrics written by cron scripts (`logs/textfile/`)
16. **nginx-exporter** - NGINX metrics for Prometheus
17. **tallied** / **tallied-scheduler** - Personal finance dashboard (image from ghcr.io/mcheli/tallied); the scheduler is the same image running background jobs.
18. **tallied-db** - PostgreSQL database for Tallied. Port 5432 is public on purpose (per-household `tld_*` roles, hostssl + scram; `tallied`/`tallied_app` rejected from outside Docker). Host fail2ban jail `postgresql-tallied` bans guessing on 5432 in DOCKER-USER (log fed by Fluent Bit to `/var/log/pg-auth/`); bans and `tld_` logins alert via ntfy. Docs: `infrastructure/fail2ban/README.md`
19. **tallied-demo** / **tallied-demo-db** - Tallied public demo at money-demo.markcheli.com: read-only, made-up Claudius Banks data, its own database on an internal network, reached by nginx over `demo-proxy` (not on `infrastructure`), no `.env`; cron restarts it nightly to reseed.
20. **tasks** / **tasks-db** - Cycle-based todo app (image from ghcr.io/mcheli/tasks), Google SSO auth. The app also serves the **Tasks MCP connector** for claude.ai at https://tasks.markcheli.com/mcp (OAuth; sign-in limited to the same allowlist as homelab-mcp, `HOMELAB_MCP_ALLOWED_EMAILS`; never on the demo). Deploy with checks: `scripts/tasks-deploy.sh`
21. **tasks-demo** / **tasks-demo-db** - Tasks public demo at tasks-demo.markcheli.com, built like the Tallied demo (own internal network, `demo-proxy`, nightly reseed).
22. **daily-report** - Thermal-printer daily report generator (image from ghcr.io/mcheli/daily-report) for the LAN printer at 192.168.1.147:9100. Scheduled printing is **paused** since 2026-11-23 (printer unplugged): `REPORT_TIMES` is empty in compose; set it back to `05:00` (US Eastern) and recreate the container to resume. The preview page and `/trigger` (report.ops) still work.
23. **energy-monitor** / **energy-monitor-db** - Panel tool that maps breaker circuits to energy-monitor CT channels (image `ghcr.io/mcheli/panel-tool`, from MCheli/energy-monitor). LAN-only at energy.ops.markcheli.com; it has no login of its own, so it must stay behind the `*.ops` allowlist.
24. **uptime-kuma** - Uptime monitor and the public status page https://status.markcheli.com (digest-pinned slim image). Probes the public, LAN and game endpoints and alerts through ntfy; monitors, notification and status page are set up by `scripts/setup_uptime_kuma.py`.
25. **ntfy** - Push notifications for homelab alerts (ntfy.markcheli.com, deny-all auth, topic `homelab`). OpenSearch alerting, Uptime Kuma, Grafana, Watchtower, the cron wrapper, NUT and Dependency-Track all publish here (replaced email alerting 2026-10-31). Routes: `docs/OBSERVABILITY.md#alerting`; ntfy setup: `infrastructure/opensearch/config/alerting/README.md`
26. **watchtower** - Automatic updates for containers with the label `com.centurylinklabs.watchtower.enable=true` (the `ghcr.io/mcheli/*` apps), polling every 5 minutes. Each update session's report goes to ntfy (silent priority); failures also page through the OpenSearch `watchtower-update-failure` monitor. Digest-pinned itself.
27. **openclaw** - Self-hosted agent/automation runtime (image `ghcr.io/openclaw/openclaw`, pinned by digest in `infrastructure/openclaw/docker-compose.yml`), on `openclaw-net` (egress) plus the internal `openclaw_nginx-openclaw` network; runtime data (secrets, credentials, workspace, agent state) under `infrastructure/openclaw/` (gitignored). Only the Discord channel is in use; the control UI is proxied by the main nginx at https://openclaw.ops.markcheli.com (LAN-only, :443 only — the old :80 ESP32 WebSocket path was removed 2026-11-01).
28. **deptrack-apiserver / deptrack-frontend / deptrack-db** - OWASP Dependency-Track v5 (LAN-only, deptrack.ops.markcheli.com): CVE tracking of every running container's SBOM. `scripts/sbom-scan.sh` (Syft, cron 03:30 UTC) uploads nightly; new HIGH/CRITICAL findings go to ntfy. Images pinned by digest, not watchtower-managed. Docs + runbook: `docs/dependency-track.md`
29. **homelab-mcp** - claude.ai connector (remote MCP server): read-only tools for the Seafile "AI Context" library (a backup copy of the notes since the 2026-11-23 cut-over), `notes_*` tools forwarded to basic-memory over the internal Docker network (fixed allowlist: 6 read tools plus `notes_write`/`notes_edit` since the cut-over, the only write path for AI notes; project pinned; no delete/move; writes refused under `templates/`; `HOMELAB_MCP_NOTES_MCP_URL`), plus optional `bus_*` tools that start Claude Code sessions on the Mac mini by ssh over the LAN (forced command into bus-gateway in the private mac-mini-collector repo; the mini has no public port) and, over that same link, four **read-only iMessage tools** (`imessage_recent`, `imessage_search`, `imessage_threads`, `imessage_unanswered`, since 2026-11-23: bus-gateway forwards them to the mini's iMessage service, `collector imessage-serve`, a LaunchAgent under the collector's Full-Disk-Access launcher that opens chat.db `mode=ro` and listens on a 0600 Unix socket; verification codes dropped, tapbacks skipped, limit ≤100, text ≤1,000 chars, answers ≤50 KB; no message text in any log; no new secret or port), built locally from `infrastructure/homelab-mcp` (not GHCR, not watchtower-managed), compose profile `mcp` (`COMPOSE_PROFILES=mcp` in .env once configured). Google OAuth sign-in limited to `HOMELAB_MCP_ALLOWED_EMAILS`; Seafile access via a read-only library token (startup refuses an rw token). Edge-routed at https://mcp.markcheli.com (MCP endpoint `/mcp`). Docs: `infrastructure/homelab-mcp/README.md`
30. **house-transcriber** - Transcribes speech from the 5 indoor UniFi cameras (allowlist by Protect id + MAC; never Driveway or the Front Door doorbell) into the AI Context RAW vault on this server (`/data/ai-context/raw/house-transcripts/YYYY/YYYY-MM-DD.md`, bind mount `/output`, runs as uid 1000; since the 2026-11-23 cut-over, before that the Seafile library through a read-write token, kept in the image as the roll-back). Image `ghcr.io/mcheli/house-transcriber` (private repo, watchtower-managed); CPU Whisper (faster-whisper), capped at 6 CPUs / 4 GB. No ports, no nginx route. Gated by HA `input_boolean.house_transcription` (fails closed). Logs counts only, never transcript text. Compose profile `transcriber`. Docs + deploy runbook: `docs/house-transcriber.md`
31. **basic-memory / obsidian-sync-notes / obsidian-sync-raw** - AI Context, **the main copy since the 2026-11-23 cut-over**: plain-Markdown vaults under `/data/ai-context/{notes,raw}` (outside the repo; auto-committed to local git every 15 min, notes pushed to the private repo MCheli/notes; tag `pre-cutover-2026-11-23` marks the state before), **basic-memory** 1.0.0 (digest-pinned, not watchtower-managed) mounting the real notes vault **read-write** and serving MCP at https://memory.ops.markcheli.com/mcp (nginx admits only the Mac mini, 192.168.1.161; no auth of its own) and to claude.ai through homelab-mcp's OAuth (#29). Every AI note write goes through basic-memory (Mark's decision 2026-11-23; no session edits vault files directly); `templates/` is in `.bmignore` and never rewritten; the one-time front-matter normalisation of all 2336 notes is a single vault commit. The Seafile "AI Context" library is now a **backup**: `scripts/ai-context/seafile-backup-push.py` (cron `*/30`, read-write library token in `/data/ai-context/.secrets/seafile-rw-token`) uploads changed files, never deletes, never touches `04-work/` or `05-raw/work-laptop/` (which stay Seafile-only); the old pull cron line is commented out (roll-back path, with the index-copy rsync and the pull token). The official Obsidian Sync headless client, one container per vault (compose profile `obsidian`), carries the notes to Mark's devices and his edits back. Standalone compose: `infrastructure/ai-context/docker-compose.yml`. Writers: claude.ai via `notes_write`/`notes_edit`, Mac mini sessions via `bm_write`/`bm_edit`, house-transcriber straight into the RAW vault (#30); the Mac mini collector still writes to Seafile `05-raw/mac-mini` (not pulled any more) until it is pointed at the server. The vaults, basic-memory's index and the homelab-mcp volume are in the nightly backup (`docs/BACKUP_RESTORE.md`). Docs + roll-back: `infrastructure/ai-context/README.md`
32. **knowledge** - Web reader and editor for the AI Context notes vault (image `ghcr.io/mcheli/knowledge`, private repo MCheli/knowledge, watchtower-managed): FastAPI + Vue on :8000, mounts `/data/ai-context/notes` **read-only** at `/vault`, indexes it into SQLite (FTS5) in the `knowledge_data` volume on start and keeps the index live with a file watcher (never writes to the vault itself). The editor (owner, and editors within their grants) saves, creates and appends notes only through basic-memory's MCP tools over the Docker network: `KNOWLEDGE_BASIC_MEMORY_URL=http://basic-memory:8000/mcp` and `KNOWLEDGE_BASIC_MEMORY_PROJECT=main` (the basic-memory project rooted at the same vault; an empty URL turns the editor off, every write then answers 503). Google sign-in, owner + allowlist (`KNOWLEDGE_OWNER_EMAIL`, `KNOWLEDGE_ALLOWED_EMAILS`), same Google OAuth client as Tasks/Cookbook; production refuses default secrets or the dev login. Public through Cloudflare at https://knowledge.markcheli.com (deployed 2026-11-24). `/ambient` (the graph slide of the ambient display) may be framed by the Mac mini kiosk only: `KNOWLEDGE_AMBIENT_FRAME_ANCESTORS=http://127.0.0.1:8765` in compose and an nginx `location = /ambient` without X-Frame-Options; every other page stays unframeable. Deploy: `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull knowledge && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps knowledge`

### Host-level config (not containers)
Plain files with an install header, installed on the host by hand (or by an agent with sudo):
- **NUT (UPS shutdown)** - `infrastructure/nut/` (since 2026-11-25): Network UPS Tools 2.8.1 (Ubuntu packages; upsd listens on localhost and the LAN address, port 3493, for the Synology NAS, which is a NUT network client) for the CyberPower CP1500PFCRM2U on USB, UPS name `ups`. After 5 minutes on battery (or low battery first) `pre-shutdown.sh` unmounts `/mnt/nas` and saves the ARK and Minecraft worlds over RCON, then forced shutdown takes the NAS and the R630 down cleanly. Kill-power is off: the UPS keeps powering the router and Home Assistant. Just before the shutdown NUT calls a Home Assistant webhook; when house mains is back, HA wakes the R630 and the NAS with Wake-on-LAN. ntfy pushes to `homelab`. Install/verify: `sudo infrastructure/nut/install.sh [--check]`; the real test cuts mains and needs Mark's yes. Docs: `infrastructure/nut/README.md`
- **fail2ban** - `infrastructure/fail2ban/`: two jails, `sshd` (Ubuntu's default) and `postgresql-tallied` (bans in the DOCKER-USER chain). Install: `sudo infrastructure/fail2ban/install.sh`; bans are logged to OpenSearch and summarised in ntfy. Docs: `infrastructure/fail2ban/README.md`
- **crontab** - `infrastructure/cron/crontab` is the source of truth for the `mcheli` crontab (times in UTC; every line runs through `scripts/cron-notify.sh`, which pushes failures to ntfy). Diff against `crontab -l` before installing: `infrastructure/cron/README.md`
- **Backups** - `scripts/backup.sh`, nightly at 02:00 UTC to the NAS (`/mnt/nas/83rr-backup`): database dumps, Docker volumes, configs, Seafile data and, since 2026-11-25, `/data/ai-context`. Failure or a missing run alerts three ways (cron wrapper, OpenSearch `backup-no-heartbeat`, Grafana `hl-backup-stale`). Docs + restore: `docs/BACKUP_RESTORE.md`
- **Home Assistant auto-update** - `scripts/ha-auto-update.py`, from cron daily at 04:15 US Eastern: installs Home Assistant OS/Supervisor/Core/add-on updates after a 3-day soak (never a Core X.Y.0), with a backup and health checks first. Docs: `docs/home-assistant-auto-update.md`
- **Let's Encrypt renewal** - `scripts/renew-letsencrypt-certs.sh`, cron daily at 03:00 UTC (certbot, Cloudflare DNS-01): the `*.ops.markcheli.com` and `status.markcheli.com` certificates. Details: `docs/LETSENCRYPT_LOCAL_SSL.md`
- **systemd drop-in** - `infrastructure/systemd/docker-wait-storage.conf` (Docker waits for the `/storage` RAID mount)
- **logrotate** - `infrastructure/logrotate/83rr-backup` (caps the backup log)

### Service Dependencies
- **nginx** must start first (other services proxy through it)
- **prometheus** should start before **grafana** (datasource dependency)
- All other services are independent

### Environment Variables
Each service can use `.env` files from its infrastructure directory:
- `infrastructure/minecraft/.env` - Minecraft server configuration
- Root `.env` - Cloudflare credentials, app secrets and global settings, including `COMPOSE_PROFILES=mcp,transcriber` (`.env.example` lists every variable, without values)

---

## 📊 Service Endpoints

### Public Services (HTTPS via Cloudflare)
- **https://www.markcheli.com** - Personal website
- **https://cookbook.markcheli.com** - Cookbook app (public recipes; Google SSO for lists, products, AI)
- **https://cookbook-demo.markcheli.com** - Cookbook public demo (read-only, made-up data)
- **https://flask.markcheli.com** - Flask API
- **https://videos.markcheli.com** - Plex Media Server (streaming movies, TV, music)
- **https://files.markcheli.com** - Seafile file sync and share
- **https://home.markcheli.com** - Home Assistant smart home platform (runs on its own box; nginx proxies it)
- **https://money.markcheli.com** - Tallied personal finance dashboard (Google SSO)
- **https://money-demo.markcheli.com** - Tallied public demo (read-only, made-up data)
- **https://tasks.markcheli.com** - Tasks cycle-based todo app (Google SSO); **https://tasks.markcheli.com/mcp** is the Tasks MCP connector (OAuth)
- **https://tasks-demo.markcheli.com** - Tasks public demo (read-only, made-up data)
- **https://knowledge.markcheli.com** - Knowledge, web reader + editor for the AI Context notes vault (Google SSO, owner + allowlist; edits go through basic-memory, the vault mount stays read-only)
- **https://mcp.markcheli.com/mcp** - homelab-mcp claude.ai connector (OAuth required; read-only Seafile AI Context library (backup copy), basic-memory notes read + write/edit, optional Mac mini session bus + read-only live iMessage tools)
- **https://ntfy.markcheli.com** - ntfy push alerts (deny-all; publish token `NTFY_PUBLISH_TOKEN` in `.env`)
- **https://status.markcheli.com** - Uptime Kuma status page
- **minecraft.markcheli.com:25565** - Minecraft server (DNS-only record, straight to the host)
- **ARK: Survival Ascended** - port 7777/udp on the public IP (no hostname)

### LAN-Only Services (HTTPS with Let's Encrypt)

> ⚠️ **"LAN-only" is DNS/proxy convention, NOT enforced isolation.** `*.ops`
> hostnames resolve to the LAN IP and are not Cloudflare-proxied, but the
> underlying container/host ports bind to `0.0.0.0` (all interfaces), e.g.
> OpenSearch `9200/9300`, Postgres `5432`, Grafana `3000`. Actual reachability
> depends entirely on router NAT + host firewall. Do not assume these are
> unreachable. The `*.ops` vhosts share nginx's public :443 listener, so every
> `*.ops` server block MUST carry `allow 192.168.1.0/24; deny all;` (enforced
> since 2026-10-18). Security backlog: **`docs/SECURITY_PLAN.md`**.

- **https://dashboard.ops.markcheli.com** - Grafana dashboards (user `admin`, password in `.env` as `GRAFANA_ADMIN_PASSWORD`; rotated 2026-10-18, compose refuses to start without it)
- **https://prometheus.ops.markcheli.com** - Prometheus metrics
- **https://cadvisor.ops.markcheli.com** - Container monitoring
- **https://logs.ops.markcheli.com** - OpenSearch Dashboards
- **https://opensearch.ops.markcheli.com** - OpenSearch API
- **https://report.ops.markcheli.com** - Daily report HTML preview + ad-hoc trigger API (LAN-only, bearer token required for `/trigger`)
- **https://deptrack.ops.markcheli.com** - Dependency-Track (own login: admin password in 1Password; scanner key `DT_API_KEY` in `.env`)
- **https://energy.ops.markcheli.com** - Energy monitor panel tool (no login of its own)
- **https://openclaw.ops.markcheli.com** - OpenClaw control UI
- **https://memory.ops.markcheli.com/mcp** - basic-memory MCP (admits only the Mac mini, 192.168.1.161)

### NGINX Routing
All HTTPS traffic is handled by NGINX:
- **All routes**: Defined in `infrastructure/nginx/conf.d/production.conf`, public and `*.ops` LAN vhosts alike (there is no separate `local.conf`; every `*.ops` server block carries `allow 192.168.1.0/24; deny all;`)
- `conf.d/production.conf.full` and `default.conf.disabled` are not loaded (nginx only includes `conf.d/*.conf`)
- **SSL certificates**: Located in `infrastructure/nginx/certs/` (keys and the Let's Encrypt files are gitignored; see below)

---

## 🔐 SSL Certificate Management

Three certificates are in use (check with `grep -h ssl_certificate infrastructure/nginx/conf.d/production.conf | sort | uniq -c`):

| Certificate | Used by | Issuer | Expires | Renewal |
|---|---|---|---|---|
| `wildcard-markcheli.crt/.key` | every public `*.markcheli.com` vhost | Cloudflare Origin CA | 2040 | by hand, every 15 years |
| `letsencrypt-ops-markcheli.crt/.key` | every `*.ops.markcheli.com` vhost | Let's Encrypt | 90 days | automatic, cron 03:00 UTC |
| `letsencrypt-status.crt/.key` | `status.markcheli.com` | Let's Encrypt | 90 days | automatic, same job |

`wildcard-ops-markcheli.crt` (a Cloudflare Origin certificate for `*.ops`) is still on disk but no vhost uses it: `*.ops` names are not proxied by Cloudflare, so browsers need a publicly trusted certificate. Expiry of every configured certificate is watched by the Grafana rule `hl-cert-expiry` (under 14 days).

### Cloudflare Origin Certificates (public sites)
**Benefits**:
- ✅ **15-year validity** (expires 2040) - no 90-day renewals
- ✅ **Automatic HTTPS** - Cloudflare handles public SSL
- ✅ **Origin protection** - Certificates only work through Cloudflare proxy

**Renewal (2039-2040)**: create a new Origin Certificate for `*.markcheli.com` in the Cloudflare dashboard (SSL/TLS → Origin Server), then:
```bash
cp new-certs/wildcard-markcheli.crt new-certs/wildcard-markcheli.key infrastructure/nginx/certs/
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```
(The old API script, `cloudflare_ssl_manager.py`, is in `scripts/archive/` and is not maintained.)

### Let's Encrypt (`*.ops` and status)
`scripts/renew-letsencrypt-certs.sh` runs certbot with the Cloudflare DNS-01 plugin (credentials in `~/.secrets/cloudflare.ini` on the server), copies the renewed files into `infrastructure/nginx/certs/`, tests and reloads nginx. A failure writes a `renew_failed` document that the OpenSearch monitor `letsencrypt-renew-failed` pages on, and the cron wrapper pushes too. Setup and manual runs: `docs/LETSENCRYPT_LOCAL_SSL.md`

### Cloudflare SSL Mode
**Required Setting**: "Full (Strict)" mode in Cloudflare dashboard
- Ensures end-to-end encryption
- Validates origin certificates
- Prevents SSL errors

---

## 🌐 DNS Management with Cloudflare

### DNS Configuration
DNS records can be managed two ways: via the Cloudflare Dashboard (for one-offs / proxied flag changes) or via `scripts/cloudflare_dns_manager.py` (preferred for adding LAN-only `*.ops.markcheli.com` records — the script defaults to `proxied: false`, which matches the existing LAN pattern).

**Public Services** (proxied through Cloudflare, A record → `173.48.155.66`, the public IP):
- `www`, `flask`, `videos`, `files`, `home`, `knowledge`, `mcp`, `ntfy`, `status`
- `cookbook`, `cookbook-demo`, `money`, `money-demo`, `tasks`, `tasks-demo`

**DNS-only (not proxied)**:
- `minecraft.markcheli.com` → A record → `173.48.155.66` (Cloudflare can't proxy the Minecraft protocol)

**LAN Services** (DNS-only, not proxied):
- `*.ops.markcheli.com` → A record → `192.168.1.179` (LAN IP)
- Used for internal services like Grafana (dashboard.ops), Prometheus, etc.

### DNS Management Scripts
```bash
# View current DNS records
python scripts/cloudflare_dns_manager.py list

# Add new DNS record (creates as DNS-only / unproxied — fine for *.ops.markcheli.com)
python scripts/cloudflare_dns_manager.py create --domain markcheli.com --type A --name <fqdn> --content <ip> --ttl 300

# Delete DNS record — the `delete` action is registered in argparse but has no handler in main();
# delete via the Cloudflare Dashboard or extend the script if needed.
```

### DNS Troubleshooting
```bash
# Check DNS resolution
dig www.markcheli.com +short

# Check from specific DNS server
dig @1.1.1.1 www.markcheli.com +short

# Verify SSL certificate
openssl s_client -connect www.markcheli.com:443 -servername www.markcheli.com
```

---

## 📊 Monitoring with Prometheus & Grafana

### Access Monitoring Dashboards
**Grafana**: https://dashboard.ops.markcheli.com
- **Login**: admin / `GRAFANA_ADMIN_PASSWORD` from `.env`
- **Pre-configured datasource**: Prometheus
- **Provisioned dashboards** (`infrastructure/monitoring/grafana/provisioning/dashboards/`): Infrastructure Overview, System Metrics, Docker Containers, Containers — Glance, Docker Services, NGINX, Dependency-Track trend
- **Alert rules** (`provisioning/alerting/`): target down, disk, memory, restart loops, stale backup, certificate expiry, UPS on battery → ntfy

**Prometheus**: https://prometheus.ops.markcheli.com
- Query interface for metrics
- 30-day retention policy

**cAdvisor**: https://cadvisor.ops.markcheli.com
- Real-time container resource monitoring
- Per-container CPU/memory/network stats

Logs, log dashboards and every alert route: **`docs/OBSERVABILITY.md`**.

### Key Metrics Monitored
- **CPU usage** per container and total system
- **Memory usage** per container and total system
- **Network I/O** per container
- **Disk I/O** and usage
- **Container health** and restart counts

### Useful Prometheus Queries
```promql
# Container CPU usage (% of total system)
rate(container_cpu_usage_seconds_total{name!=""}[1m]) / scalar(count(count(node_cpu_seconds_total) by (cpu))) * 100

# Container memory usage (GB)
container_memory_usage_bytes{name!=""} / 1024 / 1024 / 1024

# System CPU usage (%)
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

---

## 🔧 Common Operations

### Add New Service
1. **Create service directory**:
   ```bash
   mkdir -p infrastructure/<service>
   ```

2. **Create docker-compose.yml**:
   ```yaml
   services:
     <service>:
       image: <image>
       container_name: <service>
       networks:
         - app-network
       # ... other config
   ```

3. **Add to main docker-compose.yml** (usual) and deploy with the production files, or deploy standalone:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d <service>
   docker compose -f infrastructure/<service>/docker-compose.yml up -d   # standalone
   ```

4. **Add NGINX routing** (if web service):
   - Edit `infrastructure/nginx/conf.d/production.conf` (public and `*.ops` vhosts both live here)
   - Add upstream and server block
   - Reload NGINX: `docker compose exec nginx nginx -s reload`

5. **Add DNS record** in Cloudflare dashboard (or `scripts/cloudflare_dns_manager.py create` for a LAN-only `*.ops` name)
6. **Add an Uptime Kuma monitor** (`scripts/setup_uptime_kuma.py`) and, if it keeps data, add it to `scripts/backup.sh`

### Update Service Configuration
1. **Edit configuration files** (docker-compose.yml, .env, etc.)
2. **Recreate service**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d <service>
   ```
3. **Verify**:
   ```bash
   docker ps | grep <service>
   docker compose logs <service>
   ```

### Troubleshoot Service Issues
```bash
# Check container status
docker ps -a | grep <service>

# View recent logs
docker compose logs --tail 50 <service>

# Check container resource usage
docker stats <service>

# Inspect container details
docker inspect <service>

# Get shell access to container
docker exec -it <service> /bin/bash  # or /bin/sh

# Restart problematic service
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart <service>
```

### NGINX Configuration Changes
```bash
# Test NGINX configuration
docker compose exec nginx nginx -t

# Reload NGINX (without downtime)
docker compose exec nginx nginx -s reload

# View NGINX error logs
docker compose logs nginx

# Check NGINX routing
docker compose exec nginx cat /etc/nginx/conf.d/production.conf
```

---

## 🚨 Critical Rules for Claude Code

### NEVER Do These
1. **NEVER** commit without running tests
2. **NEVER** ignore or dismiss 4XX/5XX HTTP errors as "expected"
3. **NEVER** delete Docker volumes without verified backups
4. **NEVER** modify production configs without testing locally first
5. **NEVER** assume services are working - always verify

### ALWAYS Do These
1. **ALWAYS** use `docker compose -f docker-compose.yml -f docker-compose.prod.yml` (or the Makefile) for deployment
2. **ALWAYS** test configuration changes with `nginx -t` before reloading
3. **ALWAYS** check logs after deployment changes
4. **ALWAYS** verify services return HTTP 200 or proper redirects
5. **ALWAYS** run health checks after changes
6. **ALWAYS** investigate 4XX/5XX errors immediately
7. **ALWAYS** create backups before destructive operations
8. **ALWAYS** update `scripts/README.md` when adding or significantly modifying scripts

### Pre-Commit Checklist
```bash
# 1. Verify all services are running
docker ps

# 2. Test service health
curl -I https://www.markcheli.com
curl -I https://flask.markcheli.com
docker exec prometheus wget -qO- http://localhost:9090/-/healthy  # Prometheus (port not published)

# 3. Check for errors in logs
docker compose logs --tail 100 | grep -i error

# 4. Verify NGINX config is valid
docker compose exec nginx nginx -t

# 5. Run infrastructure tests (if available)
python scripts/test_infrastructure.py

# 6. Compose files still parse (on the server)
docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q
```

---

## 🚨 HTTP Status Code Standards

### Acceptable Responses
- **HTTP 200**: Service functioning correctly ✅
- **HTTP 301/302**: Proper redirects (HTTP→HTTPS) ✅

### Unacceptable Responses (Must Investigate)
- **HTTP 401**: Authentication problems ❌
- **HTTP 403**: Authorization problems ❌
- **HTTP 404**: Missing resources or routing issues ❌
- **HTTP 500+**: Server errors ❌

### Investigation Process
When encountering 4XX/5XX errors:

1. **Do NOT dismiss the error**
2. **Check container health**: `docker ps`
3. **View container logs**: `docker compose logs <service>`
4. **Verify NGINX routing**: Check conf.d files
5. **Test internal connectivity**: `docker exec nginx curl http://<service>:<port>`
6. **Fix the underlying issue**
7. **Re-test to confirm resolution**

---

## 🚨 Surgical Change Protocol

### Change Classification

**🟢 LEVEL 1: Configuration File Changes (90% of requests)**
- **Examples**: Add NGINX route, update environment variable
- **Method**: Edit file, reload service
- **Tools**: Direct file editing, `docker compose exec`
- **Time**: 1-3 minutes

**🟡 LEVEL 2: Container Updates (8% of requests)**
- **Examples**: Update single service, change image version
- **Method**: `docker compose up -d <service>`
- **Time**: 5-10 minutes

**🔴 LEVEL 3: Infrastructure Changes (2% of requests)**
- **Examples**: Add new service, major version upgrades
- **Method**: Full testing, staged rollout
- **Requires**: User approval + backup plan
- **Time**: 15+ minutes

### Minimal Change Principle

**For simple config changes (NGINX routing, env vars)**:
```bash
# ✅ CORRECT: Edit and reload
vim infrastructure/nginx/conf.d/production.conf
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
# Test: curl -I https://new-service.markcheli.com
```

**❌ WRONG: Rebuild everything**:
```bash
# DON'T DO THIS for simple changes
docker compose down
docker compose up -d --build
```

### Pre-Change Checklist
1. **Identify change level** (1, 2, or 3)
2. **Save current state** (git commit or backup)
3. **Plan rollback** (know how to undo)
4. **Make minimal change** (only what's needed)
5. **Test immediately** (verify change works)

---

## 📁 File Structure

```
~/83rr-poweredge/
├── docker-compose.yml              # Base service definitions
├── docker-compose.prod.yml         # Production overrides (always pass with the base file)
├── docker-compose.override.yml     # Local development overrides (never on the server)
├── Makefile                       # Common operations (make help)
├── .env                           # Environment variables (gitignored; .env.example lists them)
├── CLAUDE.md                      # This document
├── README.md                      # Project overview
├── docs/                          # Runbooks: OBSERVABILITY, BACKUP_RESTORE, SECURITY_PLAN, upgrades...
│
├── infrastructure/
│   ├── nginx/                     # NGINX reverse proxy (Dockerfile, conf.d/, certs/)
│   ├── ai-context/                # basic-memory + Obsidian sync (standalone compose)
│   ├── asa/                       # ARK server config template
│   ├── cron/                      # Server crontab (source of truth)
│   ├── dependency-track/          # Dependency-Track config
│   ├── fail2ban/                  # Host fail2ban jails and filters
│   ├── fluent-bit/                # Log shipper to OpenSearch
│   ├── homelab-mcp/               # claude.ai connector (built locally)
│   ├── logrotate/                 # Host logrotate config
│   ├── minecraft/                 # Minecraft server
│   ├── monitoring/                # Prometheus/Grafana (dashboards, alert rules)
│   ├── ntfy/                      # ntfy server config, Kuma wiring
│   ├── nut/                       # UPS shutdown (host config)
│   ├── openclaw/                  # OpenClaw (standalone compose)
│   ├── opensearch/                # Index template, pipeline, ISM, monitors, saved objects
│   └── systemd/                   # Docker waits for /storage
│   (no local dirs for: personal-website, flask-api, cookbook, tallied, tasks, knowledge,
│    daily-report, energy-monitor, house-transcriber — image-only, defined in docker-compose.yml)
│
└── scripts/
    ├── README.md                         # Script documentation (update this when modifying scripts!)
    ├── test_infrastructure.py            # ⭐ Main testing script
    ├── quick_service_test.py            # 🚀 Quick health checks
    ├── infrastructure_manager.py        # 🏗️ Deployment controller
    ├── cookbook-deploy.sh, tasks-deploy.sh  # 🏗️ App deploys with backup + checks
    ├── backup.sh                        # Nightly NAS backup
    ├── cron-notify.sh                   # Cron wrapper: failures → ntfy, results → Grafana
    ├── cloudflare_dns_manager.py        # 🌐 DNS management
    ├── cloudflare_cache_purge.py        # 🌐 Cache purge (make deploy / purge-cache)
    ├── logq.sh                          # 📊 Read-only OpenSearch log queries
    ├── opensearch_diagnostic.py         # 📊 Log diagnostics
    ├── renew-letsencrypt-certs.sh       # 🔐 Let's Encrypt renewal (cron)
    ├── ha-auto-update.py                # Home Assistant auto-update (cron)
    ├── ssh_manager.py                   # ⚠️ Emergency SSH
    ├── ai-context/                      # AI Context vault jobs (autocommit, Seafile backup push)
    ├── one-time/                        # One-time setup scripts
    └── archive/                         # Obsolete/migration scripts
```

---

## 📜 Script Management Protocol

**IMPORTANT:** Claude Code must maintain `scripts/README.md` whenever scripts are modified.

### When to Update scripts/README.md

Update `scripts/README.md` when:
1. **Adding a new script** to the `scripts/` directory
2. **Significantly modifying** an existing script (functionality changes, not just bug fixes)
3. **Archiving a script** (move to `scripts/archive/`)
4. **Changing script usage patterns** or command-line interfaces

### What to Update

When updating scripts/README.md:
- Add/modify the relevant script section with:
  - Purpose and description
  - File size and language
  - Usage examples with actual commands
  - When to use / when not to use
  - Integration points with other scripts
- Update the "Last Updated" timestamp
- Maintain consistent formatting with existing entries
- Keep emoji indicators (⭐ PRIMARY, 🚀 QUICK, etc.)

### Update Format

```markdown
### N. `script_name.py` 🔧 PURPOSE TAG
**Purpose:** Brief one-line description
**Size:** XXkB
**Language:** Python 3

**Description:**
Detailed explanation of what this script does.

**Usage:**
\`\`\`bash
source venv/bin/activate
python scripts/script_name.py [options]
\`\`\`

**When to Use:**
- Bullet points

**Referenced in:** CLAUDE.md, README.md, etc.
```

### Script Categories

- ⭐ PRIMARY - Main infrastructure scripts (testing, deployment)
- 🚀 QUICK - Fast validation/checks
- 🏗️ DEPLOYMENT - Infrastructure deployment
- 🌐 DNS - DNS management
- 📊 DIAGNOSTICS - Troubleshooting and logs
- 🔐 SECURITY - SSL/TLS management
- ⚠️ EMERGENCY - Emergency/fallback tools

---

## 🎯 Success Criteria

Infrastructure is considered healthy when:
1. ✅ All services show as "Up" in `docker ps`
2. ✅ All public services return HTTP 200 or proper redirects
3. ✅ NGINX config passes validation: `nginx -t`
4. ✅ Monitoring dashboards are accessible (Grafana, Prometheus)
5. ✅ Minecraft server responds on port 25565, and https://status.markcheli.com shows everything up
6. ✅ All Prometheus targets are "up" (prometheus, cadvisor, node-exporter, nginx-exporter)
7. ✅ Logs appearing in OpenSearch (via Fluent Bit)
8. ✅ No error messages in recent logs (`docker compose logs`)

---

## 🚀 Quick Reference Commands

### Makefile Commands (Recommended)
```bash
make help              # Show all available commands
make up                # Start all services (production)
make down              # Stop all services
make status            # Show container status
make health            # Run health checks on all services
make logs              # Follow all logs
make logs s=nginx      # Follow specific service logs
make restart s=nginx   # Restart specific service
make nginx-test        # Test NGINX configuration
make nginx-reload      # Reload NGINX configuration
make build s=NAME      # Build specific service
make deploy s=NAME     # Pull + recreate one service, purge its Cloudflare cache
```

### Direct Docker Compose Commands
```bash
# Deploy everything
cd ~/83rr-poweredge
DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$DC up -d

# Check status
docker ps

# View logs
docker compose logs -f <service>

# Restart service
$DC restart <service>

# Reload NGINX config
docker compose exec nginx nginx -s reload

# Test NGINX config
docker compose exec nginx nginx -t

# Health check
curl -I https://www.markcheli.com
docker exec prometheus wget -qO- http://localhost:9090/-/healthy  # Prometheus (port not published)

# Clean up unused resources
docker system prune -a --volumes  # ⚠️  DANGER: removes unused data
```

---

## 🔑 Environment Configuration

Required variables in `.env`:
```bash
# Cloudflare (for DNS and SSL management)
CLOUDFLARE_API_TOKEN=your_token_here
CLOUDFLARE_ZONE_ID=your_zone_id_here
CLOUDFLARE_EMAIL=your_email@example.com

# Optional: Service-specific configurations
# See infrastructure/<service>/.env files for service-specific vars
```

---

## 📖 Additional Documentation

- **docs/OBSERVABILITY.md** - Logs, metrics, dashboards and every alert route (ntfy)
- **docs/BACKUP_RESTORE.md** - What the nightly backup covers and how to restore
- **docs/SECURITY_PLAN.md** - Security backlog
- **infrastructure/cron/README.md** - The server crontab and how to install it
- **infrastructure/nut/README.md** - UPS shutdown and power restore
- **docs/DEPLOYMENT_STATUS.md** - Older deployment notes (history)
- **Makefile** - Run `make help` for available commands
- **infrastructure/nginx/README.md** - NGINX configuration guide
- **infrastructure/monitoring/README.md** - Prometheus/Grafana monitoring guide
- **infrastructure/fluent-bit/README.md** - Fluent Bit log shipping guide
- **scripts/README.md** - Python script documentation

---

**Last Updated**: November 25, 2026
**Architecture Version**: Phase 6 (NGINX + Cloudflare + Docker Compose)
**Status**: Production-ready, all services operational
