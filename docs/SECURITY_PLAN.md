# Security Plan & Backlog

**Created:** 2026-10-18 (after the Plex compromise — see commit 96db834 and
`~/plex-incident-2026-10-18/` for evidence). This is the "security backlog"
referenced by CLAUDE.md. Tick items off and add the commit hash as you go.

Legend: **[me]** = Claude can do it (repo/config + `docker compose`),
**[sudo]** = needs the owner at a sudo prompt, **[router]** = router/ISP UI.

---

## Sweep summary (2026-10-18)

**Intrusion verdict:** no evidence the attacker reached anything beyond Plex.
OpenSearch history (from 2026-07-21), 30 d of Prometheus CPU/egress, every
container's `docker diff`/`docker top`, host auth logs, crontabs, `~/.ssh`,
and app login logs (Seafile, Tallied/Tasks SSO, Grafana) are clean.
*Blind spots:* container-to-container traffic isn't logged (Plex could have
read OpenSearch — no auth — or Grafana — default password — invisibly);
Postgres doesn't log successful connections; Webmin `miniserv.log` and root
crontab unread (no sudo). `/etc/webmin` mtime 04:02 UTC 10-18 unexplained.

**Background noise seen:** ~130k failed Postgres logins on 5432 since 07-03
(generic users only); attacker's IPv6 /48 (`2a0f:ca80:b00b::/48`) probed
`.env`/`.aws` on status.markcheli.com in Sept (only SPA fallbacks returned);
`45.194.92.53` (attacker /24) hit tallied-db 07-14 (rejected).

**Root causes behind most findings:**
1. The origin accepts traffic from anyone, not only Cloudflare, and "LAN-only"
   `*.ops` vhosts share the public :443 listener, so anyone can reach them
   with a `Host:` header.
2. Docker-published ports bind `0.0.0.0` and bypass ufw (no DOCKER-USER rules).
3. One flat `infrastructure` docker network; several services with no/weak auth.
4. Stale images/engine; detection controls installed on paper only.

---

## Phase 0 — urgent, quick (internet-reachable now)

- [x] **P0-1 Grafana** *(done 2026-10-18: every `*.ops` block now `allow 192.168.1.0/24; deny all;` — verified 403 from non-LAN; flask-dev.ops removed; password rotated to 32-char random in `.env`, compose now `${GRAFANA_ADMIN_PASSWORD:?}`. Caveat: Grafana doesn't log successful logins, so prior use of admin123 can't be ruled out — review users/API keys/datasources at next session.)* reachable from internet via Host header with
  `admin/admin123` (verified). Rotate (`docker exec grafana grafana-cli admin
  reset-admin-password …` — env var only applies on first init), move to
  `${GRAFANA_ADMIN_PASSWORD}` in compose (currently hardcoded
  `docker-compose.yml` ~L304; CLAUDE.md is wrong about it), add
  `allow 192.168.1.0/24; deny all;` to **every** `*.ops` server block
  (dashboard, logs, opensearch, prometheus, cadvisor, report, energy,
  openclaw), delete dead `flask-dev.ops` block (no auth, proxies to flask-api). **[me]**
- [ ] **P0-2 Plex direct WAN path**: router still forwards 32400 (Plex logs
  show `(WAN)` exploitation straight to it, bypassing nginx). Remove the
  forward + disable Remote Access/manual mapping **[router]**; bind compose
  port to `192.168.1.179:32400:32400` **[me]**.
- [ ] **P0-3 Postgres (tallied-db) 5432** on 0.0.0.0, `pg_hba.conf:17-18`
  `hostssl all all 0.0.0.0/0` + `::/0` (matches superuser too). Decide if any
  remote tenant (`tld_*`) needs it → restrict lines to those roles + reject
  tallied/tallied_app from non-docker, or drop/bind the port; set
  `log_connections=on`. **[me]** — *open question: who needs remote 5432?*
