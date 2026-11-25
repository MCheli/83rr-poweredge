# Infrastructure Scripts Documentation

This directory contains all active infrastructure management scripts for the 83RR PowerEdge homelab.

**Last Updated:** November 25, 2026
**Infrastructure Version:** Phase 6 (NGINX + Cloudflare + Docker Compose)
**Architecture:** Local execution (Docker Compose + Makefile)

---

## 📋 Active Scripts

### 1. `test_infrastructure.py` ⭐ PRIMARY TESTING
**Purpose:** Comprehensive infrastructure health testing
**Size:** 28KB
**Language:** Python 3

**Description:**
Main testing script that validates all infrastructure components. Should be run before every git commit to ensure system health.

**Tests Performed:**
- DNS resolution for every public and `*.ops` hostname; `*.ops` records must point at `LOCAL_IP` (.env)
- Docker container status for all compose services (+ `healthy` where a healthcheck exists)
- OpenSearch cluster health, log indices, today's log ingestion
- SSL certificate validation, HTTP status, expected content and response time for public services (website, flask, cookbook, plex, seafile + `/notification/ping`, home assistant, tallied/tasks `/api/health`, uptime-kuma status page) and LAN services (grafana, daily-report, energy-monitor, openclaw)
- nginx basic-auth gate (`auth_basic "Ops Services"`) on logs/opensearch/prometheus/cadvisor `.ops` vhosts: without credentials, PASS only on a genuine nginx `401` + `WWW-Authenticate: Basic realm="Ops Services"` (labelled "Auth-gated"); set `OPS_BASIC_AUTH_USER` / `OPS_BASIC_AUTH_PASSWORD` in `.env` to test the upstreams end-to-end (expects 200 + content)
- Minecraft server TCP connection
- Backups: NAS mounted at `/mnt/nas` (WARN) and last `backup-heartbeat` from `backup.sh` in OpenSearch within 26h (FAIL otherwise)
- Git working tree / sync status

**Usage:**
```bash
source venv/bin/activate
python scripts/test_infrastructure.py
```

**Expected Results:**
- 0 failures; warnings only for uncommitted changes or a transiently unmounted NAS
- All critical services return HTTP 200 or proper redirects
- NO unexplained 4XX errors (the only accepted 401 is the verified nginx "Ops Services" gate)

**Referenced in:** CLAUDE.md (pre-commit checklist)

---

### 2. `quick_service_test.py` 🚀 QUICK VALIDATION
**Purpose:** Fast service health checks
**Size:** 2.0KB
**Language:** Python 3

**Description:**
Lightweight alternative to full test suite. Quick validation of critical services for rapid feedback during development.

**Tests:**
- Public services (www, flask, minecraft)
- LAN services (grafana, prometheus, logs, opensearch)
- Basic HTTP response codes

**Usage:**
```bash
source venv/bin/activate
python scripts/quick_service_test.py
```

**Use When:**
- Making small changes and need quick validation
- Don't need comprehensive testing
- Want fast feedback loop

---

### 3. `infrastructure_manager.py` 🏗️ DEPLOYMENT CONTROLLER
**Purpose:** Native Docker Compose infrastructure management
**Size:** 15KB
**Language:** Python 3

**Description:**
Master controller for infrastructure deployment using native Docker Compose (no Portainer dependency).

**Features:**
- Environment-aware deployment (development vs production)
- Auto-build and push for production deployments
- Health monitoring and validation
- Service availability testing
- Comprehensive logging

**Usage:**
```bash
source venv/bin/activate

# Deploy all services
python scripts/infrastructure_manager.py deploy-all

# Deploy specific service
python scripts/infrastructure_manager.py deploy <service_name>

# Health check all services
python scripts/infrastructure_manager.py health-check-all

# Run full tests
python scripts/infrastructure_manager.py run-tests
```

**Key Commands:**
- `deploy-all` - Deploy entire infrastructure
- `deploy <service>` - Deploy specific service
- `health-check-all` - Check health of all services
- `run-tests` - Run comprehensive test suite
- `logs recent` - View recent container logs
- `logs errors` - View error logs

---

### 4. `cloudflare_dns_manager.py` 🌐 DNS MANAGEMENT
**Purpose:** Cloudflare DNS record management
**Size:** 18KB
**Language:** Python 3

**Description:**
Manages DNS records in Cloudflare for both public and LAN services.

**Features:**
- List all DNS records
- Add new DNS records
- Delete DNS records
- Update existing records
- Audit current DNS configuration

**Usage:**
```bash
source venv/bin/activate

# List all DNS records
python scripts/cloudflare_dns_manager.py list

# Add A record
python scripts/cloudflare_dns_manager.py add <subdomain> <ip_address>

# Delete record
python scripts/cloudflare_dns_manager.py delete <subdomain>

# Audit configuration
python scripts/cloudflare_dns_manager.py audit
```

**Environment Variables Required:**
- `CLOUDFLARE_API_TOKEN` - Cloudflare API token with DNS edit permissions
- `CLOUDFLARE_ZONE_ID` - Zone ID for markcheli.com

**Referenced in:** CLAUDE.md (DNS management section)

---

### 5. `opensearch_diagnostic.py` 📊 LOG DIAGNOSTICS
**Purpose:** OpenSearch cluster diagnostics and log analysis
**Size:** 11KB
**Language:** Python 3

