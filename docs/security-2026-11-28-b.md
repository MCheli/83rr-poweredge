# Security sweep 2026-11-28, PR B: stateful app bumps (runbook)

**Scope:** `ntfy` v2.37.2 → v2.38.3, `grafana` 13.3.1 → 13.3.2, `seafile` (seafile-mc) 13.0.29 → 13.0.30.
`seafile-notification` stays on 13.0.29.
**Order:** after PR A (`docs/security-2026-11-28-a.md`), before PR C. Each service is backed up first.
**Downtime:** ntfy and grafana each go down for under a minute, while their volume is tarred and the container
is recreated. Seafile gives 2–3 minutes of 502. Book 45 minutes in total. Avoid 02:00 ET (the nightly backup)
and 19:40–20:10 ET (Seafile's log rotation).

Pins checked against Docker Hub on 2026-11-28. Each is the tag's multi-arch index. The image ID is the linux/amd64
config digest, which is what `docker inspect -f '{{.Image}}'` shows once the container runs:

| Image | Pin (index) | amd64 image ID |
|---|---|---|
| `binwiederhier/ntfy:v2.38.3` | `sha256:874299b2…ea51` | `sha256:98297573…a21c` |
| `grafana/grafana:13.3.2` | `sha256:81556409…5101` | `sha256:a9f7f54e…5238` |
| `seafileltd/seafile-mc:13.0.30` | `sha256:92df4680…cc1f` | `sha256:fd87f8e8…e3be1` |

Healthcheck tools are unchanged: ntfy and grafana use `wget` (Alpine busybox; grafana also installs curl), and seafile uses `curl` (installed in the image).

Notes:
- **ntfy v2.38.3** deletes stored web push subscriptions that fail its new endpoint check. `server.yml` has no
  `web-push-*` settings, so there are none here. The release notes list no schema change. The tarball is the rollback anyway.
- **grafana 13.3.2** is a patch release in 13.3 (two CVE fixes plus one provisioning fix). No migration is expected.
- **seafile 13.0.30**: the image's start logic sees the same major version and runs only `minor-upgrade.sh`, the same as
  the 13.0.29 upgrade (`docs/seafile-upgrade-13.0.29.md` section 0). The upstream changelog moved to the Seafile wiki and
  wasn't read for this review, so step 3 diffs the schema and Django migrations to confirm that nothing touched the DB.

## Conventions

- Run on 83rr-poweredge as `mcheli` in **bash** (type `bash` first: the login shell is zsh, which doesn't
  word-split `$VARS` and aliases `cat` to `cat -n`). Start every block with the PRELUDE. State lives in `$S`.
- Lines starting with `!!` mean stop. Every wait is bounded.
- Each service starts with a `--dry-run` block of its own. If it would **create a volume**, stop: the
  real run would start the service on an empty volume.

```bash
# PRELUDE (bash)
cd ~/83rr-poweredge
BK=/data/backups/2026-11-28; NAS=/mnt/nas/83rr-backup/pre-upgrade-2026-11-28; S=$BK/state-b.env
mkdir -p "$BK"; [ -f "$S" ] && . "$S"; [ -f ~/rollback-2026-11-28-b.env ] && . ~/rollback-2026-11-28-b.env
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml ${RB_OVERRIDE:+-f "$RB_OVERRIDE"} "$@"; }
q() { docker exec seafile-db sh -c "exec mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"$1\""; }
SCHEMA_SQL="SELECT table_schema,table_name,column_name,column_type FROM information_schema.columns WHERE table_schema IN ('ccnet_db','seafile_db','seahub_db') ORDER BY 1,2,ordinal_position"
MIGR_SQL="SELECT app,name FROM seahub_db.django_migrations ORDER BY id"
dryrun() { local out; out=$(dc --dry-run up -d --no-deps "$@" 2>&1); printf '%s\n' "$out"
  if printf '%s\n' "$out" | grep -qiE 'volume.*creat'; then echo "!! STOP: the dry run would create a volume"; return 1; fi
  printf '%s\n' "$out" | grep -qiE 'network.*creat' && echo "!! the dry run would create a network: check the project name"
  echo "OK dry run: no new volume"; }
# keep_old <container> <rollback tag> <old version string>: tags the running image once, never overwrites
keep_old() { local v id; v=OLD_$(printf %s "$1" | tr 'a-z-' 'A-Z_')
  if grep -q "^$v=" "$S" 2>/dev/null; then echo "OK $v already recorded, not overwritten"
  else docker inspect -f '{{.Config.Image}}' "$1" | grep -qF ":$3@" || { echo "!! $1 is not running $3: stop"; return 1; }
       id=$(docker inspect -f '{{.Image}}' "$1") && docker tag "$id" "$2" && echo "$v=$id" >> "$S"; fi
  . "$S"; [ "$(docker image inspect -f '{{.Id}}' "$2" 2>/dev/null)" = "${!v}" ] && echo "OK rollback tag $2 = ${!v}" || echo "!! rollback tag $2 missing or wrong"; }
wait_healthy() { local s i; for i in $(seq 1 $(( $2 / 5 ))); do
    s=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null)
    case $s in healthy) echo "OK $1 healthy after $((i*5))s"; return 0;; esac; sleep 5; done
  echo "!! $1 not healthy after $2 s (last: $s): see Rollback"; return 1; }
nas_copy() { mountpoint -q /mnt/nas || { echo "!! NAS not mounted: stop (sudo mount /mnt/nas)"; return 1; }
  mkdir -p "$NAS" && cp "$1" "$NAS/" && [ "$(sha256sum < "$1")" = "$(sha256sum < "$NAS/${1##*/}")" ] \
    && echo "OK NAS copy $NAS/${1##*/}" || { echo "!! NAS copy of $1 failed"; return 1; }; }
# voltar <volume> <image with tar> <out.tgz> <file that must be in it>: tars a STOPPED service's volume
voltar() { [ -f "$3" ] && { echo "OK $3 exists from an earlier run, not overwritten"; return 0; }
  docker volume inspect "$1" >/dev/null || { echo "!! volume $1 not found: stop"; return 1; }
  docker run --rm -u 0 --entrypoint sh -v "$1":/src:ro -v "$BK":/dst "$2" \
    -c "tar -C /src -czf /dst/${3##*/}.part . && chown $(id -u):$(id -g) /dst/${3##*/}.part" \
  && gzip -t "$3.part" && tar -tzf "$3.part" | grep -qx "./$4" && command mv -f "$3.part" "$3" \
  && echo "OK $3 $(du -h "$3" | cut -f1)" || { echo "!! BAD backup of $1 (no ./$4): stop"; return 1; }; }
```

## 0. Prepare

```bash
# PRELUDE first
git status --porcelain | grep -v '^??' && echo "!! tracked changes in the checkout: stop"
grep -q '^HEAD0=' "$S" 2>/dev/null || echo "HEAD0=$(git rev-parse HEAD)" >> "$S"
git pull --ff-only
dc config --images | grep -E 'ntfy|grafana/grafana|seafile-mc'   # v2.38.3, 13.3.2, 13.0.30 (an old SEAFILE_IMAGE in .env would show here)
dc pull ntfy grafana seafile
mountpoint -q /mnt/nas && echo "OK NAS mounted" || echo "!! NAS not mounted"
```

## 1. ntfy

```bash
# PRELUDE first
dryrun ntfy
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old ntfy binwiederhier/ntfy:rollback-v2.37.2 v2.37.2
dc stop ntfy
voltar 83rr-poweredge_ntfy_data binwiederhier/ntfy:rollback-v2.37.2 "$BK/ntfy_data.tgz" user.db && nas_copy "$BK/ntfy_data.tgz"
```
If either line says `!!`, run `dc start ntfy` and stop here.

```bash
# PRELUDE first. Only after both OK lines.
dc up -d --no-deps ntfy
wait_healthy ntfy 120
dc logs --since 5m ntfy 2>&1 | grep -iE 'error|migrat|fatal' | tail -10       # no errors
docker exec ntfy wget -qO- http://localhost/v1/health                         # {"healthy":true}
docker exec ntfy ntfy --version 2>&1 | head -1                                # ntfy 2.38.3
```
Send a test alert to topic `homelab`, the same way `infrastructure/opensearch/config/alerting/README.md` does, and check that it reaches the phone.

## 2. grafana

```bash
# PRELUDE first
dryrun grafana
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old grafana grafana/grafana:rollback-13.3.1 13.3.1
dc stop grafana                                                     # stopped, so SQLite is consistent
voltar 83rr-poweredge_grafana_data grafana/grafana:rollback-13.3.1 "$BK/grafana_data.tgz" grafana.db && nas_copy "$BK/grafana_data.tgz"
```
If either line says `!!`, run `dc start grafana` and stop here.

```bash
# PRELUDE first. Only after both OK lines.
dc up -d --no-deps grafana
wait_healthy grafana 300
docker exec grafana wget -qO- http://localhost:3000/api/health      # "version": "13.3.2", "database": "ok"
dc logs --since 10m grafana 2>&1 | grep -iE 'level=error|migration.*(fail|error)' | tail -10   # nothing
curl -s -m 10 -o /dev/null -w 'dashboard %{http_code}\n' https://dashboard.ops.markcheli.com/login   # 200 (from the LAN)
```

## 3. seafile

Tell the desktop clients to pause sync until the checks pass.

```bash
# PRELUDE first
dryrun seafile                                                      # only seafile (Recreate)
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old seafile seafileltd/seafile-mc:rollback-13.0.29 13.0.29
docker exec seafile cat /shared/seafile/seafile-data/current_version          # 13.0.29
if [ ! -f "$BK/seafile-3db.sql.gz" ]; then
  docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
    --routines --triggers --events --databases ccnet_db seafile_db seahub_db' | gzip > "$BK/seafile-3db.sql.gz.part" \
  && command mv -f "$BK/seafile-3db.sql.gz.part" "$BK/seafile-3db.sql.gz"
  docker exec seafile tar -C /shared/seafile -czf - conf > "$BK/seafile-conf.tgz"
  q "$SCHEMA_SQL" > "$BK/seafile-schema.txt"; q "$MIGR_SQL" > "$BK/seafile-migrations.txt"
fi
f=$BK/seafile-3db.sql.gz
gzip -t "$f" && zcat "$f" | tail -1 | grep -q 'Dump completed' && [ "$(zcat "$f" | grep -cE '^CREATE DATABASE')" = 3 ] \
  && echo "OK dump $(du -h "$f" | cut -f1) (about 20 MB expected)" || echo "!! BAD dump: stop"
gzip -t "$BK/seafile-conf.tgz" && tar -tzf "$BK/seafile-conf.tgz" | grep -q 'conf/seahub_settings.py' && echo "OK conf tarball" || echo "!! BAD conf tarball: stop"
echo "OK schema $(wc -l < "$BK/seafile-schema.txt") columns, $(wc -l < "$BK/seafile-migrations.txt") migrations"
nas_copy "$f" && nas_copy "$BK/seafile-conf.tgz"
```

```bash
# PRELUDE first. Only after every line above says OK. 502 from here until healthy.
grep -q '^SF_T0=' "$S" || echo "SF_T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$S"; . "$S"
dc up -d --no-deps seafile
wait_healthy seafile 300
docker exec seafile cat /shared/seafile/seafile-data/current_version          # 13.0.30
docker logs --since "$SF_T0" seafile 2>&1 | grep -iE 'upgrade|traceback|error' | tail -10   # minor-upgrade only
dc exec nginx nginx -t && dc exec nginx nginx -s reload                       # the static upstream holds the old container IP
q "$SCHEMA_SQL" | diff - "$BK/seafile-schema.txt" >/dev/null && echo "OK schema unchanged" || echo "!! SCHEMA CHANGED: a rollback must restore the dump"
q "$MIGR_SQL" | diff - "$BK/seafile-migrations.txt" >/dev/null && echo "OK no new migrations" || echo "!! NEW MIGRATIONS: a rollback must restore the dump"
for u in accounts/login/ api2/ping/ seafhttp/protocol-version notification/ping; do
  printf '%s %s\n' "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://files.markcheli.com/$u")" "$u"; done   # all 200
curl -s -m 10 https://files.markcheli.com/api2/server-info/ | grep -o '"version": "[^"]*"'   # 13.0.30
```
Then resume the desktop clients. Edit a file in the web UI, and the client should pick it up within seconds.

## 4. Finish

`make health`, plus 10 minutes of watching `docker ps` for restarts on ntfy, grafana and seafile. After a week,
`docker rmi` the three `rollback` tags. Keep `$BK` until the nightly backups have rotated (7 days).

## Rollback (per service)

The override file pins only the services you roll back. The PRELUDE loads it, so every later `dc` call keeps
those services on their old images until the revert PR is merged and pulled. **Calls that skip the PRELUDE
(`make up`, a plain `docker compose up`) bring the new image back.** Once the revert is pulled, delete
`~/rollback-2026-11-28-b.env` and `~/rollback-2026-11-28-b.yml`.

```bash
# PRELUDE first. Write the override once, with only the services being rolled back (delete the others' lines).
printf 'services:\n  ntfy:\n    image: binwiederhier/ntfy:rollback-v2.37.2\n  grafana:\n    image: grafana/grafana:rollback-13.3.1\n  seafile:\n    image: seafileltd/seafile-mc:rollback-13.0.29\n' > ~/rollback-2026-11-28-b.yml
echo "RB_OVERRIDE=$HOME/rollback-2026-11-28-b.yml" > ~/rollback-2026-11-28-b.env
```

- **ntfy** (restore the data too):
  ```bash
  # PRELUDE first
  gzip -t "$BK/ntfy_data.tgz" && docker image inspect binwiederhier/ntfy:rollback-v2.37.2 >/dev/null && echo GUARDS_OK
  # only after GUARDS_OK:
  dc stop ntfy
  docker run --rm -u 0 --entrypoint sh -v 83rr-poweredge_ntfy_data:/dst -v "$BK":/src:ro binwiederhier/ntfy:rollback-v2.37.2 \
    -c 'find /dst -mindepth 1 -delete && tar -C /dst -xzf /src/ntfy_data.tgz'
  dc up -d --no-deps ntfy && wait_healthy ntfy 120
  ```
- **grafana:** first try the image alone: `dc up -d --no-deps grafana && wait_healthy grafana 300`. If 13.3.1 won't
  start on the data, restore `grafana_data.tgz` the same way as ntfy (volume `83rr-poweredge_grafana_data`).
- **seafile:** `dc up -d --no-deps seafile && wait_healthy seafile 300`, then `dc exec nginx nginx -s reload`. If step 3
  printed `!! SCHEMA CHANGED` or `!! NEW MIGRATIONS`, also restore the dump, following section 6b of
  `docs/seafile-upgrade-13.0.29.md` with `$BK/seafile-3db.sql.gz`.
