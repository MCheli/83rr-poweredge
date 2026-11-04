# seafile-db patch runbook: mariadb 10.11.15 → 10.11.19 (November 2026)

**Status:** planned (PR `patch/seafile-db-mariadb-10.11.19`). Not deployed.
**Why:** `seafile-db` runs `mariadb:10.11`, resolved to a January 2026 build (10.11.15). Dependency-Track
shows about **32 critical / 105 high** findings for it, including the real OpenSSL **CVE-2025-15467**.
The new pin is `mariadb:10.11.19@sha256:d769e379…deae` (multi-arch index, Ubuntu jammy base,
published 2026-10-27; it includes `linux/amd64`, digest `sha256:6c65a843…f5ea`). This stays on 10.11.
It's a same-series patch, so there are no on-disk format changes and no `mariadb-upgrade` is
required. (`MARIADB_AUTO_UPGRADE` isn't set, and that's fine.)
**Expected downtime:** about 1–2 minutes of Seafile errors while the DB container is recreated. Book 30 minutes.
**Scope:** only `seafile-db` is recreated (`--no-deps`). `seafile` and `seafile-notification` keep running
and reconnect. Seafile 14 is deliberately **not** part of this (14.0.9 is still beta).
**Watchtower:** `seafile-db` has no `com.centurylinklabs.watchtower.enable` label (watchtower only acts on
labelled containers), so merging this PR deploys nothing. It takes effect only at step 3.