**Description:**
Diagnostic tool for OpenSearch logging infrastructure. Runs locally using direct Docker commands (no SSH required).

**Features:**
- Cluster health monitoring
- Index listing and statistics
- Log searching with filters
- Recent log retrieval
- Error log analysis
- Test log injection

**Usage:**
```bash
source venv/bin/activate

# Check cluster health
python scripts/opensearch_diagnostic.py health

# List indices
python scripts/opensearch_diagnostic.py indices

# View recent logs (last hour)
python scripts/opensearch_diagnostic.py recent

# View recent logs (custom time)
python scripts/opensearch_diagnostic.py recent --hours 24

# Search for errors
python scripts/opensearch_diagnostic.py errors --hours 6

# Search for specific term
python scripts/opensearch_diagnostic.py search "connection failed"

# Add test log entry
python scripts/opensearch_diagnostic.py test-log
```

**Integration:**
- Can be called via `infrastructure_manager.py logs` commands
- Provides centralized log access across all containers

---

### 6. `renew-letsencrypt-certs.sh` 🔐 SSL RENEWAL
**Purpose:** Automated Let's Encrypt certificate renewal
**Size:** 1.2KB
**Language:** Bash

**Description:**
Automated renewal script for Let's Encrypt wildcard certificates (*.ops.markcheli.com). Configured to run via cron.

**What It Does:**
1. Runs `certbot renew` with Cloudflare DNS plugin
2. Copies renewed certificates to NGINX cert directory
3. Reloads NGINX to apply new certificates
4. Logs all operations

**Cron Schedule:**
```cron
0 3 * * * /home/mcheli/83rr-poweredge/scripts/renew-letsencrypt-certs.sh >> /var/log/letsencrypt-renewal.log 2>&1
```

**Manual Execution:**
```bash
./scripts/renew-letsencrypt-certs.sh
```

**Certificates Managed:**
- `*.ops.markcheli.com` - Wildcard for LAN services
- Auto-renews 30 days before expiration
- No manual intervention required

**Note:** Public services (*.markcheli.com) use Cloudflare Origin Certificates (15-year validity, no renewal needed)

---

### 7. `ssh_manager.py` ⚠️ ARCHIVED / EMERGENCY ONLY
**Purpose:** Emergency SSH operations (DEPRECATED - SSH no longer required)
**Size:** 3.7KB
**Language:** Python 3

**Description:**
Legacy SSH tool. **DEPRECATED:** All scripts now run locally without SSH. Keep for emergency remote troubleshooting only.

**Features:**
- Single SSH command execution
- Multiple command batching
- Session management
- Connection pooling

**Usage:**
```bash
source venv/bin/activate

# Single command
python scripts/ssh_manager.py run "docker ps"

# Multiple commands
python scripts/ssh_manager.py batch "docker ps" "docker stats --no-stream"
```

**When to Use:**
- Docker daemon issues
- Container accessibility problems
- Network troubleshooting
- System-level diagnostics

**When NOT to Use:**
- Normal deployments (use `docker compose` instead)
- Regular management (use `infrastructure_manager.py`)
- Log viewing (use `opensearch_diagnostic_ssh.py`)

**Note:** This is a fallback tool. Primary operations should use Docker Compose directly.

---

### 8. `emit_security_telemetry.sh` 🔐 SECURITY TELEMETRY

**Purpose:** Emit host security signals into OpenSearch for alerting
**Size:** ~3KB
**Language:** Bash

**Description:**
Cron collector (every 10 min, as `mcheli`) that ships two signals into
`logs-homelab-*` so the OpenSearch alerting monitors can fire:
- `security_unexpected_port` — a TCP port is LISTENing that is not in the
  script's `ALLOWED_PORTS` allowlist (rogue/new service, bad container publish).
- `security_external_db_conn` — an ESTABLISHED connection to a sensitive
  backend port (OpenSearch 9200/9300, Postgres 5432, Grafana 3000) from a
  non-loopback, non-docker-bridge peer (firewall/NAT gap or lateral movement).

Read-only (`ss`), no sudo. Uses the same in-container OpenSearch `_doc`
endpoint as `emit_host_metrics.sh` / `backup.sh`. All failures non-fatal.

**Paired monitors** (`infrastructure/opensearch/config/alerting/monitors/`):
`security-unexpected-listen-port.json`, `security-external-db-conn.json`,
`docker-exec-into-sock-container.json` — apply via the loop in
`infrastructure/opensearch/config/alerting/README.md`.

**Usage:**
```bash
# Runs from cron; manual run:
/home/mcheli/83rr-poweredge/scripts/emit_security_telemetry.sh
```

**When to Use:**
- Runs automatically; run manually to seed/test telemetry after changes.

