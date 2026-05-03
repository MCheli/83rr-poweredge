# Backup & Restore — 83RR PowerEdge

This document describes what is backed up, how to restore from a full device
failure, and how to test a restore without touching production. The authoritative
script is `scripts/backup.sh`; this doc describes the *intent* and *recovery
procedure*. If they disagree, read the script.

---

## What is backed up

**Schedule**: cron at `0 2 * * *` (daily 02:00 ET).
**Destination**: NAS at `//MarksNAS/Performance/83rr-backup/` (CIFS mount at `/mnt/nas`).
**Retention** (set in `backup.sh`): 7 daily / 4 weekly / 3 monthly snapshots, hardlinked.

### Database dumps — `/mnt/nas/83rr-backup/databases/*.sql.gz`

These are the *authoritative* recovery path for stateful services. The volume rsyncs
below are a hot copy of the data dirs and may not be crash-consistent.

| Service | Dump | Container | Command |
|---|---|---|---|
| Seafile (MariaDB) | `seafile_<ts>.sql.gz` | `seafile-db` | `mysqldump --all-databases` |
| Tallied (PostgreSQL) | `tallied_<ts>.sql.gz` | `tallied-db` | `pg_dump tallied` |
| Tasks (PostgreSQL) | `tasks_<ts>.sql.gz` | `tasks-db` | `pg_dump tasks` |
| Energy Monitor (PostgreSQL) | `energy_monitor_<ts>.sql.gz` | `energy-monitor-db` | `pg_dump panel_tool` |

The `cleanup_old_backups` step keeps the newest 14 dump files per service (set in
`backup.sh:304`).

### File mirrors — `/mnt/nas/83rr-backup/latest/`

`latest/` is rsynced fresh every night; `daily/<date>/`, `weekly/<date>/`, and
`monthly/<date>/` are hardlinked snapshots.

| Path on host | Backup destination | Why |
|---|---|---|
| `~/83rr-poweredge/` | `latest/config/83rr-poweredge/` | Compose, nginx confs, certs, scripts, **`.env`** |
| `/home/mcheli/letsencrypt/` | `latest/config/letsencrypt/` | LE certs for `*.ops.markcheli.com` |
| `/root/.nas-credentials` | `latest/config/nas-credentials` | Required to mount the NAS during recovery |
| `/storage/seafile/` | `latest/seafile/` | Seafile blob storage (~3 GB) |

### Docker volumes — `latest/docker-volumes/<volume>/`

| Volume | Approx size | Why |
|---|---|---|
| `83rr-poweredge_grafana_data` | 42 M | Dashboards, datasources, users |
| `83rr-poweredge_prometheus_data` | 3.4 G | Metrics history (~30 days TSDB retention) |
| `83rr-poweredge_minecraft_data` | 405 M | World saves |
| `83rr-poweredge_plex_config` | 312 M | Plex's metadata DB only — *not media* |
| `83rr-poweredge_tallied_db_data` | 81 M | Postgres data dir (use `.sql.gz` for restore) |
| `83rr-poweredge_tasks_db_data` | 47 M | Postgres data dir (use `.sql.gz` for restore) |
| `83rr-poweredge_energy_monitor_db_data` | 47 M | Postgres data dir (use `.sql.gz` for restore) |
| `83rr-poweredge_energy_monitor_data` | small | Snapshots and logs from the panel-tool app |

---

## What is NOT backed up

These are *intentional* exclusions. If any of them matters to you, the backup
script needs to grow.

| Excluded | Reason |
|---|---|
| `/storage/media` (Plex library, ~2.3 TB) | Re-rippable / re-downloadable. Too large for the NAS target. |
| OpenSearch data | Logs are ephemeral; Fluent Bit re-ships from container stdout. |
| Fluent Bit buffer / Marimo / personal-website-node-modules | Ephemeral or regenerable. |
| Docker images | Pulled from `ghcr.io` / Docker Hub on `docker compose up`. |
| Crontab / systemd units / `/etc` | Re-created by hand during recovery. The single backup cron line is documented in `scripts/backup.sh` header. |
| Monarch session token (Tallied) | Provider invalidates on re-login; must reconnect via UI after restore. |
| Home Assistant token in Energy Monitor | Encrypted at rest with `ENERGY_MONITOR_SECRET_KEY` from `.env` — which *is* backed up — so this survives if `.env` does. |

---

## Operational health checks

**Before trusting the backup, look at:**

1. **Last successful run timestamp**:
   `tail -5 ~/83rr-poweredge/logs/backup.log` — should end with `Backup completed successfully!` from the most recent night.
2. **Current dump sizes** — they should grow gradually, not collapse to a few KB:
   ```bash
   ls -la /mnt/nas/83rr-backup/databases/*.sql.gz | tail -20
   ```
   A sudden drop from MB to KB means the source DB was empty or the dump aborted mid-stream.
3. **Snapshot continuity**:
   ```bash
   ls /mnt/nas/83rr-backup/daily/   # should have today + previous 6 days
   ls /mnt/nas/83rr-backup/weekly/  # last 4 Sundays
   ```
   Gaps mean the script failed to run on those days.

