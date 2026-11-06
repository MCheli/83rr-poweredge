# Grafana "Database locked" / dashboard 500s (2026-11)

## Symptom

- Grafana logs `logger=sqlstore.transactions msg="Database locked, sleeping then retrying" error="database is locked (5) (SQLITE_BUSY)"`.
- In the same second, `logger=context userId=0 ... msg="Request Completed" method=POST path=/api/ds/query status=500 time_ms=7507` appears, plus `ngalert.scheduler "Failed to update alert rules" ... database is locked`.
- nginx shows those requests as 500s on dashboard.ops: `/api/ds/query` and `/api/annotations`. The referrer is `system-dashboard` with `refresh=30s`.

`userId=0` together with "Failed to authenticate request" means the request fails while Grafana looks up or rotates the session in SQLite. The datasource query itself isn't what fails. A refreshing dashboard fires one request per panel, all at the same moment. They contend with the alert scheduler and with 13.x's unified-storage writes for SQLite's single lock.

## Did it start with the 13.3.0 upgrade? No.

Daily counts from `logs-homelab-*` (all 90 retained days, UTC). `locked` = grafana lines with "Database locked". `gf 500` = grafana `status=500` request lines. `nginx 500` = nginx 5xx where the referrer is dashboard.ops or the path is `/api/ds/` or `/api/annotations`.

| day | Grafana version | locked | gf 500 | nginx 500 | grafana lines |
|---|---|---|---|---|---|
| 08-09 … 10-29 (82 days) | 11.5.2 | **0** | 0 | 0 | ~339/day (514–911 on 10-17…10-19) |
| 10-30 | 11.5.2 | 4 (first at 03:26:43Z) | 0 | 0 | 377 |
| 10-31 | 11.5.2 → 12.4.14 at 17:03Z | 29 (5 before the 12.4 start) | 6 | 40 | 2,454 |
| 11-01 | 12.4.14 | 28 | 0 | 0 | 5,435 |
| 11-02 | 12.4.14 | 1 | 0 | 0 | 4,523 |
| 11-03 | 12.4.14 | 1 | 0 | 0 | 4,520 |
| 11-04 | 13.3.0 (from ~02:40Z) | 18 | 8 | 58 | 78,323 |
| 11-05 | 13.3.0 | 20 | 15 | 15 | 87,050 |

So the locking started on **2026-10-30 on 11.5.2**, before both the 12.4 and the 13.3 upgrades. Whether 500s show up on a given day tracks whether someone had a dashboard open with auto-refresh: 10-31, 11-04 and 11-05 have 500s, and 11-01 has 28 locks but no 500s. The 13.3 upgrade didn't start it. It does make every lock more visible, because 13.x does more SQLite work: unified storage, the search index, and the per-query `Plugin Request Completed` / `queryData` INFO lines behind the jump to ~80k lines/day.

Reproduce the numbers:

```bash
scripts/logq.sh 'container_name:grafana AND log:"Database locked"' 2160
scripts/logq.sh 'container_name:grafana AND log:"status=500"' 2160
scripts/logq.sh 'container_name:nginx AND status:>=500 AND path:(\/api\/ds\/* OR \/api\/annotations*)' 2160
```

## Fix (config only)

```yaml
- GF_DATABASE_WAL=true
- GF_DATABASE_QUERY_RETRIES=5
```

These come from Grafana's configuration reference, [database] section (https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#database, the 13.x docs), and `conf/defaults.ini`:

