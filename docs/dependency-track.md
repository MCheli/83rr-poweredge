# Dependency-Track (CVE tracking for what's actually running)

OWASP Dependency-Track **v5** holds a CycloneDX SBOM of every running
container and matches it against mirrored vulnerability data (OSV, NVD,
CISA KEV). Known-exploited (KEV) findings, and HIGH/CRITICAL ones with
EPSS >= 0.1 in an internet-exposed service, are pushed to ntfy the same day;
everything else lands in a weekly digest.
Dependabot and CodeQL only see the code in our repos; this covers the
runtimes and third-party images (Uptime Kuma's Node, openclaw, nginx,
distro packages such as libbrotli, ...).

| | |
|---|---|
| UI | https://deptrack.ops.markcheli.com (LAN only, DT's own login) |
| API | same host, `/api` (the scanner uses the container directly) |
| Containers | `deptrack-apiserver`, `deptrack-frontend`, `deptrack-db` (`docker-compose.yml`) |
| Volumes | `deptrack_db_data` (Postgres 17), `deptrack_data` (`/data`: KEK keyset + file storage) |
| Nightly scan | `scripts/sbom-scan.sh` (cron 03:30, user `mcheli`), log `logs/sbom-scan.log` |
| Setup / config | `scripts/deptrack-setup.sh` |
| Alerts | ntfy topic `homelab`: policy "alert: KEV, or HIGH/CRITICAL with EPSS >= 0.1 on internet-exposed" + rule "ntfy: KEV or high-EPSS on internet-exposed" (push), rule "ntfy: weekly vulnerability digest" (Saturdays) |
| Credentials | admin password in 1Password ("Dependency-Track admin"); `DEPTRACK_DB_PASSWORD`, `DT_API_KEY` (scanner), `DT_TRIAGE_API_KEY` (weekly sweep) in `.env` |

## How it fits together

```
cron 03:30 ─▶ sbom-scan.sh ─┬─ docker ps / inspect      (container → image ID, tag, digest)
                            ├─ syft docker:<image ID>   (CycloneDX SBOM of exactly what runs)
                            └─ POST /api/v1/bom ───────▶ deptrack-apiserver ──▶ deptrack-db
                                                          │  mirrors OSV / NVD / KEV daily
                                                          ├─ alert policy violation ─▶ http://ntfy/ ─▶ phone
                                                          └─ Saturday digest ─────────▶ http://ntfy/ ─▶ phone
LAN browser ─▶ nginx (deptrack.ops) ─┬─ /     ─▶ deptrack-frontend
                                     └─ /api  ─▶ deptrack-apiserver
```

* **No host ports.** nginx reaches both containers on the `infrastructure`
  network; the database is on the internal-only `deptrack` network. The
  vhost carries the usual `allow 192.168.1.0/24; deny all;` and the
  `Content-Encoding: br` 415 rule.
* **Outbound allowlist:** `DT_OUTBOUND_ALLOWED_DESTINATIONS=external,ntfy`, so
  a webhook can only reach the internet or the ntfy container, not the rest
  of the docker network.
* **Pinned images** (version + digest), deliberately **not** watchtower-managed.
  Upgrades run one-way schema migrations: back up `deptrack-db` first and
  read the release notes (`docs/guides/upgrading/` in DependencyTrack/docs).
* **JVM heap:** the apiserver has a 6 GB memory limit; the image sizes the heap
  at 80% of that (~4.8 GB). Raise the limit, not `-Xmx`.
* **Telemetry** submission to the DT project is off.

### Projects and versions

One DT project per **container name** (`tallied`, `tallied-scheduler`, `plex`,
...). The version is `<image tag>@<first 12 hex of the digest>`, e.g.
`17.11-alpine@266d3c257594`, `latest@1111aaaa2222`, or `digest@e0ab27395614`
for digest-only refs. The registry digest is used when there is one, the local
image ID otherwise (locally built images).

* A version that already exists is skipped, so the nightly run only does work
  for containers whose image changed (`--force` re-uploads everything).