### Known failure mode: NAS not mounted

If the NAS is unreachable at 02:00, `check_nas_mount` aborts the entire run.
There's currently **no alerting on backup failure** — the only signal is `[ERROR]`
lines in `logs/backup.log`. A 10-day silent gap actually happened in April 2026.

Mitigation until alerting is added: include `tail -3 logs/backup.log` in your
morning routine, or grep weekly:
```bash
grep -c "Backup completed successfully" ~/83rr-poweredge/logs/backup.log | tail -7
```

---

## Recovery from full device failure

Assumes new hardware + the NAS is intact. Total RTO ~4–8 hours including image
pulls and SSL setup.

### Step 1 — Bootstrap the OS

1. Install Ubuntu 22.04 LTS (or matching version), Docker Engine, Docker Compose v2,
   `cifs-utils`, `git`.
2. Create user `mcheli` with the same UID/GID (1000:1000) the existing files use.
3. Add the user to the `docker` group.

### Step 2 — Mount the NAS

You need `/root/.nas-credentials` before you can mount the NAS. Get it from:
- The off-host password-manager copy (the contents are tiny — `username=`/`password=`/`domain=`), **or**
- A previous file backup on a separate medium.

```bash
sudo mkdir -p /mnt/nas
sudo bash -c 'cat > /root/.nas-credentials' <<'EOF'
username=<from password manager>
password=<from password manager>
domain=<from password manager>
EOF
sudo chmod 600 /root/.nas-credentials

# Add fstab entry:
echo '//MarksNAS/Performance /mnt/nas cifs credentials=/root/.nas-credentials,uid=1000,gid=1000,file_mode=0755,dir_mode=0755,vers=3.0,soft,nofail,_netdev 0 0' | sudo tee -a /etc/fstab
sudo mount /mnt/nas
```

Once mounted, you can also retrieve the credentials file from
`/mnt/nas/83rr-backup/latest/config/nas-credentials` for verification.

### Step 3 — Restore the project directory

```bash
rsync -aL /mnt/nas/83rr-backup/latest/config/83rr-poweredge/ ~/83rr-poweredge/
```

This includes `.env` with all secrets — make sure NAS access is locked down.

### Step 4 — Restore Let's Encrypt certs

```bash
sudo mkdir -p /home/mcheli/letsencrypt
sudo rsync -aL /mnt/nas/83rr-backup/latest/config/letsencrypt/ /home/mcheli/letsencrypt/
sudo chown -R root:root /home/mcheli/letsencrypt
```

### Step 5 — Restore Seafile blob storage

```bash
sudo mkdir -p /storage/seafile
sudo rsync -aL /mnt/nas/83rr-backup/latest/seafile/ /storage/seafile/
```

### Step 6 — Re-create Docker volumes from the rsync mirror

For each volume in `backup.sh:backup_docker_volumes()`:

```bash
for vol in 83rr-poweredge_grafana_data 83rr-poweredge_prometheus_data \
           83rr-poweredge_minecraft_data 83rr-poweredge_plex_config \
           83rr-poweredge_tallied_db_data 83rr-poweredge_tasks_db_data \
           83rr-poweredge_energy_monitor_db_data 83rr-poweredge_energy_monitor_data; do
  docker volume create "$vol"
  sudo rsync -aL "/mnt/nas/83rr-backup/latest/docker-volumes/$vol/" \
                 "/var/lib/docker/volumes/$vol/_data/"
done
```

### Step 7 — Bring the stack up

```bash
cd ~/83rr-poweredge
docker login ghcr.io          # GITHUB_USERNAME / GITHUB_TOKEN from .env
docker compose pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Step 8 — Restore SQL dumps (authoritative state)

The volume rsync gave you a hot copy that may not be crash-consistent for Postgres.
Replay the dumps over what came up:

```bash
# Pick the most recent file for each service in /mnt/nas/83rr-backup/databases/
# Example with placeholder timestamps — substitute the actual newest file:

# Seafile
gunzip -c /mnt/nas/83rr-backup/databases/seafile_<ts>.sql.gz | \
  docker exec -i seafile-db mysql -u root -p"$SEAFILE_DB_ROOT_PASSWORD"

# Tallied
gunzip -c /mnt/nas/83rr-backup/databases/tallied_<ts>.sql.gz | \
  docker exec -i tallied-db psql -U tallied tallied

# Tasks
gunzip -c /mnt/nas/83rr-backup/databases/tasks_<ts>.sql.gz | \
  docker exec -i tasks-db psql -U tasks tasks

# Energy Monitor
gunzip -c /mnt/nas/83rr-backup/databases/energy_monitor_<ts>.sql.gz | \
  docker exec -i energy-monitor-db psql -U panel_tool panel_tool