- [~] **P0-4 Backups** *(2026-10-18: NAS back online + remounted; backup.sh now re-checks `mountpoint` after mounting; fresh backup run. Remaining: fstab by IP + automount [sudo].)*: 10-18 02:00 run failed (NAS was off). Fix
  `backup.sh` false "[OK] NAS mounted" (add `mountpoint -q /mnt/nas || exit 1`
  after the mount) **[me]**; `/etc/fstab`: NAS by IP not `MarksNAS`, add
  `x-systemd.automount,x-systemd.mount-timeout=30` **[sudo]**; take a fresh
  backup before Phase 2.
- [ ] **P0-5 Webmin** 2.641, root, `0.0.0.0:10000` tcp+udp, not used by repo.
  `sudo systemctl disable --now webmin && sudo apt purge webmin`, or bind
  192.168.1.179 + `allow=192.168.1.0/24` in miniserv.conf. Check
  `/var/webmin/miniserv.log` for non-LAN logins first. **[sudo]**
- [~] **P0-6 Bind internal ports** *(3000/5001 → 127.0.0.1 done 2026-10-18. 5050/5051 → `LOCAL_IP` (.env) 2026-11-01: LAN consumers (HeyClawy firmware, Home Assistant) already hard-depend on the same address, and a failed bind only takes down the two voice services, so the DHCP reservation below is still recommended. Remaining 32400/32469/1900 deliberately left: LAN IP is DHCP-dynamic, binding to it risks containers failing at boot — Plex failing breaks nginx. Do a DHCP reservation (or netplan static) first. No global IPv6 on host, so `[::]` is not internet-exposed today.)* to 127.0.0.1/LAN in compose: 3000
  (personal-website), 5001 (flask-api), 5050 edge-tts + 5051 faster-whisper
  (no auth), 32469, 1900/udp → LAN IP. **[me]**
- [x] **P0-7 File perms** *(done 2026-10-18)*: `chmod 600` `infrastructure/nginx/certs/*.key`
  (wildcard + letsencrypt-ops are 644), `infrastructure/openclaw/.env` (664),
  openclaw `gogcli/token.json`. **[me]**

## Phase 1 — this week

- [ ] **P1-1 Origin lockdown**: nginx `set_real_ip_from <CF ranges>;
  real_ip_header CF-Connecting-IP;` → then set `X-Forwarded-For $remote_addr`
  (not `$proxy_add_x_forwarded_for`) for files/status/money/tasks (Seahub
  lockout is spoofable today) → then CF-only on 443 via DOCKER-USER rules
  **[sudo]** or Cloudflare Authenticated Origin Pulls (`ssl_verify_client`). **[me]+[sudo]**
- [ ] **P1-2 Uptime Kuma**: status.markcheli.com proxies the full admin UI.
  Expose only `/status/ /api/status-page/ /api/badge/ /assets/ /upload/
  /icon.svg`, LAN-allow the rest; pin by digest, drop watchtower label. **[me]**
- [ ] **P1-3 Privilege**: `/etc/sudoers.d/backup` NOPASSWD
  `/usr/bin/rsync -aL --delete *` = trivial root. Replace with a root-owned
  fixed-args wrapper or root systemd timer; `sudo gpasswd -d mcheli lxd`;
  run Plex as a dedicated uid (`PLEX_UID/PLEX_GID`) not 1000. **[sudo]+[me]**
- [ ] **P1-4 Detection is mostly non-functional**:
  - 3 monitors from 2d63a4e exist only as JSON in the repo — install in OpenSearch alerting.
  - `emit_security_telemetry.sh` reads the wrong `ss` columns (`$4" "$3`);
    allowlist already contains 10000/5432/9200/445; no UDP; 10-min sampling.
  - Docker `exec_*` events not ingested; host `auth.log`/journal not shipped.
  - Uptime Kuma SMTP alerts failing ("451 Maximum credits exceeded").
  - rkhunter `CRON_DAILY_RUN=""`; no auditd. **[me]+[sudo]**