* When an image changes, the scanner **clones** the previous latest version
  (components, findings, audit decisions) to the new version and then uploads
  the BOM into the clone. Findings you already have carry over and do **not**
  alert again; only genuinely new ones do. The new version is marked latest.
* After each upload, every other version of that project that isn't latest is
  **deactivated** (`active=false`), not deleted. DT leaves inactive projects
  out of the portfolio metrics, so the totals count only what runs, but their
  findings and audit history stay (UI: project list → *Show inactive*). Each
  change is logged (`deactivated superseded version …`). This needs
  `PORTFOLIO_MANAGEMENT` on the scanner team; without it the scan logs a
  warning, still uploads, and leaves the old versions active.
* Projects of containers that no longer run stay until you delete them in the UI.

Until 2026-11-01 the scanner instead *deleted* versions beyond the newest 2
(`KEEP_VERSIONS=2`). With exactly two versions per container (the old and
the new), nothing was ever beyond 2, so after the 2026-11-01 upgrades 24
superseded versions stayed active and the portfolio totals went **up**
(crit 540 → 740) while what was running went down (540 → 294). Deletion is
gone: deactivating keeps the history and is reversible.

### Supply chain: why Syft is installed the way it is

After the March 2026 Trivy compromise (malicious release binaries), the
scanner itself is treated as a supply-chain risk. **Trivy is not used.**
Syft is installed by `scripts/install-syft.sh` as a **pinned release binary in
`~/.local/bin`**:

* The sha256 of `syft_1.54.1_linux_amd64.tar.gz` is pinned **in this repo**, so
  a later tampered upload to the same GitHub release cannot be installed
  without a reviewed commit.
* Before pinning, the release's `checksums.txt` Sigstore signature was verified
  with cosign (identity `https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main`,
  issuer `https://token.actions.githubusercontent.com`). If cosign is ever
  installed on the server, the script re-verifies it on every install.
* Pick releases at least ~2 weeks old (1.54.1 is from 2026-10-06; 1.55.0 was
  12 days old when this was set up).

A digest-pinned Syft container would also work, but it would need
`/var/run/docker.sock` mounted into another container; the host binary uses
the docker group mcheli already has and adds no new socket mount.

### Vulnerability sources

| Source | State | Notes |
|---|---|---|
| OSV | on | Ecosystems: Alpine, Debian, Ubuntu, npm, PyPI, Go, Maven, crates.io, RubyGems, Packagist, NuGet. Main source for distro and language packages (PURL matching). |
| NVD | on | v5 mirrors the NVD JSON 2.0 **feed files**; there is no API-key setting any more, so no NVD key is needed. NVD matches by CPE, which Syft adds for many packages; expect some noisier CPE matches. |
| GitHub Advisories | off unless `DT_GITHUB_TOKEN` is set | Needs a token (no scopes). OSV already includes GitHub's advisories, so this mostly adds duplicates. |
| CISA KEV | on (DT default) | Marks known-exploited CVEs; such findings alert at any severity and in any project (alert policy). |

## First boot (summary; exact commands in the runbook below)

1. Start the three containers and wait for `deptrack-apiserver` to be healthy
   (first boot runs migrations, 1–3 min).
2. `scripts/deptrack-setup.sh init-admin` replaces the default **admin/admin**
   password with a random one, written to `~/.config/deptrack/admin-password`
   (0600, never printed). **Mark:** store it in 1Password as
   "Dependency-Track admin (deptrack.ops.markcheli.com)", then
   `shred -u ~/.config/deptrack/admin-password`.
3. `scripts/deptrack-setup.sh apply`: base URL, vuln sources + first mirror,
   ntfy secret/publisher, alert policy + push rule (created **off**) and the
   weekly digest rule, team `sbom-scanner` with
   `BOM_UPLOAD, PROJECT_CREATION_UPLOAD, VIEW_PORTFOLIO, PORTFOLIO_MANAGEMENT`
   and its API key written to `.env` as `DT_API_KEY`. (A v4-style team key is
   used on purpose: team keys don't expire, v5 service-account keys expire
   after at most 366 days and would silently break the nightly scan.)