```

The Postgres targets need the database to exist (it will, from the volume restore) —
if you're starting from an empty volume, `docker compose up -d <db>` first, then
let the app's migrations run, then load the dump.

### Step 9 — Reinstall the backup cron

```bash
crontab -e
# Add:
0 2 * * * /home/mcheli/83rr-poweredge/scripts/backup.sh >> /home/mcheli/83rr-poweredge/logs/backup.log 2>&1
```

### Step 10 — Reconnect external integrations

- **Tallied**: open the UI, reconnect Monarch (token doesn't survive sessions).
  SimpleFin should still authenticate from stored creds.
- **Energy Monitor**: open `https://energy.ops.markcheli.com` — the in-app setup
  screen should pre-fill with the previous ESPHome URL and HA token (decrypted
  from `.env`'s `ENERGY_MONITOR_SECRET_KEY`). Verify connectivity to ESPHome.
- **Cloudflare**: verify DNS still points to your new server's public IP. If the
  IP changed, update via `python scripts/cloudflare_dns_manager.py` (script is in
  the restored project dir; venv requires `python3 -m venv venv && pip install -r
  requirements.txt`).

### Step 11 — Smoke test

```bash
docker ps                                                 # all services Up (healthy)
curl -I https://www.markcheli.com                         # 200
curl -fsS https://energy.ops.markcheli.com/api/health     # 200 from LAN
docker compose logs --tail 50 | grep -i error             # nothing concerning
```

---

## Testing a restore (without touching production)

The point of testing is to prove the backups are *actually usable* — not just that
files exist. Do this on a separate machine (a VM, a spare laptop, even an old
Raspberry Pi for the small services). **Never restore over the live `/var/lib/docker`
or live volumes.**

### Minimal restore test

This is a "can I bring up Tallied from yesterday's backup" smoke test. Takes ~15
minutes and verifies the most-likely-to-corrupt path (Postgres dumps).

1. **On a sandbox machine** with Docker installed, pick one service and one DB:
   ```bash
   mkdir -p /tmp/restore-test && cd /tmp/restore-test

   # Mount the NAS read-only so you can't accidentally modify it
   sudo mkdir -p /mnt/nas-ro
   sudo mount -t cifs -o ro,credentials=/root/.nas-credentials,vers=3.0 \
     //MarksNAS/Performance /mnt/nas-ro

   # Spin up an isolated Postgres just for this test
   docker run -d --name restore-test-pg \
     -e POSTGRES_USER=tallied -e POSTGRES_PASSWORD=test \
     -e POSTGRES_DB=tallied -p 25432:5432 postgres:16-alpine

   # Wait for it to be ready, then load the latest dump
   until docker exec restore-test-pg pg_isready -U tallied; do sleep 1; done
   gunzip -c /mnt/nas-ro/83rr-backup/databases/tallied_*.sql.gz | tail -1 \
     | docker exec -i restore-test-pg psql -U tallied tallied

   # Verify
   docker exec restore-test-pg psql -U tallied tallied -c \
     "SELECT count(*) FROM tenant_f00ffe2e.transactions;"
   ```

2. Repeat with `tasks` and `energy_monitor` substituting database/user/table names.
3. Tear down: `docker rm -f restore-test-pg && sudo umount /mnt/nas-ro`.

If any of those `psql` loads emit errors, you have a corrupted dump and need to
fall back to the volume mirror or an earlier snapshot. Log what you find.

### Full restore test

This is closer to a real DR drill. Plan for half a day.

1. Provision a fresh VM (Ubuntu 22.04, Docker, ≥50 GB disk, ≥8 GB RAM).
2. Follow steps 2–8 of the **Recovery from full device failure** procedure above,
   but:
   - Mount the NAS **read-only** (`-o ro`) to guarantee you can't damage backups
   - Skip step 9 (don't install the backup cron on the test VM)
   - In step 10, do not reconnect Monarch or modify Cloudflare DNS — those would
     touch production state. Just verify the local UI loads and the database is
     populated.
3. Run smoke tests (step 11). Note any errors.
4. After the test, tear down the VM. Don't keep restored copies of `.env` lying
   around on machines you don't control.

### What "passing" means

- All containers start with `(healthy)` status within 5 minutes.
- The Tallied UI shows transactions, the Tasks UI shows tasks, Energy Monitor
  shows breaker mappings.
- Grafana dashboards render with historical data.
- Prometheus targets show recent scrape times (will be stale, but TSDB intact).

If anything fails, fix the backup script before declaring success — silent
backup loss is worse than no backup, because you trust it.

### Cadence

- **Minimal restore test**: monthly. Quick, cheap, catches dump-format regressions.
- **Full restore test**: yearly, or after major architecture changes (new service
  added, Postgres major version upgrade, OS upgrade, etc.). Schedule it like a
  fire drill — pick a calm week, allocate a day.

---

## Improvements queued (not yet implemented)

- Backup-failure alerting (push to ntfy / Slack / Home Assistant when a run
  doesn't end with `Backup completed successfully`).
- Stale entries in `/mnt/nas/83rr-backup/latest/docker-volumes/` from removed
  services (e.g., the JupyterHub leftovers) need a cleanup pass — `rsync --delete`
  doesn't remove sibling dirs that aren't in the sync list.
- Plex media (~2.3 TB) is intentionally not backed up. If you decide it should
  be, plan for a dedicated large-volume target — the NAS is undersized for it.

---

**Last updated**: 2026-05-03