Run on `83rr-poweredge` in `~/83rr-poweredge`, in **bash**. Every block starts with the PRELUDE, so a
fresh shell (a new SSH session or an agent's tool call) reloads its state from `~/seafile-db-patch.state`.

```bash
# PRELUDE: run at the top of every block, in bash
cd ~/83rr-poweredge
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }   # never the override file
q() { docker exec seafile-db sh -c "exec mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"$1\""; }
[ -f ~/seafile-db-patch.state ] && . ~/seafile-db-patch.state   # BK, OLD_ID, OLD_DIGEST, HEAD0 (step 1)
```

Credentials: every DB command runs **inside** the container and uses the container's own
`$MYSQL_ROOT_PASSWORD`, which compose set from `SEAFILE_DB_ROOT_PASSWORD` in `.env`. Nothing is echoed or
put on a host command line.

---

## 1. Record the rollback state (no downtime)

```bash
# PRELUDE first
[ -f ~/seafile-db-patch.state ] && echo "!! state file exists from an earlier run: check it, don't overwrite"
git status --porcelain | grep -v '^??' && echo "!! tracked changes in the checkout: stop"
BK=/data/backups/mariadb-$(date +%Y%m%d)
OLD_ID=$(docker inspect seafile-db --format '{{.Image}}')
OLD_DIGEST=$(docker image inspect "$OLD_ID" --format '{{index .RepoDigests 0}}')
HEAD0=$(git rev-parse HEAD)
printf 'BK=%s\nOLD_ID=%s\nOLD_DIGEST=%s\nHEAD0=%s\n' "$BK" "$OLD_ID" "$OLD_DIGEST" "$HEAD0" > ~/seafile-db-patch.state
cat ~/seafile-db-patch.state
docker tag "$OLD_ID" mariadb:10.11-rollback       # keeps the old image from being pruned
q "SELECT VERSION()"                               # expect 10.11.15-MariaDB-…
docker pull mariadb:10.11.19@sha256:d769e37960821dfdcf096954f6e7ac89f747e116c1bba98e48edd265dfc7deae
```

## 2. Back up (gate: everything must print OK)

The dump runs while Seafile is up. `--single-transaction` gives a consistent InnoDB snapshot.

```bash
# PRELUDE first
mkdir -p "$BK"                                   # /data/backups is mcheli-owned; no sudo (it needs a password)
docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
  --routines --triggers --events --all-databases' | gzip > "$BK/seafile-alldb.sql.gz"
docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
  --routines --triggers --events --databases ccnet_db seafile_db seahub_db' | gzip > "$BK/seafile-3db.sql.gz"
for f in "$BK"/seafile-alldb.sql.gz "$BK"/seafile-3db.sql.gz; do
  gzip -t "$f" && zcat "$f" | tail -1 | grep -q 'Dump completed' && echo "OK $f $(du -h "$f" | cut -f1)" || echo "!! BAD $f"
done
zcat "$BK/seafile-3db.sql.gz" | grep -cE '^CREATE DATABASE'    # 3
# baseline counts, compared again in step 4
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo
   UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2" | tee "$BK/baseline.txt"
# off-host copy, under dated names so the nightly seafile_*.sql.gz rotation can't clash with it
NAS=/mnt/nas/83rr-backup/databases
if findmnt /mnt/nas >/dev/null && [ -d "$NAS" ]; then
  (cd "$BK" && sha256sum seafile-alldb.sql.gz seafile-3db.sql.gz > SHA256SUMS)
  for f in seafile-alldb.sql.gz seafile-3db.sql.gz; do cp "$BK/$f" "$NAS/premariadb-10.11.19-${BK##*-}-$f"; done
  (cd "$BK" && sed "s#  #  $NAS/premariadb-10.11.19-${BK##*-}-#" SHA256SUMS | sha256sum -c) && echo "OK NAS copy"
else
  echo "!! NAS NOT MOUNTED: no off-host copy. Stop and fix the mount (or get Mark's OK to continue with the local copy only)"
fi
```

Each dump should be about 20 MB compressed, the size of the nightly `seafile_*.sql.gz`. A much smaller
file means something failed. Don't continue until both lines say `OK`.

## 3. Deploy (downtime starts here)

```bash
# PRELUDE first
git pull --ff-only
grep -n 'mariadb:10.11.19@sha256:d769e379' docker-compose.yml      # the new pin is present
dc config --quiet && echo "OK compose config"
dc up -d --no-deps --dry-run seafile-db                             # must list only seafile-db (Recreate)
dc up -d --no-deps seafile-db
# bounded wait for the DB to accept connections (3 min)
for i in $(seq 1 36); do
  docker exec seafile-db healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1 && { echo "OK db up after $((i*5))s"; break; }
  sleep 5
done
docker exec seafile-db healthcheck.sh --connect --innodb_initialized || echo "!! DB not up: go to Rollback"
q "SELECT VERSION()"                                                # 10.11.19-MariaDB-…
```

If the dry run lists any service other than `seafile-db`, stop. That means the checkout has drifted from main.

## 4. Verify

```bash
# PRELUDE first
# 4a. Seafile reconnects without a restart (give it up to 2 min)
for i in $(seq 1 24); do
  c=$(curl -s -o /dev/null -w '%{http_code}' https://files.markcheli.com/api2/ping/)
  [ "$c" = 200 ] && { echo "OK api ping"; break; }; sleep 5
done
[ "$c" = 200 ] || echo "!! ping failed after 2 min (last $c): do the one-time restart below"
curl -s -o /dev/null -w 'web %{http_code}\n' https://files.markcheli.com/accounts/login/   # 200
docker inspect seafile --format '{{.State.Health.Status}}'                                 # healthy
docker logs --since 10m seafile-notification 2>&1 | grep -iE 'error|fail' | tail -5           # nothing new after the restart
```

If the ping fails after 2 minutes, restart the apps **once** and **say so in the report**:
`dc restart seafile seafile-notification`, wait for `healthy`, then
`dc exec nginx nginx -t && dc exec nginx nginx -s reload`. The static upstream keeps the old container IP otherwise.

```bash
# 4b. fileserver path through the edge (non-interactive)
curl -s -o /dev/null -w 'seafhttp %{http_code}\n' https://files.markcheli.com/seafhttp/protocol-version   # 200
# 4c. Counts and the DB error log
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo
   UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2" | diff - "$BK/baseline.txt" && echo "OK counts match"
docker logs --since 10m seafile-db 2>&1 | grep -E '\[(ERROR|Warning)\]' | grep -v 'Aborted connection'   # expect nothing
docker logs --since 10m seafile 2>&1 | grep -iE 'error|mysql' | tail -10                                   # expect at most the brief disconnect
```

**Gate:** 4a ping 200, web 200, `healthy`, seafhttp 200, `OK counts match`, and no new DB `[ERROR]` lines.
These checks are all non-interactive, so an agent operator can run them.

**Optional (Mark, afterwards, not a gate):** log in at https://files.markcheli.com, open a library (an
authenticated library list through the DB), and check that the desktop client shows "synced".