**Maintenance:** when you intentionally add a service/port, add the port to
`ALLOWED_PORTS` or the unexpected-port monitor will alert. Host services in
the list: 3493 (NUT upsd for the NAS's UPS client, since 2026-11-25). 5432
connections are still emitted but `security-external-db-conn` no longer pages
on them (public on purpose for Tallied's `tld_*` roles).

**Referenced in:** CLAUDE.md (security backlog E3)

---

### 9. `alert-test.sh` 🚀 ALERT PATH CHECK

**Purpose:** Prove that OpenSearch alerting and Uptime Kuma can still reach ntfy
**Size:** ~2KB
**Language:** Bash

**Description:**
Sends one test alert through OpenSearch alerting (a one-off monitor run via
`infrastructure/opensearch/config/alerting/wire-ntfy.py --test-only`, the same
path a real alert takes) and one through Uptime Kuma's own ntfy provider
(`infrastructure/ntfy/kuma-ntfy.js test`), then checks that both landed in
ntfy's message cache (topic `homelab`). Prints `ALERT TEST OK` / `ALERT TEST
FAILED` and exits non-zero on failure. Reads no secrets itself. Each run sends
two pushes to Mark's phone.

Exists because alerting silently failed from 2026-09-04 to 2026-10-31 (SendGrid
out of credits) and nothing noticed.

**Usage:**
```bash
~/83rr-poweredge/scripts/alert-test.sh
```

**When to Use:**
- Weekly: the Mac mini's homelab-weekly-check runs it (`act.sh alert-test`).
- After touching ntfy, the `ntfy-homelab` channel, monitors or Kuma notifications.

**Referenced in:** infrastructure/opensearch/config/alerting/README.md

---

### 10. `sbom-scan.sh` 🔐 SBOM / CVE SCAN

**Purpose:** Nightly SBOM of every running container, uploaded to Dependency-Track
**Size:** ~59KB
**Language:** Bash (+ python3 for JSON)

**Description:**
For each running container: resolves image ID, tag and registry digest, makes
a CycloneDX SBOM of that exact image with Syft (`~/.local/bin/syft`), and
uploads it to Dependency-Track as project `<container>`, ONE stable version
`running` (since 2026-11-03; before that one version `<tag>@<digest12>` per
image). Image ref and digest are stored on that version as properties (group
`sbom-scan`) and tags (`digest:<12 hex>`, `image:<ref>`); a container whose
digest matches the stored one is skipped (idempotent). Re-uploading into the
same version keeps findings and analyses of components still in the image, and
DT's portfolio history stays continuous, so its dashboard shows the burn-down.
A package whose version changes is a new component, so the analysed findings
of `running` are snapshotted before each re-upload and replayed after DT has
processed the BOM (kept in `~/.cache/sbom-scan/pending/` for the next run if
it hasn't). Every analysis copy matches the same purl first, then the same
purl at another version: a suppressed NOT_AFFECTED/FALSE_POSITIVE is carried
to the one newer-or-equal build (dpkg / apk / semver order, comment
"re-verify"); downgrades, several candidates and other states are logged as
"needs review" and pushed to ntfy (one push; not with `--no-notify`).
Only `--migrate-stable` moves a container off the old per-digest model (the
nightly run keeps unmigrated containers on it): the old latest version is
cloned to `running`, missing analyses are copied (two-pass, as above)
with `DT_TRIAGE_API_KEY`, and the old versions are deactivated (not deleted;
needs `PORTFOLIO_MANAGEMENT`, else it warns and continues). A re-run finishes
a half-done migration. After each full run it appends DT's current portfolio totals to
`logs/deptrack-metrics.jsonl` and writes `logs/textfile/deptrack.prom` for
node-exporter's textfile collector (Grafana "Dependency-Track trend").
Talks to `deptrack-apiserver` on the docker bridge (no nginx), reads
`DT_API_KEY` / `DT_TRIAGE_API_KEY` / `NTFY_PUBLISH_TOKEN` from `.env`, logs to
`logs/sbom-scan.log`, sends one ntfy push (topic `homelab`) on failure, one when analyses need review and one listing suppressions carried to a newer build (each also logged).
No sudo; needs the docker group.

**Usage:**
```bash
scripts/sbom-scan.sh                  # what cron runs (03:30)
scripts/sbom-scan.sh --dry-run        # list what would be uploaded (GETs only)
scripts/sbom-scan.sh --only plex      # one container
scripts/sbom-scan.sh --force          # re-upload unchanged images too
scripts/sbom-scan.sh --migrate-stable [--dry-run]               # one-time: move every container onto "running" (clone + upload + copy analyses + deactivate old versions)
scripts/sbom-scan.sh --deactivate-superseded-only [--dry-run]   # no scan: deactivate all non-latest versions
scripts/sbom-scan.sh --deactivate-missing [--dry-run]            # no scan: deactivate projects whose container is gone (after removing a service; not in cron)
```

**When to Use:**
- Runs from mcheli's crontab: `30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1`
- Manually after bumping an image, to see its findings before the next night.
- `--migrate-stable` once after deploying the stable-version change (dry run first). Idempotent: containers already on `running` are skipped, analyses are never overwritten. Needs a working `DT_TRIAGE_API_KEY`.
- `--deactivate-missing` once, by hand, after removing a service: sets `active=false` on every version of each `sbom-scan`-tagged project whose name matches no existing container, running or stopped (refuses if `docker ps -a` is empty). If the container returns, the nightly run reactivates its `running` version.

**Referenced in:** docs/dependency-track.md

---

### 11. `install-syft.sh` 🔐 SUPPLY CHAIN

**Purpose:** Install the pinned, verified Syft release used by `sbom-scan.sh`
**Size:** ~4KB
**Language:** Bash

**Description:**
Downloads `syft_<ver>_linux_amd64.tar.gz` and checks it against the sha256
pinned in the script (taken from the release's `checksums.txt` after its
Sigstore signature was verified with cosign). Also checks the published
checksums file agrees, and re-verifies the signature when cosign is
installed. Installs to `~/.local/bin/syft`; no-op if that version is already
there. Trivy is intentionally not used (March 2026 release compromise).

**Usage:**
```bash
scripts/install-syft.sh            # install / no-op
scripts/install-syft.sh --force    # reinstall
```

**When to Use:**
- Once at deploy; again after bumping `SYFT_VERSION` + `SYFT_SHA256` (steps in the script header).

**Referenced in:** docs/dependency-track.md

---

### 12. `deptrack-setup.sh` 🏗️ DEPLOYMENT

**Purpose:** First boot and idempotent configuration of Dependency-Track
**Size:** ~27KB
**Language:** Bash (+ python3 for JSON)

**Description:**
`init-admin` replaces the default admin/admin password with a random one in a
0600 file (for 1Password). `apply` sets the base URL, enables OSV + NVD
(GitHub Advisories only with `DT_GITHUB_TOKEN`) and starts mirrors, stores the
ntfy token as a DT secret, installs the `ntfy` webhook publisher with
`infrastructure/dependency-track/ntfy-template.peb`, creates the alert policy
(CEL: any KEV finding, or HIGH/CRITICAL with EPSS >= 0.1 in an internet-exposed
project, list in `INTERNET_PROJECTS`) and the push rule that fires only on
that policy's violations (created disabled; renames the old severity rule in
place), adds the weekly digest (scheduled `NEW_VULNERABILITIES_SUMMARY` rule,
Saturdays 13:00 UTC), and creates team `sbom-scanner` with an API key written
to `.env` as `DT_API_KEY`. `triage-key` creates team `triage`
(VIEW_PORTFOLIO, VIEW_VULNERABILITY, VULNERABILITY_ANALYSIS) and writes its
key to `.env` as `DT_TRIAGE_API_KEY`. Every step checks state first;
re-running is safe.

**Usage:**
```bash
scripts/deptrack-setup.sh init-admin
scripts/deptrack-setup.sh apply
scripts/deptrack-setup.sh triage-key    # key for the weekly sweep -> DT_TRIAGE_API_KEY
scripts/deptrack-setup.sh status        # mirrors, projects, rules on/off, policy
scripts/deptrack-setup.sh alerts on|off # push rule only; the digest keeps running
scripts/deptrack-setup.sh test-alert    # push + digest test, verified in ntfy's cache
```

**When to Use:**
- Deploy (see the runbook in docs/dependency-track.md), after rotating the ntfy token or scanner key, and after changing which services are internet-exposed (`INTERNET_PROJECTS`).

**Referenced in:** docs/dependency-track.md

---

### 13. `logq.sh` 📊 LOG DIAGNOSTICS
**Purpose:** Read-only OpenSearch log query, built for deploy watches
**Size:** 3KB
**Language:** Bash (needs `jq` on the caller)

**Description:**
Runs one `_search` against `logs-homelab-*` and prints the total hits, the hits per container and the 10 most common messages (digits normalised to `N`). It only reads. OpenSearch runs with the security plugin disabled and doesn't publish 9200 on the host, so the script goes through `docker exec opensearch curl`: directly when it runs on the server, over `ssh 83rr-poweredge` when it runs anywhere else (override the host with `LOGQ_SSH_HOST`).

Arguments are positional: `[query] [hours] [container]`. The query is OpenSearch `query_string` syntax, and the default field is `log`. The special query `errors` (the default) expands to `level:(ERROR OR FATAL OR CRITICAL OR PANIC) OR status:>=500 OR log:(error OR traceback OR exception OR panic)`. That's broad on purpose (it catches the word "error", so seafile-db's "Aborted connection" warnings show up), so scope it to a container or compare against a pre-deploy baseline. `hours` can be fractional (`0.25` = 15 minutes).

Exit codes: `0` = no hits, `1` = hits, `2` = the query or transport failed.

**Usage:**
```bash
scripts/logq.sh                                   # errors, last 1h, all containers
scripts/logq.sh errors 6                          # errors, last 6h
scripts/logq.sh errors 1 tasks                    # errors for one container
scripts/logq.sh 'container_name:nginx AND status:>=500' 24
scripts/logq.sh 'container_name:grafana AND log:"Database locked"' 24

# Deploy watch: non-zero exit means something matched
scripts/logq.sh errors 0.25 tasks || echo "new errors after deploy"
```

**When to Use:**
- After a deploy, to confirm the redeployed container isn't logging new errors
- Quick "is X still happening?" checks across the 90 days of retained logs
- Use `opensearch_diagnostic.py` or OpenSearch Dashboards (logs.ops) for browsing and anything interactive

**Referenced in:** docs/log-noise-2026-11.md, docs/grafana-sqlite-locked.md

### 14. `cookbook-deploy.sh` 🏗️ DEPLOYMENT
**Purpose:** By-hand deploy of the Cookbook app and its public demo, with a backup and checks
**Size:** 2KB
**Language:** Bash (runs on the server)

**Description:**
Dumps `cookbook-db` to `~/cookbook-backups/` (skipped on the first deploy), pulls `ghcr.io/mcheli/cookbook:latest`, creates `cookbook-db`/`cookbook-demo-db` only if missing (`--no-recreate`: it never restarts or upgrades a database), recreates `cookbook` and `cookbook-demo` with `--no-deps` (migrations run in the entrypoint; the demo reseeds Claudius Banks), waits for both health checks, then checks the public URLs: health, auth config, the public recipe count, and that a write to the demo is refused with 403. Uses `docker-compose.yml` + `docker-compose.prod.yml` explicitly, never the dev override file. Same shape as `tasks-deploy.sh`. Watchtower deploys new images on its own; this is the path with checks.

**Usage:**
```bash
ssh 83rr-poweredge 'bash ~/83rr-poweredge/scripts/cookbook-deploy.sh'
```

**When to Use:**
- First deploy of Cookbook 2.0, and any deploy you want verified end to end
- Not needed for routine image updates (Watchtower)

**Referenced in:** github.com/MCheli/cookbook docs/DEPLOYING.md

### 15. `ai-context/seafile-pull.py` 🔄 SEAFILE MIRROR (retired 2026-11-23, kept for roll-back)
**Purpose:** Keep local Markdown folders current from a Seafile library, read-only (the AI Context trial, before the cut-over; since 2026-11-24 the daily work-laptop copy)
**Size:** 12KB
**Language:** Python 3 (stdlib only; runs on the server from cron)

**Description:**
Lists a Seafile library through the `via-repo-token` API with a **read-only library token** (it refuses any other permission), downloads only files whose Seafile file id changed since the last run, keeps the Seafile mtime, and never deletes anything locally. Targets, includes and excludes come from a JSON config kept outside the repo (`/data/ai-context/pull-config.json`; format in the script's docstring). A lock file stops overlapping runs. **Its cron line was commented out at the 2026-11-23 cut-over** (the server folders are the main copy now and Seafile receives pushes, see #17); the script, its config, state and read-only token stay in place for a roll-back. Never run it with `pull-config.json` while the backup push is active: it would overwrite local notes with Seafile's older copies. **Since 2026-11-24 a second config, `pull-work-config.json`, runs daily** and mirrors only Seafile `05-raw/work-laptop` into `/data/ai-context/work-laptop` (outside both vaults; the knowledge app mounts it read-only). Per-target options `redact_names` (no file names in any log line) and `dir_mode` (e.g. `"775"`, applied to every folder after a run) were added for it.

**Usage:**
```bash
python3 scripts/ai-context/seafile-pull.py --config /data/ai-context/pull-config.json [--dry-run] [--target notes] [--max-files N]
# cron (deploy user): */30 * * * *  -> /data/ai-context/logs/seafile-pull.log   (DISABLED since 2026-11-23)
python3 scripts/ai-context/seafile-pull.py --config /data/ai-context/pull-work-config.json
# cron (deploy user): 20 4 * * *    -> /data/ai-context/logs/seafile-pull-work.log
```

**When to Use:**
- `pull-config.json`: only for a roll-back to Seafile as the main copy (infrastructure/ai-context/README.md, "Roll-back"); `--dry-run` first
- `pull-work-config.json`: runs itself daily; run by hand to refresh the work-laptop copy sooner (infrastructure/ai-context/README.md, "Work-laptop copy")

**Referenced in:** infrastructure/ai-context/README.md, CLAUDE.md

---

### 16. `ai-context/git-autocommit.sh` 🔄 LOCAL HISTORY
**Purpose:** Commit whatever changed in the AI Context vault folders (local git), optionally push listed repos
**Size:** 2KB
**Language:** Bash (runs on the server from cron)

**Description:**
For each folder given, `git add -A` and commit as `auto: <timestamp>` when the index differs. Repos listed in `AUTOCOMMIT_PUSH_REPOS` (space-separated paths) are also pushed with `git push -q origin HEAD` whenever the remote is behind: one attempt per run, failures logged, no retries; an `origin` remote and upstream must exist (set up by hand once). Repos not listed are never pushed. Never resets or deletes. The repos are created once by hand (`git init`, author `ai-context-autocommit <noreply@localhost>`, `.gitignore` from `infrastructure/ai-context/vault.gitignore`).

**Usage:**
```bash
AUTOCOMMIT_PUSH_REPOS=/data/ai-context/notes scripts/ai-context/git-autocommit.sh /data/ai-context/notes /data/ai-context/raw
# cron (deploy user): */15 * * * *  -> /data/ai-context/logs/git-autocommit.log
```

**When to Use:**
- Runs itself every 15 minutes; `git -C /data/ai-context/notes log --oneline | head` shows the history

**Referenced in:** infrastructure/ai-context/README.md

---

### 17. `ai-context/seafile-backup-push.py` 🔄 SEAFILE BACKUP
**Purpose:** Push the AI Context vaults on the server into the Seafile "AI Context" library (backup), the reverse of `seafile-pull.py`
**Size:** 14KB
**Language:** Python 3 (stdlib only; runs on the server from cron)

**Description:**
Since the 2026-11-23 cut-over the folders under `/data/ai-context` are the main copy and Seafile only receives. The script lists the library once (`via-repo-token` API, **read-write library token**, refuses a read-only one; token file must be mode 600), then uploads with `replace=1` every local file that changed: per-target state (`size`, `mtime`, `sha256` as last uploaded) decides, files not in the state yet are compared with Seafile's listing (same size and a Seafile mtime at least as new as the local one = in sync, so the first run uploaded only the 2336 notes the front-matter normalisation had changed). It **never deletes or moves anything in Seafile**, hard-refuses any path that would land under `/04-work` or `/05-raw/work-laptop`, skips dot-paths (`.git`, `.obsidian`, `.trash`), everything the vault's `.gitignore` ignores (the secret-flagged raw dumps) and the configured `exclude_names`, and skips files over `max_file_mb` (90, Cloudflare's upload limit) with a log line. **Divergence guard** (`guard_prefixes`, default `/03-diary`): before uploading, every Seafile file under a guarded prefix that is missing on the server, or that Seafile holds in a version this script did not upload (file id ≠ the `remote_id` recorded at upload) and with a newer mtime than the local copy, is logged as `DIVERGED <path>`, never overwritten and never imported; a human resolves it. `--adopt-remote` (once, by hand, when Seafile is known to hold only this script's uploads) records the current Seafile ids for unchanged files that predate the guard. Lock file against overlapping runs. Config outside the repo: `/data/ai-context/push-config.json` (format in the docstring).

**Usage:**
```bash
python3 scripts/ai-context/seafile-backup-push.py --config /data/ai-context/push-config.json [--dry-run] [--target notes|raw] [--max-files N] [--adopt-remote]
# cron (deploy user): */30 * * * *  -> /data/ai-context/logs/seafile-backup-push.log
# check: grep -c " uploaded " /data/ai-context/logs/seafile-backup-push.log ; grep -E "DIVERGED|FAIL|REFUSED|ERROR" ...
```

**When to Use:**
- Runs itself every 30 minutes; `--dry-run` lists what would be uploaded (one line per file)
- After a bulk change in a vault, to see the backup catch up; never together with `seafile-pull.py`

**Referenced in:** infrastructure/ai-context/README.md, CLAUDE.md

---

### 18. `ai-context/bm.py` 🔄 BASIC-MEMORY CLIENT
**Purpose:** Command-line MCP client for basic-memory (the notes vault server), so sessions and scripts can read and write notes without an MCP host
**Size:** 22KB
**Language:** Python 3 (standard library only)

**Description:**
Speaks streamable-HTTP MCP (JSON-RPC over POST, SSE or JSON replies, one session per invocation) to the basic-memory server at `https://memory.ops.markcheli.com/mcp` (`BM_URL` to override, e.g. the container's `http://<ip>:8000/mcp` on the server). Subcommands `tools`, `read`, `search`, `context`, `write`, `edit` map onto the server's `bm_*` tools with their real parameter names (`title`+`directory` or `identifier`, `note_type`, `tags`, `metadata`, `overwrite`, `expected_checksum`; `command` with `append`/`prepend`/`find_replace`/`replace_section`/`insert_before_section`/`insert_after_section`/`set_metadata`), and `call <tool> <json>` reaches any tool. Results are JSON (`--raw` for text). `--transport auto` falls back to the `curl` binary when Python cannot open sockets (the Claude Code sandbox on the Mac mini). Full parameter tables and observed server behaviour (permalink line added, YAML lists re-serialised, final newline dropped, body kept byte for byte): `scripts/ai-context/BM-CLIENT.md`.

**Usage:**
```bash
python3 scripts/ai-context/bm.py tools --names
python3 scripts/ai-context/bm.py read README.md --output-format json
python3 scripts/ai-context/bm.py write --title "Note Title" --folder some/folder --content-file note.md --output-format json
python3 scripts/ai-context/bm.py edit some/note.md --operation set_metadata --metadata '{"updated": "2026-11-23"}' --checksum <from read>
python3 scripts/ai-context/bm.py call bm_man '{"page": "bm_edit"}' --raw
```

**When to Use:**
- Any scripted or shell-driven note write (every AI write goes through basic-memory, never the vault files)
- Checking how the server indexed a note (`context`, `search`) or what a tool accepts (`tools --describe`)

**Referenced in:** infrastructure/ai-context/README.md, scripts/ai-context/BM-CLIENT.md

---

### 19. `ai-context/recent-ai-changes.py` 🔄 AI CHANGE LOG NOTE
**Purpose:** Keep the vault note `maps/Recently changed by AI.md` current: every note written or edited through basic-memory in the last 7 days, grouped by day
**Size:** 10KB
**Language:** Python 3 (standard library only; runs on the server from cron, imports `bm.py` from the same directory)

**Description:**
Opens basic-memory's SQLite index **read-only** (`file:…memory.db?mode=ro`), reads `accepted_project_note_change` (the table where basic-memory logs each write made through its tools: `accepted_at` in UTC, `operation`, `file_path`, `title`), keeps the last `--days` (7), joins the `entity` table for the current title, and groups by day in America/New_York, newest first. Repeated writes of one note on one day collapse into one line with a count (`- 21:49 · [[2021-01-12]] (updated, 5×)`; the ` ·` keeps basic-memory from minting a relation type "21:49" out of the line, it becomes a plain `links_to` edge); when a note's title is not its file name the link is `[[path|Title]]` so Obsidian resolves it; a `bm_move` (operation `moved`, `previous_file_path` set) reads `(moved from <old file name>)` and links the note's current title, so a renamed note is one line. At most `--max-lines` (300) entry lines; the note's own writes are skipped. The note is then written **through basic-memory** (`bm_write` with `overwrite`, using `bm.py`'s client), like every other AI write. `BM_URL` unset means the script asks `docker inspect basic-memory` for the container IP (how cron reaches it on the server); `--dry-run` prints the note instead.

**Usage:**
```bash
python3 scripts/ai-context/recent-ai-changes.py --dry-run                      # on the server: print, write nothing
python3 scripts/ai-context/recent-ai-changes.py [--days 7] [--max-lines 300]     # write maps/Recently changed by AI.md
# cron (deploy user): 7 * * * *  -> /data/ai-context/logs/recent-ai-changes.log
# deploy: cp scripts/ai-context/{recent-ai-changes.py,bm.py} /data/ai-context/bin/
```

**When to Use:**
- Runs itself hourly at :07; read the result with `python3 scripts/ai-context/bm.py --raw read "maps/Recently changed by AI.md"`
- After a bulk writing session, to see what it touched (or `--dry-run --days 1`)

**Referenced in:** infrastructure/ai-context/README.md

---

### 20. `ha-auto-update.py` 🏗️ HOME ASSISTANT AUTO-UPDATE
**Purpose:** Install Home Assistant's own updates (Supervisor, add-ons, HACS, Core, OS) unattended, after a 3-day soak, with a backup and health checks
**Size:** 31KB (+ `test_ha_auto_update.py`, unit tests for the planning logic)
**Language:** Python 3 (standard library only; runs on the server from cron)

**Description:**
Talks to the HA Yellow over the LAN REST API (`HA_URL`, default `http://192.168.1.121:8123`, so restarts don't go through nginx). **Scope** is the `update.*` entities of the `hassio` and `hacs` integrations only (found with the `integration_entities()` template); device firmware (UniFi, ZHA, ESPHome devices, Matter, Synology DSM, the Yellow's radio/board firmware) is never touched. **Hold rules:** a version installs only after it has been offered for 3 days (first-seen times in `~/.cache/ha-auto-update/state.json`; a version the state file hasn't seen is dated from HA's own history, up to 10 days back); Core `X.Y.0` releases are never installed (waits for `X.Y.1`); a version skipped in the HA UI is never installed; nothing is installed while any in-scope update shows *in progress* (someone updating by hand), and one stuck there with no change for 6 h gets a single alert. **Order:** Supervisor → add-ons → HACS → Core → OS, one at a time. Before Core or OS it runs `backup.create_automatic` (Mark's automatic-backup settings: locations, encryption, retention) and waits for it; `update.install` gets `backup: true` where the entity supports it and `version: <soaked version>` where it supports choosing one. **After each install and at the end:** `/api/` answers, `/api/config` is `RUNNING`, `installed_version` is the target, and unavailable entities are not more than 25 (or 10 %) above the pre-run count (waits up to 10 min for them to come back). The first failure stops the run, sends a **priority-5 ntfy push** (topic `homelab`, says whether a backup was made) and files a **Tasks agent item** "Home Assistant auto-update failed: <component>" (personal list, source `ha-auto-update`). It never restores backups (Supervisor already rolls back a Core update that fails to start). Installs that succeed → one priority-2 push listing the versions; nothing installed → silent. Log: `logs/ha-auto-update.log` (no secrets).

**Usage:**
```bash
scripts/ha-auto-update.py --dry-run      # the plan for every in-scope entity, changes nothing
scripts/ha-auto-update.py                # a real run (what cron runs)
scripts/ha-auto-update.py --no-notify    # no ntfy push / Tasks item
python3 scripts/test_ha_auto_update.py   # unit tests
# cron (mcheli, server on UTC; --at-hour keeps only the 04:15 America/New_York firing, DST-proof):
#   15 8,9 * * * /home/mcheli/83rr-poweredge/scripts/ha-auto-update.py --at-hour 4 >/dev/null 2>&1
```
`.env` keys: `HA_AUTO_UPDATE_TOKEN` (1Password Agents "HA agent token"), `HA_AUTO_UPDATE_TASKS_API_KEY` (Agents "Tasks API key"), `NTFY_PUBLISH_TOKEN`; optional `HA_URL`. Copy a key in without printing it: `agent-op read "op://Agents/HA agent token/credential" | ssh 83rr-poweredge '...append to .env...'`.

**When to Use:**
- Runs itself daily at 04:15 ET; `--dry-run` to see what is pending and when each update becomes due
- To hold an update for good: skip that version in the HA UI (Settings → System → Updates → Skip)
- Don't use it for device firmware; those stay manual by design

**Referenced in:** docs/home-assistant-auto-update.md

---

## 📁 Directory Structure

```
scripts/
├── README.md                         # This file (documentation)
├── test_infrastructure.py            # ⭐ Main testing script
├── quick_service_test.py            # 🚀 Quick health checks
├── infrastructure_manager.py        # 🏗️ Deployment controller
├── cloudflare_dns_manager.py        # 🌐 DNS management
├── opensearch_diagnostic_ssh.py     # 📊 Log diagnostics
├── logq.sh                          # 📊 Read-only OpenSearch query (deploy watches)
├── renew-letsencrypt-certs.sh       # 🔐 SSL renewal (automated)
├── alert-test.sh                    # 🚀 Weekly alert path check (ntfy)
├── sbom-scan.sh                     # 🔐 Nightly container SBOMs -> Dependency-Track
├── install-syft.sh                  # 🔐 Pinned, verified Syft install
├── deptrack-setup.sh                # 🏗️ Dependency-Track first boot / config
├── cookbook-deploy.sh               # 🏗️ Cookbook app + demo deploy with checks
├── ha-auto-update.py                # 🏗️ Daily Home Assistant updates (soak, backup, health checks)
├── test_ha_auto_update.py           # Unit tests for ha-auto-update.py
├── ssh_manager.py                   # ⚠️ Emergency SSH
├── ai-context/                      # 🔄 Notes vault: bm.py (basic-memory client) + BM-CLIENT.md, recent-ai-changes.py, git-autocommit.sh, seafile-backup-push.py, seafile-pull.py (retired)
├── one-time/                        # One-time setup scripts
│   ├── README.md
│   ├── setup_data_disk.sh
│   ├── migrate_docker_to_data_disk.sh
│   ├── restart_and_verify_docker.sh
│   ├── cleanup_docker_backup.sh
│   └── seafile_conf_migrate.py      # Seafile 11→12→13 config edits (docs/seafile-upgrade-2026-11.md)
└── archive/                         # Obsolete/migration scripts
    ├── (18 archived scripts from Phase 5 migration)
    └── README.md
```

---

## 🔄 Script Workflow

### Standard Deployment Workflow:
```bash
# 1. Make infrastructure changes
vim docker-compose.yml

# 2. Deploy services
python scripts/infrastructure_manager.py deploy-all

# 3. Run quick validation
python scripts/quick_service_test.py

# 4. Run comprehensive tests
python scripts/test_infrastructure.py

# 5. Commit if tests pass
git add -A && git commit -m "Your changes"
```

### Troubleshooting Workflow:
```bash
# 1. Quick service check
python scripts/quick_service_test.py

# 2. Check container health
python scripts/infrastructure_manager.py health-check-all

# 3. View recent logs
python scripts/infrastructure_manager.py logs recent

# 4. Search for errors
python scripts/infrastructure_manager.py logs errors

# 5. Deep dive with OpenSearch
python scripts/opensearch_diagnostic_ssh.py errors --hours 24
```

---

## 📝 Maintenance Instructions

### Adding a New Script

When adding a new script to this directory:

1. **Create the script** with proper shebang and documentation
2. **Add executable permissions** (if shell script): `chmod +x script_name.sh`
3. **Update this file** (`README.md`) with:
   - Script name and purpose
   - Size and language
   - Comprehensive description
   - Usage examples
   - When to use / when not to use
4. **Update CLAUDE.md** if script changes standard workflows
5. **Add to git**: `git add scripts/script_name.{py,sh} scripts/README.md`
6. **Commit with description**: Explain what the script does and why it's needed

### Modifying an Existing Script

When significantly modifying a script:

1. **Make your changes** to the script
2. **Update this file** (`README.md`) to reflect:
   - New features or functionality
   - Changed usage patterns
   - Updated examples
   - New dependencies or requirements
3. **Test thoroughly**: Run both the script and `test_infrastructure.py`
4. **Update CLAUDE.md** if workflows change
5. **Commit with details**: Explain what changed and why

### Archiving a Script

When a script becomes obsolete:

1. **Move to archive**: `mv scripts/script_name.{py,sh} scripts/archive/`
2. **Update archive/README.md**: Document why it was archived
3. **Remove from this file** (`README.md`)
4. **Update CLAUDE.md**: Remove references to archived script
5. **Commit**: Explain why script is no longer needed

---

## 🎯 Quick Reference

**Makefile Commands (Recommended):**
```bash
make help              # Show all available commands
make up                # Start all services
make status            # Show container status
make health            # Run health checks
make logs s=nginx      # View specific service logs
```

**Before Every Commit:**
```bash
make health
# or: python scripts/test_infrastructure.py
```

**After Infrastructure Changes:**
```bash
make up                # Deploy all services
make health            # Verify health
```

**View Logs:**
```bash
make logs              # All logs
make logs s=grafana    # Specific service
python scripts/opensearch_diagnostic.py recent --hours 24
```

**DNS Changes:**
```bash
python scripts/cloudflare_dns_manager.py list
python scripts/cloudflare_dns_manager.py add <subdomain> <ip>
```

**Emergency Troubleshooting:**
```bash
make status            # Check containers
docker ps -a           # All containers including stopped
python scripts/infrastructure_manager.py health-check-all
```

---

## ⚙️ Environment Setup

All Python scripts require the virtual environment:

```bash
# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

**Required Environment Variables:**
- `CLOUDFLARE_API_TOKEN` - For DNS management
- `CLOUDFLARE_ZONE_ID` - For DNS management
- `SSH_HOST` - Server IP (192.168.1.179)
- `SSH_USER` - Server username (mcheli)

**Load from .env:**
```bash
# .env file in project root is auto-loaded by scripts
cat .env | grep CLOUDFLARE
```

---

## 📚 Related Documentation

- **CLAUDE.md** - Complete infrastructure management guide with SOPs
- **README.md** - Project overview and quick start
- **docs/DEPLOYMENT_STATUS.md** - Current deployment status
- **scripts/one-time/README.md** - One-time setup scripts documentation
- **scripts/archive/README.md** - Archived scripts documentation

---

**🤖 Auto-Update Instruction:**

Claude Code should automatically update this file whenever:
- A new script is added to the `scripts/` directory
- An existing script is significantly modified (functionality changes, not just bug fixes)
- A script is moved to archive
- Script usage patterns change

Update format: Add/modify the relevant section with current information, update "Last Updated" date, maintain consistent formatting with existing entries.
