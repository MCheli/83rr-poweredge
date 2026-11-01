# Seafile Upgrade Runbook — 11.0.13 → 12.0.14 → 13.0.21

> **Superseded (2026-11-01) by [`seafile-upgrade-2026-11.md`](seafile-upgrade-2026-11.md).**
> This draft predates the 12.0/13.0 config changes (env-driven config, separate
> notification server, redis) and its rollback leaves migrated tables behind.
> Don't follow it. Kept for history only.

**Status:** planned change, not yet executed. Schedule a maintenance window
(~30–60 min, files.markcheli.com down during it).

## Why

`seafileltd/seafile-mc:11.0.13` is the **last 11.0.x release** (2024-11-04);
the 11.0 line is EOL. The only path forward is the **major** chain
**11 → 12 → 13** (Seafile does not support skipping a major). Each major
runs DB schema migrations on first start.

- Current: `11.0.13` (pinned in `docker-compose.yml`)
- Target: `12.0.14` (last 12.0) → `13.0.21` (current 13.0)
- DBs: `ccnet_db`, `seafile_db`, `seahub_db` (MariaDB `seafile-db` container)
- Data: `/storage/seafile` → `/shared` (bind mount), object store under
  `/storage/seafile/seafile/`

## Hard prerequisites (do not skip)

1. **Verified backup exists.** A pre-upgrade snapshot was taken
   2026-05-17 at `/mnt/nas/83rr-backup/pre-seafile-upgrade-20260517/`
   (DB dump `seafile-alldb.sql.gz`, gzip-OK, all 4 DBs; 3.2 G data copy).
   **Re-take immediately before the window** — see step 1; data changes daily.
2. Read upstream notes for each hop:
   - <https://manual.seafile.com/12.0/upgrade/upgrade_notes_for_12.0.x/>
   - <https://manual.seafile.com/13.0/upgrade/upgrade_notes_for_13.0.x/>
   (12.0 changes the default DB host handling and Python deps; 13.0 changes
   the notification/seasearch services. Confirm the env in
   `docker-compose.yml` still matches.)
3. Have a second terminal open and the rollback section below in view.
4. Announce downtime; confirm no large sync is mid-flight.

## Procedure

> Run from `~/83rr-poweredge`. Replace `<TAG>` per hop. Do the hops
> **sequentially**, fully verifying each before the next.

### Step 1 — Fresh verified backup (gate)

```bash
SNAP=/mnt/nas/83rr-backup/pre-seafile-upgrade-$(date +%Y%m%d-%H%M)
mkdir -p "$SNAP"
PW=$(grep -E '^SEAFILE_DB_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec seafile-db sh -c "exec mysqldump -u root -p'$PW' --all-databases \
  --single-transaction --quick --lock-tables=false" | gzip > "$SNAP/seafile-alldb.sql.gz"
gzip -t "$SNAP/seafile-alldb.sql.gz" && echo "DB dump OK"
sudo rsync -aL --delete /storage/seafile/ "$SNAP/seafile-data/"   # ~3 GB
echo "11.0.13" > "$SNAP/ROLLBACK_FROM_VERSION"
```
Do **not** proceed unless `DB dump OK` printed and `$SNAP/seafile-data/seafile/` is populated.

### Step 2 — 11.0.13 → 12.0.14

```bash
docker compose stop seafile                       # stop app (db stays up)
# edit docker-compose.yml: image: seafileltd/seafile-mc:12.0.14
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d seafile
docker logs -f seafile        # watch for "Upgrade" / migration lines, then "Seahub is started"
```

Verify before continuing:
- `docker logs seafile 2>&1 | grep -iE 'upgrad|migrat|error|traceback'` — migrations ran, no errors
- `curl -sk -o /dev/null -w '%{http_code}' https://files.markcheli.com/accounts/login/` → `200`
- Log in via the web UI; confirm a library lists and a file downloads
- `docker exec seafile-db sh -c "mysql -uroot -p'$PW' -e 'SELECT version FROM seahub_db.django_migrations LIMIT 1'"` (sanity that seahub_db is reachable/migrated)

### Step 3 — 12.0.14 → 13.0.21

Repeat Step 2 with `image: seafileltd/seafile-mc:13.0.21`. 13.0 introduces
extra services (notification-server / seasearch) inside the image — confirm
`docker logs seafile` shows them starting and no port clash. Re-run the
same verification checks.

### Step 4 — Finalize

- Commit the `docker-compose.yml` image bump (now `13.0.21`).
- Update `CLAUDE.md` service inventory note (Seafile version).
- Update memory `[[project-backup-rsync-recursion]]` siblings if relevant.
- Keep the pre-upgrade snapshot for ≥2 weeks.

## Rollback (per hop)

If a hop fails verification:

```bash
docker compose stop seafile
# revert docker-compose.yml image: back to the previous tag
# restore DB from the snapshot taken in Step 1:
PW=$(grep -E '^SEAFILE_DB_ROOT_PASSWORD=' .env | cut -d= -f2-)
zcat "$SNAP/seafile-alldb.sql.gz" | docker exec -i seafile-db sh -c "mysql -uroot -p'$PW'"
# if object data was touched, restore it too:
sudo rsync -aL --delete "$SNAP/seafile-data/" /storage/seafile/
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d seafile
```
Seafile migrations are forward-only — **the DB restore is mandatory** to
roll a major back; reverting the image alone against a migrated DB will not
start. This is why Step 1 is a hard gate.

## Notes / gotchas specific to this host

- Seafile is bind-mounted (`/storage/seafile:/shared`), and `/storage` is
  the `/dev/md0` RAID with the post-reboot mount race. The
  `docker-wait-storage.conf` systemd drop-in is installed, but still
  confirm `findmnt /storage` before starting any hop.
- The internal nginx in the seafile image symlinks `/var/log/nginx` →
  `/shared/logs/var-log`; an unclean stop can leave an ELOOP self-symlink
  (seen 2026-05-17). If seafile crash-loops on
  `Too many levels of symbolic links`, `docker compose up -d --force-recreate
  seafile` against the correctly-mounted `/storage` clears it.
- Use the **prod** invocation (`-f docker-compose.yml -f docker-compose.prod.yml`)
  consistently — the dev `docker-compose.override.yml` remaps some volumes
  to `*_local`, which has caused volume drift on other services.