4. Wait for the OSV and NVD mirrors to finish (`deptrack-setup.sh status`).
5. `scripts/install-syft.sh`, then the first `scripts/sbom-scan.sh`.
6. `scripts/deptrack-setup.sh alerts on` and `test-alert`.
7. Install the cron line.

Order matters for steps 4–6: with alerts on during the first scan, every
existing HIGH finding in every container would be pushed to the phone.

## Cron

In mcheli's crontab (after `backup.sh` at 02:00):

```cron
30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1
```

The script logs to `~/83rr-poweredge/logs/sbom-scan.log` itself. On any
failure (syft error, upload error, DT down, rejected key) it sends **one**
ntfy push titled "SBOM scan: N failure(s) of M container(s)" with the first
few errors. A clean run sends nothing.

## Reading the alerts

Alerts arrive in the ntfy app on topic `homelab`, tagged `dependency-track`:

| Push | Meaning | Priority |
|---|---|---|
| `Exploitable: <component> in <container>` | A component now violates the alert policy: it has a KEV finding (any project), or a HIGH/CRITICAL finding with EPSS >= 0.1 in an internet-exposed project. Body: component PURL, policy, project. | 5 |
| `Dependency-Track weekly: N new finding(s) in M project(s)` | Saturday 13:00 UTC digest of everything new that week, by severity (`NEW_VULNERABILITIES_SUMMARY`; skipped when nothing is new). | 2 |

**Why a policy, not a rule filter:** DT 5.2's notification schema has
`is_kev` but no EPSS, so a rule filter can't test EPSS. The CEL policy engine
can (`vulns`, `project`, `v.epss_score`), and it re-evaluates on every BOM
upload: a CVE that is added to KEV, or whose EPSS rises, later still alerts.
Suppressed findings are excluded, so a *Not affected* + suppress analysis
silences a false positive for good. "Internet-exposed" is the
`INTERNET_PROJECTS` list in `scripts/deptrack-setup.sh` (container names with
a public vhost or a forwarded port); re-run `apply` after changing it.
Policies are evaluated per project version, so a container that is still
violating can alert again when its image changes (new version).

Tapping opens the project in the DT UI. What to do:

1. Open the project in DT → *Audit Vulnerabilities*. Check the component and
   whether a fixed version exists.
2. Fix it the usual way: bump the image/digest in `docker-compose.yml`, or
   rebuild our own image (Dependabot/watchtower for ghcr.io images). The next
   nightly scan uploads the new version and the finding disappears from latest.
3. If it doesn't apply (e.g. vulnerable code path not used, disputed CVE),
   record an analysis in DT (*Not affected* + justification, or *Suppress*).
   Analyses carry over to future versions through the clone step.

