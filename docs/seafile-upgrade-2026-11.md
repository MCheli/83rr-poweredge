# Seafile upgrade runbook: 11.0.13 → 12.0.14 → 13.0.28 (November 2026)

**Status:** planned. Replaces the earlier draft in `docs/SEAFILE_UPGRADE_RUNBOOK.md`.
**Why:** `seafileltd/seafile-mc:11.0.13` (built 2024-11-04, Ubuntu 22.04) is the last 11.0
release and is internet-facing at files.markcheli.com. Dependency-Track shows ~417 critical/high
findings, including OpenSSL CVE-2025-15467 (EPSS 0.75), Django 4.2.16, Pillow 10.2 and PyJWT 2.6.
13.0.28 is built on Ubuntu 24.04 and ships Django 5.2 and Pillow 11.3.
**Expected downtime:** about 45 minutes. Book a 90-minute window (see [Downtime](#downtime)).
**Who:** the server operator, on `83rr-poweredge`, in `~/83rr-poweredge`. Follow it in order and don't skip any gates.

---

## 0. Background (read once)

### Upgrade path: through 12.0, not direct

The image's start script (`scripts_13.0/upgrade.py` in haiwen/seafile-docker) reads the version
stamp `/shared/seafile/seafile-data/current_version`. It then runs every `upgrade_X_Y.sh` between
that version and the image's version in order, so a 13.0 image started on 11.0 data *would*
run `upgrade_11.0_12.0.sh` and then `upgrade_12.0_13.0.sh` back to back. The official manual,
however, documents only the single-major hops (11.0→12.0, 12.0→13.0), and the configuration
change differs at each hop. **We do the two hops separately** and verify after each one. Each
hop's DB migration then runs under the image it was written for, and if something
fails we know which major caused it. Starting the 12.0 hop costs about 5 extra minutes.

### What changed upstream, and how this repo handles it

| Change | Version | What we do |
|---|---|---|
| Config is env-driven (`SEAFILE_MYSQL_DB_*`, `SEAFILE_SERVER_HOSTNAME/PROTOCOL`, `JWT_PRIVATE_KEY`). `SERVICE_URL`, `FILE_SERVER_ROOT` and `ccnet.conf` are removed | 12.0 | New env block on `seafile` in `docker-compose.yml`. Three new `.env` vars. `seafile_conf_migrate.py --step 12` drops the dead settings |
| Upstream's reference compose uses `.env` + `seafile-server.yml` + `caddy.yml` (Caddy does TLS). | 12.0 | **Not adopted.** Our edge nginx keeps doing TLS (Cloudflare origin cert). The Seafile container is still plain HTTP on :80. Caddy is only upstream's convenience proxy |
| Bundled in-container nginx: no longer generates or reads `/shared/nginx/conf` (13.0). It fronts every component on :80 (`/`, `/seafhttp`, `/media`) | 12.0/13.0 | Edge `/seafhttp` now goes to `seafile:80` and no longer to `seafile:8082` directly. I tested this path against the live 11.0 container on 2026-11-01 (`/seafhttp/protocol-version` → 200) |
| Notification server is its own image (`seafileltd/notification-server`) | 12.0 | New `seafile-notification` service. Edge `/notification` now goes to `seafile-notification:8083` |
| Notification config is env-driven (`ENABLE_NOTIFICATION_SERVER`, `INNER_NOTIFICATION_SERVER_URL`) | 13.0 | Env vars on `seafile` (12.0 ignores them; 12.0 reads `seafile.conf [notification]`) |
| Cache via `CACHE_PROVIDER`. Redis recommended and the default; memcached still supported | 13.0 | New `seafile-redis`. memcached is kept for the 12.0 hop (12.0 still reads `CACHES` from `seahub_settings.py`) and is removed later |
| `DATABASES`/`CACHES` in `seahub_settings.py` and `[database]`/`[notification]` in `seafile.conf` conflict with the env vars | 13.0 | `seafile_conf_migrate.py --step 13` removes them |
| SeaDoc 2.0, thumbnail server, metadata server, SeaSearch, Seafile AI: separate optional containers | 13.0 | Not deployed. `ENABLE_SEADOC=false` (otherwise the UI points at a missing `/sdoc-server`) |
| WebDAV: LDAP logins removed. Old file tags need migration. Binary install unsupported | 12.0/13.0 | No effect: WebDAV is disabled (`seafdav.conf`), there's no LDAP, and this is a Docker install |
| `ALLOWED_HOSTS` must include `127.0.0.1` if set | 12.0 | Not set in our `seahub_settings.py`, so nothing to do |

### Current deployment (inventoried read-only 2026-11-01)

- `seafile`: `seafileltd/seafile-mc:11.0.13` (digest `sha256:1239b087…f422c`; the local image is
  only tagged `:latest`, so pull by digest for rollback). Bind mount `/storage/seafile` → `/shared`.
  In-container nginx on :80, seaf-server fileserver on 0.0.0.0:8082 and notification server on :8083.
- `seafile-db`: `mariadb:10.11` (10.11.15), named volume `83rr-poweredge_seafile_db` (342 MB on disk).
  DBs `ccnet_db` 0.4 MB, `seafile_db` 1.5 MB, `seahub_db` 72 MB (62 MB of that is `django_session`, and
  more than 99% of those sessions have expired). 1 user, 3 libraries, `Activity` has about 4.9k rows, so no pre-clean is needed.
- `seafile-memcached`: `memcached:1.6`.
- Data: `/storage/seafile` is about 3.4 GB (`seafile-data` 3.4 G, `seahub-data` 15 M, logs about 8 M).
- Config customisations: `seahub_settings.py` (CSRF_TRUSTED_ORIGINS, SECURE_PROXY_SSL_HEADER,
  NOTIFICATION_SERVER_URL, memcached CACHES, TIME_ZONE=Etc/UTC). `seafile.conf` ([fileserver] 8082,
  [database], [notification] enabled with its own JWT key). `seafevents.conf` (email, statistics,
  file history). WebDAV disabled. Admin-UI (constance) settings are branding only: SITE_NAME,
  SITE_TITLE, CUSTOM_CSS, ENABLE_BRANDING_CSS. There's no SeaDoc, OnlyOffice, LDAP or 2FA.
- Clients: 4 device tokens (desktop + iOS).
- Edge: `infrastructure/nginx/conf.d/production.conf`, server `files.markcheli.com`.
- Existing backups (`scripts/backup.sh`, 02:00 daily): `mysqldump --all-databases` →
  `/mnt/nas/83rr-backup/databases/seafile_<ts>.sql.gz` (about 20 MB), and `rsync -aL` of `/storage/seafile` →
  `/mnt/nas/83rr-backup/latest/seafile/`. That rsync is a single rolling copy that the next night's run overwrites,
  and CIFS doesn't keep ownership. That's not enough for a rollback, so step 2 takes its own snapshot.
- Disk: `/storage` 81% used, **858 GB free**. `/mnt/nas` 3.0 TB free. Docker root `/data` 827 GB free.
  We need about 3.5 GB on the NAS, 3.5 GB on `/storage` and about 3 GB of images. **Space is not a concern.**

---

## 1. Preparation (day before or start of window, no downtime)

Everything in this section is safe while 11.0 is running. **Don't `git pull` the upgrade yet:** the
edge nginx config is bind-mounted, and the new `/notification` route only works once
`seafile-notification` exists.

The snippets assume **bash** (the login shell is zsh). They also depend on shell state: the `dc`/`q`
helpers, `TS`/`SNAP`/`LOCAL` from step 2, and the 12.0 image overrides from step 4. If a block
runs in a new shell (a new SSH connection, or an agent's separate tool call), that state is gone,
and an empty `$SNAP`/`$LOCAL` makes the rollback destructive. So **start every block with the
prelude**. Step 2 and step 4 persist the state it reloads:

```bash
# PRELUDE: run at the top of every block, in bash
cd ~/83rr-poweredge
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }
q() { docker exec seafile-db sh -c "exec mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"$1\""; }
[ -f ~/seafile-upgrade.state ] && . ~/seafile-upgrade.state   # TS, SNAP, LOCAL (written in step 2)
[ -f ~/seafile-upgrade.hop12 ] && . ~/seafile-upgrade.hop12   # 12.0 image overrides (step 4 to step 5 only)
```

```bash
bash   # then paste the PRELUDE
findmnt /storage && findmnt /mnt/nas          # both must print a mount
df -h /storage /mnt/nas /data
dc ps seafile seafile-db seafile-memcached    # all Up
```

### 1a. Add the three new `.env` values

The new compose file refuses to start **any** service until these exist, so add them first.
`SEAFILE_DB_PASSWORD` and `SEAFILE_JWT_PRIVATE_KEY` are copied from the live `seafile.conf`, so the DB
user and the notification-server key stay the same. Nothing is echoed.

```bash
C=/storage/seafile/seafile/conf/seafile.conf
DBPW=$(sudo sed -n '/^\[database\]/,/^\[/{s/^password *= *//p;}' "$C")
JWT=$(sudo sed -n '/^\[notification\]/,/^\[/{s/^jwt_private_key *= *//p;}' "$C")
REDISPW=$(openssl rand -hex 32)
echo "lengths: db=${#DBPW} jwt=${#JWT} redis=${#REDISPW}"   # expect db>0, jwt>=32, redis=64
# compose interpolates $ in .env, so a value with $, quotes, space or # needs hand-quoting:
for v in "$DBPW" "$JWT"; do printf '%s' "$v" | grep -q "[\$\"' #]" && echo "!! special character: quote this value by hand in .env"; done
# the seafile DB user must accept the copied password:
docker exec -e P="$DBPW" seafile-db sh -c 'mariadb -useafile -p"$P" -N -e "SELECT 1" seafile_db'   # prints 1
grep -qE '^SEAFILE_(DB_PASSWORD|JWT_PRIVATE_KEY|REDIS_PASSWORD)=' .env && echo "!! already present, stop and check" || \
  printf 'SEAFILE_DB_PASSWORD=%s\nSEAFILE_JWT_PRIVATE_KEY=%s\nSEAFILE_REDIS_PASSWORD=%s\n' "$DBPW" "$JWT" "$REDISPW" >> .env
unset DBPW JWT REDISPW
grep -cE '^SEAFILE_(DB_PASSWORD|JWT_PRIVATE_KEY|REDIS_PASSWORD)=' .env   # 3
```

If the JWT key is shorter than 32 characters, generate a new one with `openssl rand -hex 32` instead.
The notification server and Seafile only need to agree with each other.

### 1b. Pre-pull every image (by digest)

```bash
docker pull seafileltd/seafile-mc:12.0.14@sha256:8d0dd6b682c12cb0e1d4f1f73ba223b0176e9e3d43805408a2f631706e9c10e8
docker pull seafileltd/notification-server:12.0.11@sha256:3155a6e476109edcb36be9b953e551d0dbe0ec37839b2c64d4f6dc559642532e
docker pull seafileltd/seafile-mc:13.0.28@sha256:b0c90832126bf432db908449f1bb450211e6bbf75a2193bab3399e2a9636eccf
docker pull seafileltd/notification-server:13.0.21@sha256:1cac4101d0f4527ad08c00b5452ceb05d790db95d6c8ab6bbace82429c1e5217
docker pull redis:7.4.12-alpine@sha256:8da19c7399dca900c6822a1cf30f9d2285585e2c4b457ff4095b0f4500054d3f
# rollback image: make sure 11.0.13 stays available under its real tag
docker pull seafileltd/seafile-mc@sha256:1239b087aa4bdf1b60a3802e80855f230736ac5d5fa3325a40b15d4c598f422c
docker tag  seafileltd/seafile-mc@sha256:1239b087aa4bdf1b60a3802e80855f230736ac5d5fa3325a40b15d4c598f422c seafileltd/seafile-mc:11.0.13
```

### 1c. Optional: drop expired web sessions

There are about 260k rows, nearly all expired, and they make up 62 MB of the 72 MB `seahub_db`. Expired sessions are already unusable, so
this only shrinks the dump and the migration:

```bash
docker exec seafile-db sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DELETE FROM seahub_db.django_session WHERE expire_date < NOW()"'
```

### 1d. Tell the clients

Before the window: on the desktop, **pause sync** (or quit the Seafile client). On iOS, turn off camera upload or just don't upload.
This keeps uploads from being interrupted when the server stops.

---

## 2. Maintenance start: stop Seafile and back up (gate)

```bash
# PRELUDE first
[ -f ~/seafile-upgrade.state ] && echo "!! ~/seafile-upgrade.state exists from an earlier run: check it, don't overwrite"
TS=$(date +%Y%m%d-%H%M)
SNAP=/mnt/nas/83rr-backup/pre-seafile-13-$TS        # off-host copy
LOCAL=/storage/seafile-pre13-$TS                    # same-disk copy for fast rollback
printf 'TS=%s\nSNAP=%s\nLOCAL=%s\n' "$TS" "$SNAP" "$LOCAL" > ~/seafile-upgrade.state   # reloaded by the prelude
mkdir -p "$SNAP"
git rev-parse HEAD > "$SNAP/git-head"               # pre-upgrade commit (rollback target)

dc stop -t 60 seafile                               # db + memcached stay up
docker ps --filter name='^seafile$' --format '{{.Status}}'   # must print nothing
```

files.markcheli.com now returns 502. **Downtime starts here.**

### 2a. Baseline counts (to compare after each hop)

```bash
# PRELUDE first
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo
   UNION ALL SELECT 'branches',COUNT(*) FROM seafile_db.Branch UNION ALL SELECT 'repo_size_sum',SUM(size) FROM seafile_db.RepoSize
   UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2" | tee "$SNAP/baseline.txt"
sudo cat /storage/seafile/seafile/seafile-data/current_version | tee -a "$SNAP/baseline.txt"   # 11.0.13
```

### 2b. Database dumps (Seafile is stopped, so they're consistent)

The **per-DB dump** is the one used for a restore. The `--all-databases` dump is a second copy
(it includes the `mysql` schema, which we never restore over a running server).

```bash
docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --events \
  --databases ccnet_db seafile_db seahub_db' | gzip > "$SNAP/seafile-3db.sql.gz"
docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --events \
  --all-databases' | gzip > "$SNAP/seafile-alldb.sql.gz"
```

Verify both dumps (**all must pass**):

```bash
for f in "$SNAP"/seafile-3db.sql.gz "$SNAP"/seafile-alldb.sql.gz; do
  gzip -t "$f" && zcat "$f" | tail -1 | grep -q 'Dump completed' && echo "OK $f $(du -h "$f" | cut -f1)" || echo "!! BAD $f"
done
zcat "$SNAP/seafile-3db.sql.gz" | grep -cE '^CREATE DATABASE'      # 3
zcat "$SNAP/seafile-3db.sql.gz" | grep -c '^CREATE TABLE'          # about 150 or more (compare with the live count below)
q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('ccnet_db','seafile_db','seahub_db') AND table_type='BASE TABLE'"
```

**Restore test** into a throwaway MariaDB (no network, deleted afterwards). Recommended: it's the
only proof that the rollback dump really loads.

```bash
docker run -d --rm --name seafile-restore-test --network none -e MARIADB_ROOT_PASSWORD=restoretest mariadb:10.11
# The entrypoint runs a temporary init server, then restarts. Wait for the real server, or the
# import can hit the restart halfway through.
until docker logs seafile-restore-test 2>&1 | grep -q 'init process done'; do sleep 2; done
until docker exec seafile-restore-test mariadb -uroot -prestoretest -e 'SELECT 1' >/dev/null 2>&1; do sleep 2; done
zcat "$SNAP/seafile-3db.sql.gz" | docker exec -i seafile-restore-test mariadb -uroot -prestoretest
docker exec seafile-restore-test mariadb -uroot -prestoretest -N -e \
  "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo UNION ALL SELECT 'branches',COUNT(*) FROM seafile_db.Branch"
docker stop seafile-restore-test      # --rm deletes it
```

The counts must match `baseline.txt`.

### 2c. Data snapshots

```bash
# 1) off-host tarball (keeps ownership, modes and symlinks, which the CIFS NAS can't store as files)
sudo tar --numeric-owner -cpf "$SNAP/seafile-shared.tar" -C /storage seafile
# 2) same-disk copy for a fast rollback
sudo rsync -aHAX --numeric-ids /storage/seafile/ "$LOCAL/"
```

Verify (**all must pass**):

```bash
N_LIVE=$(sudo find /storage/seafile | wc -l)
N_TAR=$(sudo tar -tf "$SNAP/seafile-shared.tar" | wc -l)
echo "live=$N_LIVE tar=$N_TAR"                               # equal (±1 for the top dir)
sudo rsync -aHAXn --numeric-ids --delete --checksum -i /storage/seafile/ "$LOCAL/" | wc -l   # 0
sudo du -sh /storage/seafile "$LOCAL" "$SNAP/seafile-shared.tar"                            # about 3.4G each
```

### 2d. Config snapshot

```bash
mkdir -p "$SNAP/config" && chmod 700 "$SNAP/config"
cp docker-compose.yml docker-compose.prod.yml .env infrastructure/nginx/conf.d/production.conf "$SNAP/config/"
sudo cp -a /storage/seafile/seafile/conf "$SNAP/config/seafile-conf"     # also inside the tarball, kept separately for quick diffs
echo "11.0.13 sha256:1239b087aa4bdf1b60a3802e80855f230736ac5d5fa3325a40b15d4c598f422c" > "$SNAP/ROLLBACK_IMAGE"
ls -la "$SNAP"
```

**Gate:** don't continue unless 2b and 2c verified cleanly. If anything failed, start Seafile
again (`dc up -d seafile`), and the window is over with nothing changed.

---

## 3. Get the upgrade code

```bash
git fetch origin && git status --short          # must print nothing (.env is gitignored)
git pull --ff-only                              # brings in this PR (compose + nginx + script)
dc config -q && echo COMPOSE_OK                 # fails loudly if 1a was skipped
```

Don't run `nginx -t` here. Seafile is stopped, so Docker DNS can't resolve the static
`upstream seafile { server seafile:80; }`, and the test fails with `host not found in upstream`
even though the config is fine. Step 4b tests and reloads once seafile is running again.

---

## 4. Hop 1: 11.0.13 → 12.0.14

```bash
# PRELUDE first
printf 'export %s\n' \
  SEAFILE_IMAGE=seafileltd/seafile-mc:12.0.14@sha256:8d0dd6b682c12cb0e1d4f1f73ba223b0176e9e3d43805408a2f631706e9c10e8 \
  SEAFILE_NOTIFICATION_IMAGE=seafileltd/notification-server:12.0.11@sha256:3155a6e476109edcb36be9b953e551d0dbe0ec37839b2c64d4f6dc559642532e \
  > ~/seafile-upgrade.hop12
. ~/seafile-upgrade.hop12
dc config seafile seafile-notification | grep 'image: seafileltd'   # both must show 12.0.x
```

> ⚠️ The prelude reloads these overrides until step 5 deletes `~/seafile-upgrade.hop12`. A `dc up`
> **without** them would start 13.0 directly, which skips the 12.0 checkpoint. It isn't harmful (both
> migrations would still run), but it isn't the plan. Before every `dc up` in step 4, run the `dc config … | grep` check.

**4a. Config migration (12):**

```bash
sudo python3 scripts/one-time/seafile_conf_migrate.py --step 12          # review diff (secrets masked)
sudo python3 scripts/one-time/seafile_conf_migrate.py --step 12 --apply
```

Expected: `SERVICE_URL` and `FILE_SERVER_ROOT` are removed from `seahub_settings.py`, and `seafile.conf`
`[notification] host = seafile-notification`.

**4b. Start 12.0 and watch the migration:**

```bash
dc up -d seafile                  # also starts seafile-redis (unused until 13.0); db/memcached unchanged
docker logs -f seafile            # Ctrl-C when "Seahub is started" (or similar) appears
```

Look for `Running scripts /opt/seafile/seafile-server-12.0.14/upgrade/upgrade_11.0_12.0.sh` followed
by the SQL updates finishing without a `Traceback`. Then:

```bash
sudo cat /storage/seafile/seafile/seafile-data/current_version          # 12.0.14
docker logs seafile 2>&1 | grep -iE 'traceback|error|failed' | grep -v 'error_log' | tail -20   # expect nothing relevant
dc up -d seafile-notification
docker logs --tail 20 seafile-notification                              # no DB/JWT errors
dc exec nginx nginx -t && dc exec nginx nginx -s reload                 # activate new /seafhttp + /notification routes
```

**4c. Verify 12.0** (all must pass before hop 2):

```bash
for i in $(seq 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' seafile)" = healthy ] && break; sleep 5; done
docker inspect -f '{{.State.Health.Status}}' seafile      # healthy (gives up after 5 min instead of hanging)
curl -s -o /dev/null -w '%{http_code}\n' https://files.markcheli.com/accounts/login/   # 200
curl -s https://files.markcheli.com/api2/ping/                                         # "pong"
curl -s -w ' %{http_code}\n' https://files.markcheli.com/notification/ping             # {"ret": "pong"} 200
curl -s -w ' %{http_code}\n' https://files.markcheli.com/seafhttp/protocol-version     # {"version": 2} 200
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo UNION ALL SELECT 'branches',COUNT(*) FROM seafile_db.Branch"   # = baseline
sudo tail -n 50 /storage/seafile/seafile/logs/seahub.log | grep -iE 'error|traceback'   # nothing new
```

Then log in to the web UI and open a library. If anything fails, go to [Rollback](#7-rollback).
If the healthcheck never reaches `healthy`, check `docker inspect -f '{{json .State.Health}}' seafile | jq`
before you decide.

---

## 5. Hop 2: 12.0.14 → 13.0.28

```bash
# PRELUDE first
dc stop -t 60 seafile-notification seafile
rm -f ~/seafile-upgrade.hop12; unset SEAFILE_IMAGE SEAFILE_NOTIFICATION_IMAGE
dc config seafile seafile-notification | grep 'image: seafileltd'   # both must show 13.0.x
```

**5a. Config migration (13):** the env vars take over the DB, cache and notification settings.

```bash
sudo python3 scripts/one-time/seafile_conf_migrate.py --step 13
sudo python3 scripts/one-time/seafile_conf_migrate.py --step 13 --apply
```

Expected: `DATABASES`, `CACHES`, `COMPRESS_CACHE_BACKEND` and `NOTIFICATION_SERVER_URL` are removed from
`seahub_settings.py`, and `[database]` and `[notification]` are removed from `seafile.conf`. `[fileserver]`, `SECRET_KEY`,
`CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER` and `TIME_ZONE` stay.

**5b. Start 13.0:**

```bash
dc up -d seafile
docker logs -f seafile            # expect upgrade_12.0_13.0.sh, then seahub start; Ctrl-C
sudo cat /storage/seafile/seafile/seafile-data/current_version      # 13.0.28
docker logs seafile 2>&1 | grep -iE 'traceback|error|failed' | tail -20
dc up -d seafile-notification
docker logs --tail 20 seafile-notification
# The recreated seafile container may have a new IP, and nginx resolved the static
# `upstream seafile` when it loaded. Reload, or the edge keeps proxying to the old IP (502).
dc exec nginx nginx -t && dc exec nginx nginx -s reload
for i in $(seq 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' seafile)" = healthy ] && break; sleep 5; done
docker inspect -f '{{.State.Health.Status}}' seafile      # healthy
```

If seahub logs a cache or redis error: `docker exec seafile-redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'` should print `PONG`, and
`docker exec seafile env | grep -E '^(CACHE_PROVIDER|REDIS_HOST)='` should show redis / seafile-redis.

---

## 6. Final verification (13.0)

```bash
dc ps seafile seafile-notification seafile-redis seafile-db     # all Up; seafile (healthy)
curl -sI https://files.markcheli.com/ | head -1                  # 302 (to /accounts/login/)
curl -s -o /dev/null -w '%{http_code}\n' https://files.markcheli.com/accounts/login/   # 200
curl -s -w ' %{http_code}\n' https://files.markcheli.com/notification/ping             # {"ret": "pong"} 200
curl -s -w ' %{http_code}\n' https://files.markcheli.com/seafhttp/protocol-version     # 200
q "SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo UNION ALL SELECT 'branches',COUNT(*) FROM seafile_db.Branch UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2"   # = baseline
```

**API upload/download round trip.** This uses a temporary library that the test deletes afterwards. The password is read without echoing.

```bash
U=<admin email>; read -rsp 'Seafile password: ' PW; echo
TOKEN=$(curl -s -d "username=$U" --data-urlencode "password=$PW" https://files.markcheli.com/api2/auth-token/ | jq -r .token); unset PW
H="Authorization: Token $TOKEN"; B=https://files.markcheli.com
curl -s -H "$H" $B/api2/server-info/ | jq -r .version              # 13.0.28
curl -s -H "$H" $B/api2/repos/ | jq -r '.[].name'                 # the 3 libraries
R=$(curl -s -H "$H" -d name=upgrade-test-$TS $B/api2/repos/ | jq -r .repo_id)
head -c 5M /dev/urandom > /tmp/sf-test.bin
UP=$(curl -s -H "$H" "$B/api2/repos/$R/upload-link/" | tr -d '"')
curl -s -H "$H" -F file=@/tmp/sf-test.bin -F parent_dir=/ "$UP?ret-json=1"; echo
DL=$(curl -s -H "$H" "$B/api2/repos/$R/file/?p=/sf-test.bin" | tr -d '"')
curl -s "$DL" -o /tmp/sf-test.dl
sha256sum /tmp/sf-test.bin /tmp/sf-test.dl                          # identical
curl -s -X DELETE -H "$H" $B/api2/repos/$R/; rm -f /tmp/sf-test.bin /tmp/sf-test.dl
```

Then:

- [ ] **Web:** log in, open a library, preview and download a file. Admin → System Info shows 13.0.28.
      Check the branding (SITE_NAME/CUSTOM_CSS are set in Admin → Settings; the custom CSS may
      need adjusting for the new UI).
- [ ] **Purge the Cloudflare cache** for files.markcheli.com so browsers don't get 11.0 JS/CSS:
      `source venv/bin/activate && python scripts/cloudflare_cache_purge.py` (see `scripts/README.md`).
- [ ] **Desktop client:** resume sync. It should reconnect without a new login (the device tokens
      are preserved). Edit a file in the web UI, and the desktop client should pick it up within a few
      seconds. That's the notification server working; without it, the client falls back to 30 s polling. The
      client log (`~/.ccnet/logs/seafile.log` or `~/Seafile/.seafile-data/logs`) should show a
      notification server connection and no repeated reconnect errors.
- [ ] **iOS:** open the app, browse a library, upload a photo, and turn camera upload back on.
- [ ] **Logs clean:**
      `sudo grep -hiE 'error|traceback|critical' /storage/seafile/seafile/logs/{seahub,seafile,fileserver,seafevents}.log 2>/dev/null | tail -20`,
      `docker logs --since 30m seafile-notification 2>&1 | grep -i error`,
      `docker logs --since 30m nginx 2>&1 | grep files.markcheli.com | grep -E '" 5[0-9]{2} '`
- [ ] Seafile logs are still reaching OpenSearch (logs.ops → container `seafile` / seafile log files).
- [ ] `source venv/bin/activate && python scripts/test_infrastructure.py` (it now expects
      `seafile` healthy, `seafile-redis`, `seafile-notification`, and `/notification/ping` → pong).
- [ ] Uptime Kuma "Seafile" monitor is green.

**Downtime ends here.**

### Finalise

- [ ] Update `docs/DEPLOYMENT_STATUS.md` (Seafile 13.0.28, redis and notification-server entries).
- [ ] Mark `docs/SEAFILE_UPGRADE_RUNBOOK.md` as done or delete it.
- [ ] Keep `~/seafile-upgrade.state` until the snapshots are deleted, because the rollback reads it.
- [ ] Keep `$SNAP` (NAS) and `$LOCAL` (`/storage/seafile-pre13-*`) for **at least 2 weeks**, then
      `sudo rm -rf /storage/seafile-pre13-*`. The NAS copy can stay longer.
- [ ] After 2 stable weeks: follow-up PR removing `seafile-memcached` (13.0 uses redis), its
      `depends_on` entry and its test expectation, then `dc rm -sf seafile-memcached`.
- [ ] Remove the `seafileltd/seafile-mc:11.0.13` and 12.0.x images once the snapshot is retired.

---

## 7. Rollback

Use this if any verification fails and the fix isn't obvious. It restores 11.0.13 exactly as it was at step 2.
Seafile migrations only go forward. **Reverting only the image won't work against a migrated DB.** You must restore the DB
*and* `/storage/seafile` (the conf files and the `current_version` stamp changed).

```bash
# PRELUDE first (it reloads SNAP and LOCAL from ~/seafile-upgrade.state)
# GUARDS: the DROP and the rsync --delete below are destructive. With an empty $LOCAL, the
# rsync would copy / over /storage/seafile. Continue only if this prints GUARDS_OK.
rb=1
[ -n "$SNAP" ] && [ -n "$LOCAL" ] || { echo "!! SNAP/LOCAL unset: check ~/seafile-upgrade.state"; rb=0; }
zcat "$SNAP/seafile-3db.sql.gz" 2>/dev/null | tail -1 | grep -q 'Dump completed' || { echo "!! no usable dump in $SNAP"; rb=0; }
[ "$(sudo cat "$LOCAL/seafile/seafile-data/current_version" 2>/dev/null)" = 11.0.13 ] || { echo "!! $LOCAL is not an 11.0.13 snapshot"; rb=0; }
[ "$rb" = 1 ] && echo GUARDS_OK
```

```bash
# PRELUDE first. Run this only after GUARDS_OK.
dc stop -t 60 seafile-notification seafile
dc rm -f seafile-notification seafile seafile-redis

# 1. DB: drop the three (possibly migrated) DBs, then load the per-DB dump.
#    Grants for the 'seafile' user live in mysql.* and survive DROP DATABASE.
docker exec seafile-db sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS ccnet_db; DROP DATABASE IF EXISTS seafile_db; DROP DATABASE IF EXISTS seahub_db;"'
zcat "$SNAP/seafile-3db.sql.gz" | docker exec -i seafile-db sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'

# 2. Data + conf + version stamp
sudo rsync -aHAX --numeric-ids --delete "$LOCAL/" /storage/seafile/
#    (if $LOCAL is unusable: sudo rm -rf /storage/seafile && sudo tar --numeric-owner -xpf "$SNAP/seafile-shared.tar" -C /storage)
sudo cat /storage/seafile/seafile/seafile-data/current_version     # 11.0.13

# 3. Code: restore the pre-upgrade compose + nginx files
git checkout "$(cat "$SNAP/git-head")" -- docker-compose.yml infrastructure/nginx/conf.d/production.conf scripts/test_infrastructure.py
rm -f ~/seafile-upgrade.hop12; unset SEAFILE_IMAGE SEAFILE_NOTIFICATION_IMAGE
dc up -d seafile
dc exec nginx nginx -t && dc exec nginx nginx -s reload

# 4. Verify, same as 4c, against 11.0 (and compare counts with $SNAP/baseline.txt)
curl -s -o /dev/null -w '%{http_code}\n' https://files.markcheli.com/accounts/login/   # 200
curl -s -w ' %{http_code}\n' https://files.markcheli.com/notification/ping             # pong 200
```

Afterwards the working tree has those three files checked out at the old commit. Open a revert PR so
`main` matches, and leave the three `.env` values in place (they're harmless). If the DB import fails
partway, the `--all-databases` dump is the fallback. Import it the same way after the DROPs; it
also rewrites `mysql.*` with the same users.

**Rollback timing:** about 10–15 minutes (the data is only 3.4 GB on the same disk).

### Point of no return

Until **step 6 is signed off and clients resume syncing**, rollback loses nothing: the server took
no writes after the snapshot. Once desktop or iOS clients sync against 13.0, a rollback discards every
change made since step 2. Clients that synced against 13.0 might then see their libraries as
"ahead" of the server and need to be re-synced (remove the library locally and sync it again). So: test fully
in step 6 **before** resuming the clients. After that, fix forward unless the data is at risk.

---

## Downtime

| Phase | Estimate |
|---|---|
| 2: stop, baseline, DB dumps + restore test | 5 min |
| 2c/2d: tarball to NAS (3.4 GB over SMB) + local rsync + verify | 5–10 min |
| 3: pull + config check | 1 min |
| 4: hop to 12.0 (migration on a 74 MB DB) + verify | 8–10 min |
| 5: hop to 13.0 + verify | 8–10 min |
| 6: final verification and client checks | 10 min |
| **Total user-visible downtime** | **about 40–50 min** (book 90 min; add 15 min if you roll back) |

Images are pre-pulled in 1b. Without that, add about 5 minutes per hop.

## Things only Mark can do / decide

- Pause the desktop client and iOS camera upload before the window, and resume them after step 6.
- Web: you may have to log in again after the upgrade (Django 4.2 → 5.2). Desktop and iOS shouldn't need it,
  because their device tokens are kept and the JWT key is unchanged. If a client keeps reporting auth
  errors, sign it out and back in.
- Recommended: update the desktop client to the current 9.x and the iOS app to the latest App Store version.
  Older clients sync, but real-time notifications need a recent client.
- Admin → Settings: re-check the branding (CUSTOM_CSS) against the 13.0 UI.
- Not deployed, and decide later if wanted: SeaDoc 2.0 (online `.sdoc`/whiteboard editing), the thumbnail
  server (video thumbnails), the metadata server (extended properties/tags; the old file tags feature shows an
  upgrade notice instead), and SeaSearch/AI (Pro or extra services). Each one is a separate container
  plus an edge route.
- Out of scope here, but on the same list: `mariadb:10.11` should be re-pulled (the tag was rebuilt 2026-10-27, which fixes
  CVE-2025-15467 in the DB image). Do it as a separate change, not in this window.

## References

- Docker upgrade guide: https://manual.seafile.com/13.0/upgrade/upgrade_docker/
- 12.0 notes: https://manual.seafile.com/12.0/upgrade/upgrade_notes_for_12.0.x/
- 13.0 notes: https://manual.seafile.com/13.0/upgrade/upgrade_notes_for_13.0.x/
- Notification server: https://manual.seafile.com/13.0/extension/notification-server/
- Reference compose: https://manual.seafile.com/13.0/repo/docker/ce/seafile-server.yml
- Image upgrade logic: https://github.com/haiwen/seafile-docker/blob/master/scripts/scripts_13.0/upgrade.py