## 5. 10-minute watch

```bash
# PRELUDE first
for i in $(seq 1 10); do
  printf '%s db=%s seafile=%s ping=%s\n' "$(date +%T)" \
    "$(docker inspect seafile-db --format '{{.State.Status}}/{{.RestartCount}}')" \
    "$(docker inspect seafile --format '{{.State.Health.Status}}')" \
    "$(curl -s -o /dev/null -w '%{http_code}' https://files.markcheli.com/api2/ping/)"
  sleep 60
done
docker logs --since 11m seafile-db 2>&1 | grep -cE '\[ERROR\]'      # 0
```

If every line shows `running/0 healthy 200`, it's done. Once a week has passed, delete `mariadb:10.11-rollback` and
`~/seafile-db-patch.state`. Keep `$BK` until the next nightly backups have rotated (7 days).

---

## 6. Rollback

**Guard first.** This block destroys nothing, but it must print `GUARDS_OK` before you run the next one.

```bash
# PRELUDE first
rb=1
[ -n "$BK" ] && [ -n "$OLD_ID" ] || { echo "!! state not loaded"; rb=0; }
docker image inspect mariadb:10.11-rollback >/dev/null 2>&1 || { echo "!! rollback image missing: docker pull $OLD_DIGEST"; rb=0; }
zcat "$BK/seafile-3db.sql.gz" 2>/dev/null | tail -1 | grep -q 'Dump completed' || { echo "!! no complete dump in $BK"; rb=0; }
[ "$rb" = 1 ] && echo GUARDS_OK
```

**6a. Image rollback** (the usual case: the data is fine, you only want the old binary). Patch
downgrades within 10.11 keep the same datadir and redo-log format. If 10.11.15 still refuses to start, go to 6b.

```bash
# PRELUDE first. Only after GUARDS_OK.
printf 'services:\n  seafile-db:\n    image: mariadb:10.11-rollback\n' > ~/seafile-db-rollback.override.yml
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f ~/seafile-db-rollback.override.yml \
  up -d --no-deps seafile-db
for i in $(seq 1 36); do docker exec seafile-db healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1 && break; sleep 5; done
q "SELECT VERSION()"                        # 10.11.15
# then re-run step 4. Keep the override file until the repo is reverted (git revert of this PR on main),
# because a plain `dc up -d` would bring 10.11.19 back.
```

**6b. Data restore** (only if the DB won't start or the data is wrong). Writes made after the step 2 dump are
lost. There's no point of no return otherwise.

```bash
# PRELUDE first. Only after GUARDS_OK, and with seafile-db running (6a if needed).
dc stop -t 60 seafile seafile-notification
for d in ccnet_db seafile_db seahub_db; do q "DROP DATABASE IF EXISTS $d"; done
zcat "$BK/seafile-3db.sql.gz" | docker exec -i seafile-db sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo
   UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2" | diff - "$BK/baseline.txt" && echo "OK restored"
dc up -d --no-deps seafile seafile-notification
dc exec nginx nginx -t && dc exec nginx nginx -s reload   # refresh the static upstream IPs
```

The grants live in the `mysql` schema, which isn't dropped, so the `seafile` user keeps working.

**Rollback timing:** image only, about 2 minutes. With a data restore, about 5 minutes (the dump is about 20 MB).