- [ ] **P1-5 Small host hardening** **[sudo]**:
  - Samba: `interfaces = lo eno1`, `bind interfaces only = yes`,
    `map to guest = never`, `usershare allow guests = no`,
    `server min protocol = SMB3`; remove pasted heredoc junk/`EOF` +
    printer shares; `mask samba-ad-dc`.
  - sshd `10-hardening.conf`: `X11Forwarding no`, `AllowUsers mcheli`,
    `MaxAuthTries 3`; passphrase on `~/.ssh/id_ed25519`.
  - Disable: avahi, ModemManager, open-vm-tools/vgauth (bare metal),
    multipathd, open-iscsi, postfix (failed), cloud-init.
- [ ] **P1-6 Minecraft**: no whitelist on public 25565 — enable or accept. **[me]**

## Phase 2 — maintenance window (restarts every container)

Pre-reqs: fresh backup (P0-4); live-restore is off; last Docker upgrade caused
an outage (c538355); `/storage` mount race mitigated by
`docker.service.d/wait-storage.conf`; WAN IP may rotate (522 memory).

- [ ] **P2-1 Docker 29.5.0 → 29.9.1, containerd 2.2.3 → 2.4.2**
  (CVE-2026-92543 etc.; containerd 2.2 EOL 2026-11-06) + `apt full-upgrade`
  (66 pending). Verify DOCKER-USER rules survive. **[sudo]**
- [ ] **P2-2 Image batch, pin by digest**: postgres 16.10 → latest 16.x (all
  three DBs; ~9 CVEs), Grafana 11.5.2 → 12.x (CVE-2025-4123/3580/3415/6023),
  prometheus v3.2.1, node-exporter v1.8.2, cadvisor v0.52.1, fluent-bit 3.2 →
  4.1, opensearch 3.2.0, openclaw 2026.4.11 (review advisories),
  faster-whisper → speaches. **[me]**
- [ ] **P2-3 Docker socket**: socket-proxy (tecnativa) for uptime-kuma,
  fluent-bit (`:ro` doesn't restrict the API); cadvisor mounts all of
  `/var/run` rw → socket only; pin watchtower by digest. **[me]**

## Phase 3 — projects

- [ ] **P3-1 Seafile 11.0.13 (EOL) → 12 → 13** per `docs/SEAFILE_UPGRADE_RUNBOOK.md`.
- [ ] **P3-2 Network segmentation** (per-app networks; plex/minecraft/asa off
  the shared net first). Requires fixing compose override drift first
  (memory: compose override drift / volume choice).
- [ ] **P3-3 Backup redesign**: NAS is mounted rw as uid 1000 and snapshots are
  `cp -al` hardlinks → not ransomware-resilient. restic/borg (encrypted) +
  NAS immutable snapshots or append-only + offsite (object lock); restore test.
- [ ] **P3-4 OpenSearch security plugin** (currently disabled; anyone on the
  docker network can read/write/delete logs).
- [ ] **P3-5 Supply chain**: watchtower auto-deploys `ghcr.io/mcheli/*:latest`
  (money/tasks hold financial data) within ~5 min of a push. Branch
  protection, required reviews, image signing / pull-based signed digests.
- [ ] **P3-6 Don't bake secrets into images**: `infrastructure/nginx/Dockerfile`
  COPYs `certs/` and `.htpasswd` — mount at runtime instead; never push that image.

## Open questions for the owner

1. Does anything off-host need Postgres 5432 (the `tld_*` tenant roles)?
2. Full list of router port forwards (known/expected: 80, 443, 25565, 7777/udp;
   known-bad: 32400; check 5432, 10000).
3. Is `github.com/MCheli/83rr-poweredge` public? If so treat `admin123` and
   the nginx layout as published.