Silence for a while: `scripts/deptrack-setup.sh alerts off` (and `on` again);
this leaves the weekly digest running.
Sanity check: `scripts/deptrack-setup.sh test-alert` (sends both rules' test
notifications and expects two in ntfy's cache).

## Operations

```bash
scripts/deptrack-setup.sh status          # mirror runs, project count, rules on/off, policy
scripts/deptrack-setup.sh triage-key      # team "triage" key -> DT_TRIAGE_API_KEY in .env (weekly sweep)
scripts/sbom-scan.sh --dry-run            # what tonight's run would upload
scripts/sbom-scan.sh --only uptime-kuma   # re-scan one container now
scripts/sbom-scan.sh --force              # re-upload every container
scripts/sbom-scan.sh --deactivate-superseded-only --dry-run   # list superseded versions (GETs only)
scripts/sbom-scan.sh --deactivate-superseded-only             # deactivate them, no scanning
docker compose logs --tail 100 deptrack-apiserver
docker exec deptrack-apiserver wget -qO- http://127.0.0.1:9000/health/ready
```

* **Image rolled back:** the next scan finds the old version already exists,
  sets it active + latest again and deactivates the newer one (logged as
  `reactivated … as latest`). To reactivate by hand: UI → project →
  *Show inactive* → the version → *Active*.
* **Rotate the scanner key:** delete it in the UI (Administration → Access
  Management → Teams → sbom-scanner), then `deptrack-setup.sh apply` creates a
  new one and rewrites `DT_API_KEY` in `.env`.
* **Rotate the ntfy token:** update `NTFY_PUBLISH_TOKEN` in `.env`, re-run
  `deptrack-setup.sh apply` (updates the DT secret).
* **Upgrade DT:** take a fresh `pg_dump` (`scripts/backup.sh` or the command
  in it), bump both image tags+digests together, `up -d`, watch the logs.
* **Upgrade Syft:** see the header of `scripts/install-syft.sh`.

## Backups

`scripts/backup.sh` dumps the database nightly (`databases/deptrack_<ts>.sql.gz`,
14 kept) and copies the `deptrack_data` volume. Restore both together: the
volume holds the key-encryption key without which secrets stored in the DB
(ntfy token, GitHub token) can't be decrypted. If the volume is lost, restore
the dump anyway and re-run `deptrack-setup.sh apply` to re-enter the secrets.
Restore steps: `docs/BACKUP_RESTORE.md`.

## Remediation 2026-11-01

The first full scan (2026-10-31) found ~3,470 critical/high findings across
the portfolio, most of them in stale third-party images. Changes in this round:

* **Uptime Kuma** moved to the `2.5.9-slim` image: no bundled Chromium (most
  of its findings) or embedded MariaDB. Our monitors are http/docker/gamedig on
  SQLite, so nothing used them.
* **Pinned by version + digest** (were floating tags or older pins): minecraft
  `2026.10.1-java25`, plex `1.43.5.11079`, the five PostgreSQL 16 databases
  `16.15-alpine` (one shared `x-postgres16-image` anchor; same major, no
  dump/restore), ntfy `v2.36.0`, OpenSearch + Dashboards `3.9.0`, Prometheus
  `v3.13.5` (LTS), node-exporter `v1.12.1`, nginx-exporter `1.5.3`, cAdvisor
  `v0.60.6` (now from `ghcr.io/google/cadvisor`), Fluent Bit `5.1.5`.
* **edge-tts / faster-whisper** published on the LAN address (`LOCAL_IP` in
  `.env`) instead of `0.0.0.0`. Both were removed on 2026-11-01 (unused);
  `scripts/sbom-scan.sh --deactivate-missing` deactivated their projects.
* **Alerts:** the push rule no longer fires on every new HIGH/CRITICAL
  finding (about 13 pushes a day); it now fires only on the alert policy
  (above), and a weekly digest covers the rest.
* **`triage-key`** subcommand: a separate team key that can record analyses,
  so the weekly sweep can mark false positives without widening the scanner
  key.

Still open (tracked in the weekly sweep): Seafile 11 → 13 (separate change),
mariadb/memcached/watchtower re-pins, and the curl/toolchain clean-up in our
own images.

## Rollback / removal

```bash
cd ~/83rr-poweredge
crontab -l | grep -v 'scripts/sbom-scan.sh' | crontab -       # stop the nightly scan
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop deptrack-frontend deptrack-apiserver deptrack-db
docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f deptrack-frontend deptrack-apiserver deptrack-db
# Revert through a PR on GitHub (don't commit on the server), then on the server:
git pull                                                      # removes services, vhost, backup step, scripts
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

The revert also removes the `backup_deptrack_db` step. That step already
skips a missing `deptrack-db`, so the backup stays green either way. Data stays
in the two volumes. To delete it for good (only after a final backup, and
only with Mark's OK): `docker volume rm 83rr-poweredge_deptrack_db_data
83rr-poweredge_deptrack_data`, and remove `DEPTRACK_DB_PASSWORD` / `DT_API_KEY`
from `.env` and `~/.local/bin/syft`.

---

## Deploy runbook (server-deploy session)

Run on the server as mcheli, from `~/83rr-poweredge`, after Mark has approved
and the PR is merged. Each step says what to check. Stop and report on
anything unexpected; don't improvise around a 4xx/5xx.

Use `DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"`.

**Timing:** do step 1 right after `git pull`. Until `DEPTRACK_DB_PASSWORD`
is in `.env`, every `docker compose` command in this directory fails on the
`:?` check (the same as `GRAFANA_ADMIN_PASSWORD`), for every service.
`backup.sh` skips the Dependency-Track dump while `deptrack-db` doesn't
exist. But once the container exists it must be running at 02:00, or that
night's backup records a failure and suppresses its heartbeat. So if you
stop mid-deploy, either finish before 02:00 or remove the containers
(`$DC rm -sf deptrack-frontend deptrack-apiserver deptrack-db`).

### 1. Pull and prepare `.env`

```bash
cd ~/83rr-poweredge && git pull
cp -p .env ".env.$(date +%F)-pre-deptrack.bak"
grep -q '^DEPTRACK_DB_PASSWORD=' .env || \
  echo "DEPTRACK_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)" >> .env
grep -c '^NTFY_PUBLISH_TOKEN=' .env          # expect 1 (already used by OpenSearch/Kuma)
$DC config -q && echo COMPOSE_OK
```

### 2. DNS and certificate

```bash
dig +short deptrack.ops.markcheli.com        # expect 192.168.1.179
# if empty (no wildcard record), create it:
#   source venv/bin/activate && python scripts/cloudflare_dns_manager.py create \
#     --domain markcheli.com --type A --name deptrack.ops.markcheli.com --content 192.168.1.179 --ttl 300
openssl x509 -in infrastructure/nginx/certs/letsencrypt-ops-markcheli.crt -noout -ext subjectAltName
                                              # expect DNS:*.ops.markcheli.com (wildcard covers deptrack.ops)
```

### 3. Start Dependency-Track

```bash
$DC pull deptrack-db deptrack-apiserver deptrack-frontend
$DC up -d deptrack-db deptrack-apiserver deptrack-frontend
for i in $(seq 1 40); do                      # up to ~7 min
  [ "$(docker ps --filter name=deptrack --filter health=healthy -q | wc -l)" -eq 3 ] && break; sleep 10
done; docker ps --filter name=deptrack --format '{{.Names}} {{.Status}}'
                                              # all three "(healthy)"; apiserver can take ~3 min
$DC logs --tail 100 deptrack-apiserver | grep -iE 'error|exception' || echo NO_ERRORS
docker exec deptrack-apiserver wget -qO- http://127.0.0.1:9000/health/ready   # "UP"
docker ps --filter name=deptrack --format '{{.Names}} {{.Ports}}'           # no 0.0.0.0 host ports
```

### 4. nginx

```bash
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

Verify from a LAN machine (e.g. the Mac mini):

```bash
curl -sI https://deptrack.ops.markcheli.com/ | head -1          # HTTP/2 200 (frontend)
curl -s https://deptrack.ops.markcheli.com/api/version          # JSON with "version":"5.2.1"
curl -s -o /dev/null -w '%{http_code}\n' -H 'Content-Encoding: br' -d x \
  https://deptrack.ops.markcheli.com/api/v1/bom                 # 415
```

From outside the LAN (phone hotspot), the same URL against the public IP
must give 403:
`curl -sk -o /dev/null -w '%{http_code}\n' --resolve deptrack.ops.markcheli.com:443:<public-ip> https://deptrack.ops.markcheli.com/`
(`<public-ip>`: the server's current public IP; don't commit it here).

### 5. Admin password and configuration

```bash
scripts/deptrack-setup.sh init-admin      # writes ~/.config/deptrack/admin-password; do NOT print it
scripts/deptrack-setup.sh apply           # expect "done."; adds DT_API_KEY to .env
grep -c '^DT_API_KEY=odt_' .env           # 1
```

Tell Mark the admin password is waiting in `~/.config/deptrack/admin-password`
for 1Password; after he confirms it's saved: `shred -u ~/.config/deptrack/admin-password`
(later `apply`/`alerts` runs then prompt for it or take `DT_ADMIN_PASSWORD`).
Log in once in the browser as admin to confirm the UI works.

### 6. Wait for the first mirrors

```bash
scripts/deptrack-setup.sh status          # repeat until osv and nvd show COMPLETED (can take 30–90 min)
$DC logs --since 10m deptrack-apiserver | grep -iE 'mirror|osv|nvd' | tail
```

A `FAILED` mirror: check the reason in `status` and the logs (outbound
allowlist, DNS, rate limits) before going on.

### 7. Syft and the first scan

```bash
scripts/install-syft.sh                   # "sha256 OK", "installed ~/.local/bin/syft"
~/.local/bin/syft version | head -3       # Version: 1.54.1
scripts/sbom-scan.sh --dry-run            # one "would scan" line per running container
docker ps -q | wc -l                      # N
scripts/sbom-scan.sh --no-notify          # expect "done: N uploaded, 0 unchanged, 0 failed, N containers"
scripts/deptrack-setup.sh status          # projects: N (N latest versions)
scripts/sbom-scan.sh --no-notify          # rerun: "0 uploaded, N unchanged" (idempotent)
```

Large images (plex, asa) take the longest. Any failures are
listed in `logs/sbom-scan.log`; report them rather than skipping.
In the UI, open a few projects and check that the components and findings
look sane. The findings should match what the latest security sweep found
for images that haven't been bumped yet.

### 8. Alerts

```bash
scripts/deptrack-setup.sh alerts on
scripts/deptrack-setup.sh test-alert      # expect "ntfy received: [...]"; Mark's phone shows the push
```

If `test-alert` reports NOTHING: `$DC logs --since 5m deptrack-apiserver | grep -i notif`.
Common causes: the filter expression dropping the synthetic test subject (then
check the rule in Administration → Notifications → Alerts, and confirm a real
alert with the next scan instead), or the webhook auth (secret
`NTFY_AUTH_HEADER` must be `Bearer <token>`; publisher config
`authHeaderValue` = that secret's name). Don't leave alerts silently broken:
report it.

### 9. Cron

```bash
( crontab -l 2>/dev/null | grep -v 'scripts/sbom-scan.sh'; \
  echo '30 3 * * * /home/mcheli/83rr-poweredge/scripts/sbom-scan.sh >/dev/null 2>&1' ) | crontab -
crontab -l | grep sbom-scan
```

### 10. Final checks

```bash
scripts/backup.sh --dry-run | grep -iE 'deptrack|Dependency'   # dump + deptrack_data volume listed
source venv/bin/activate && python scripts/test_infrastructure.py
$DC logs --tail 100 deptrack-apiserver deptrack-frontend deptrack-db | grep -iE 'error|fatal' || echo NO_ERRORS
docker stats --no-stream deptrack-apiserver deptrack-db       # apiserver well under its 6 GiB limit
```

Next morning: `tail -20 logs/sbom-scan.log` shows the 03:30 run, and
`tail -5 logs/backup.log` ends with "Backup completed successfully!".

### Rollback during deploy

Anything wrong before step 9:
`$DC rm -sf deptrack-frontend deptrack-apiserver deptrack-db` (stop and remove
them, so the 02:00 backup skips the dump instead of failing on a stopped DB;
the volumes stay). If the change has to come out entirely, follow
**Rollback / removal** above: the cron line, a revert PR + `git pull`, and an
nginx reload. Until the revert lands, nginx keeps the vhost; it just returns
502 for deptrack.ops because of the variable `proxy_pass`. Restore `.env` from the `.env.<date>-pre-deptrack.bak` copy if needed.
No other service is touched by this change, so nothing else needs restarting.