- **`wal`**: "For "sqlite3" only. Setting to enable/disable Write-Ahead Logging … The default value is `false` (disabled)."
  - In WAL mode, readers don't block the writer and the writer doesn't block readers (https://sqlite.org/wal.html). That's the contention here: many concurrent reads from panels and auth, plus a few writes.
  - The docs also note: "SQLite stores the journal mode in the database file, so a database that was opened with WAL keeps using it", and "Setting `wal` back to `false` puts the database into `DELETE` journal mode again on the next start." So it's reversible with config alone.
- **`query_retries`**: "applies to `sqlite` only and controls the number of times the system retries a query when the database is locked. The default value is `0` (disabled)."
  - `transaction_retries` already defaults to 10 (`defaults.ini`; the docs page says 5). That's the "sleeping then retrying" line. Plain queries got no retry, so they failed straight to a 500. 5 matches the order of magnitude of the transaction setting.
- **`cache_mode`** stays `private` (the default). Grafana documents `private`/`shared` without recommending either. SQLite's shared-cache mode uses table-level locking, and SQLite itself discourages it (https://sqlite.org/sharedcache.html). It would add lock contention, not remove it.
- **Busy timeout**: Grafana 13 has no busy-timeout setting. Neither the docs nor `defaults.ini` has one, so the retries above are the supported knob.

### Volume and permission check for WAL

- **Volume:** `grafana_data` is a local-driver named volume, at `/data/docker/volumes/83rr-poweredge_grafana_data/_data` on ext4 (`/dev/sdh1`). That's a local filesystem, which WAL needs for its `-shm` shared-memory file. It would be a problem on NFS/CIFS, and that isn't the case here.
- **Permissions:** `/var/lib/grafana` is `drwxrwxrwx grafana:root`, and Grafana runs as uid 472. SQLite can create `grafana.db-wal` and `grafana.db-shm` next to `grafana.db`.
- **Backups:**
  - `scripts/backup.sh` rsyncs the whole volume directory, so the `-wal` file goes along with the db. That's the same "hot copy" consistency as today.
  - Anything that copies **only** `grafana.db` from a running Grafana (e.g. `docker cp grafana:/var/lib/grafana/grafana.db`) can miss commits that are still in `-wal`. Stop Grafana first, or use the full-volume tar from the 13.3 runbook.
- **Rollback point:**
  - The 13.3 upgrade backup (`/data/backups/upgrade-20261103/grafana_data.tgz`, NAS copy under `/mnt/nas/83rr-backup/upgrade-20261103/`) stays the rollback point.
  - That runbook's restore step does `find /dst -mindepth 1 -delete` before untarring, so stale `-wal`/`-shm` files are removed. Restoring that pre-WAL `grafana.db` is safe.
  - Never restore `grafana.db` on its own while old `-wal`/`-shm` files are still there.

## Deploy

```bash
cd ~/83rr-poweredge && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps grafana

# health
docker ps --filter name=^grafana$ --format '{{.Status}}'                  # (healthy) within ~60s
docker exec grafana wget -qO- http://localhost:3000/api/health; echo        # "database": "ok"
curl -s -o /dev/null -w '%{http_code}\n' https://dashboard.ops.markcheli.com/login   # 200 (from the LAN)
docker compose logs --since 5m grafana | grep -iE 'level=(error|crit)|locked' || echo "clean start"

# WAL actually on: the two side files exist next to grafana.db
docker exec grafana ls -la /var/lib/grafana | grep grafana.db
#   -> grafana.db, grafana.db-shm, grafana.db-wal
```

Rollback (config only): remove the two env lines and run the same `up -d --no-deps grafana`. Grafana switches the file back to DELETE journal mode on start.

## Verify it stopped

Open https://dashboard.ops.markcheli.com/d/system-dashboard with 30s refresh and leave it for ~30 min (the old failure pattern). Then:

```bash
scripts/logq.sh 'container_name:grafana AND log:"Database locked"' 1;   echo "exit=$?"   # expect 0 hits / exit 0
scripts/logq.sh 'container_name:grafana AND log:"status=500"' 1;        echo "exit=$?"   # expect 0
scripts/logq.sh 'container_name:nginx AND status:>=500 AND path:(\/api\/ds\/* OR \/api\/annotations*)' 1   # expect 0
scripts/logq.sh errors 1 grafana       # residual errors (e.g. "Failed to fetch org IDs for external ruler sync") are unrelated
```

Re-check the next day with `24` in place of `1`. Baseline: 18–29 locks and 8–58 dashboard 500s on any day with an open auto-refreshing dashboard.

If locks continue at a lower rate, the next step is `GF_DATABASE_HIGH_AVAILABILITY=false`. `defaults.ini` describes it as: "Only set it to false if you run only a single instance of Grafana", which is the case here, and it cuts HA polling of the DB. The step after that is Postgres for Grafana, which would add a container, so it's a Level 3 change.
