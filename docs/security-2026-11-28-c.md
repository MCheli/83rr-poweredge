# Security sweep 2026-11-28, PR C: database containers (runbook, needs Mark's yes)

**Scope:** `seafile-db` (MariaDB 10.11.19 → 10.11.20), `opensearch` 3.9.0 → 3.10.1, `opensearch-dashboards` 3.9.0 → 3.10.0.
**Order:** last, after PR A and PR B are deployed and settled, and **only once Mark has approved it**.
**Downtime:**
- Seafile errors for 1–2 minutes while the DB container is recreated.
- OpenSearch and Dashboards are down while the volume is tarred, which takes minutes to tens of minutes depending on its
  size (step 0 measures it). Fluent Bit buffers in the meantime, and OpenSearch alerting is paused.

Avoid 02:00 ET (the nightly backup) and 19:40–20:10 ET (Seafile's log rotation).

**One-way:** once OpenSearch 3.10 writes to `opensearch_data`, 3.9 can't open it again. The only rollback is the
step 2 tarball. MariaDB 10.11.19 ↔ 10.11.20 is a same-series patch, so the datadir format doesn't change and
the image can be swapped back. The dumps are there in case it can't.

Pins checked against Docker Hub on 2026-11-28. Each is the tag's multi-arch index. The image ID is the linux/amd64 config digest:

| Image | Pin (index) | amd64 image ID | Upstream |
|---|---|---|---|
| `mariadb:10.11.20` | `sha256:aed943ea…8738` | `sha256:84b16fe5…f31d` | GA 2026-11-16, 13 CVEs; Docker Hub push 2026-11-28 |
| `opensearchproject/opensearch:3.10.1` | `sha256:02358b2b…f464` | `sha256:e4a2c787…e28d` | 2026-11-24; one bug fix, JDK 25.0.5.1, Reactor Netty 1.3.9 |
| `opensearchproject/opensearch-dashboards:3.10.0` | `sha256:90e839fc…bcf1` | `sha256:683c58d6…8cf5` | image 2026-11-17, release notes 2026-11-27; no breaking changes |

OpenSearch 3.10.0's breaking changes remove only the experimental Views feature and the macOS/x64 archives, and neither is used here.
The OpenSearch healthchecks use `curl` from the Amazon Linux base image, as 3.9.0 does. MariaDB has no compose healthcheck
(the runbook uses the image's `healthcheck.sh`).

## Conventions

- Run on 83rr-poweredge as `mcheli` in **bash** (type `bash` first: the login shell is zsh). Start every block with
  the PRELUDE. State lives in `$S`. Lines starting with `!!` mean stop. Every wait is bounded.
- Each service starts with a `--dry-run` block of its own. If it would **create a volume**, stop.

```bash
# PRELUDE (bash)
cd ~/83rr-poweredge
BK=/data/backups/2026-11-28; NAS=/mnt/nas/83rr-backup/pre-upgrade-2026-11-28; S=$BK/state-c.env
mkdir -p "$BK"; [ -f "$S" ] && . "$S"; [ -f ~/rollback-2026-11-28-c.env ] && . ~/rollback-2026-11-28-c.env
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml ${RB_OVERRIDE:+-f "$RB_OVERRIDE"} "$@"; }
q() { docker exec seafile-db sh -c "exec mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"$1\""; }
COUNT_SQL="SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo UNION ALL SELECT 'tokens',COUNT(*) FROM seahub_db.api2_tokenv2"
dryrun() { local out; out=$(dc --dry-run up -d --no-deps "$@" 2>&1); printf '%s\n' "$out"
  if printf '%s\n' "$out" | grep -qiE 'volume.*creat'; then echo "!! STOP: the dry run would create a volume"; return 1; fi
  printf '%s\n' "$out" | grep -qiE 'network.*creat' && echo "!! the dry run would create a network: check the project name"
  echo "OK dry run: no new volume"; }
keep_old() { local v id; v=OLD_$(printf %s "$1" | tr 'a-z-' 'A-Z_')
  if grep -q "^$v=" "$S" 2>/dev/null; then echo "OK $v already recorded, not overwritten"
  else docker inspect -f '{{.Config.Image}}' "$1" | grep -qF ":$3@" || { echo "!! $1 is not running $3: stop"; return 1; }
       id=$(docker inspect -f '{{.Image}}' "$1") && docker tag "$id" "$2" && echo "$v=$id" >> "$S"; fi
  . "$S"; [ "$(docker image inspect -f '{{.Id}}' "$2" 2>/dev/null)" = "${!v}" ] && echo "OK rollback tag $2 = ${!v}" || echo "!! rollback tag $2 missing or wrong"; }
wait_healthy() { local s i; for i in $(seq 1 $(( $2 / 5 ))); do
    s=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null)
    case $s in healthy) echo "OK $1 healthy after $((i*5))s"; return 0;; esac; sleep 5; done
  echo "!! $1 not healthy after $2 s (last: $s): see Rollback"; return 1; }
db_up() { local i; for i in $(seq 1 36); do docker exec seafile-db healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1 \
    && { echo "OK seafile-db up after $((i*5))s"; return 0; }; sleep 5; done; echo "!! seafile-db not up after 3 min: see Rollback"; return 1; }
nas_copy() { mountpoint -q /mnt/nas || { echo "!! NAS not mounted: stop (sudo mount /mnt/nas)"; return 1; }
  mkdir -p "$NAS" && cp "$1" "$NAS/" && [ "$(sha256sum < "$1")" = "$(sha256sum < "$NAS/${1##*/}")" ] \
    && echo "OK NAS copy $NAS/${1##*/}" || { echo "!! NAS copy of $1 failed"; return 1; }; }
```

## 0. Prepare

```bash
# PRELUDE first
git status --porcelain | grep -v '^??' && echo "!! tracked changes in the checkout: stop"
grep -q '^HEAD0=' "$S" 2>/dev/null || echo "HEAD0=$(git rev-parse HEAD)" >> "$S"
git pull --ff-only
dc config --images | grep -E 'mariadb|opensearch'          # 10.11.20, 3.10.1, dashboards 3.10.0
dc pull seafile-db opensearch opensearch-dashboards
docker run --rm -v 83rr-poweredge_opensearch_data:/d:ro --entrypoint du opensearchproject/opensearch:3.10.1 -sh /d   # volume size
df -h /data /mnt/nas                                       # both need room for that size (compressed, usually less)
```

## 1. seafile-db (MariaDB)

```bash
# PRELUDE first
dryrun seafile-db                                          # only seafile-db (Recreate)
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old seafile-db mariadb:rollback-10.11.19 10.11.19
q "SELECT VERSION()"                                       # 10.11.19-MariaDB-…
if [ ! -f "$BK/seafile-alldb.sql.gz" ]; then
  docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
    --routines --triggers --events --all-databases' | gzip > "$BK/seafile-alldb.sql.gz.part" && command mv -f "$BK/seafile-alldb.sql.gz.part" "$BK/seafile-alldb.sql.gz"
  docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
    --routines --triggers --events --databases ccnet_db seafile_db seahub_db' | gzip > "$BK/seafile-db-3db.sql.gz.part" && command mv -f "$BK/seafile-db-3db.sql.gz.part" "$BK/seafile-db-3db.sql.gz"
  q "$COUNT_SQL" > "$BK/seafile-db-baseline.txt"
fi
for f in "$BK/seafile-alldb.sql.gz" "$BK/seafile-db-3db.sql.gz"; do
  gzip -t "$f" && zcat "$f" | tail -1 | grep -q 'Dump completed' && echo "OK $f $(du -h "$f" | cut -f1)" || echo "!! BAD $f: stop"
  nas_copy "$f"
done
[ "$(zcat "$BK/seafile-db-3db.sql.gz" | grep -cE '^CREATE DATABASE')" = 3 ] && echo "OK 3 databases" || echo "!! dump doesn't hold 3 databases"
command cat "$BK/seafile-db-baseline.txt"
```

```bash
# PRELUDE first. Only after every line above says OK. Seafile errors from here.
dc up -d --no-deps seafile-db
db_up
q "SELECT VERSION()"                                       # 10.11.20-MariaDB-…
for i in $(seq 1 24); do c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' https://files.markcheli.com/api2/ping/); [ "$c" = 200 ] && break; sleep 5; done
echo "ping $c"                                             # 200. If not: dc restart seafile seafile-notification, wait_healthy seafile 300, then the reload below
dc exec nginx nginx -t && dc exec nginx nginx -s reload
q "$COUNT_SQL" | diff - "$BK/seafile-db-baseline.txt" && echo "OK counts match"
docker logs --since 10m seafile-db 2>&1 | grep -E '\[ERROR\]' | tail -5   # nothing
```

## 2. OpenSearch (one-way: tarball first)

```bash
# PRELUDE first
dryrun opensearch                                          # only opensearch, no volume created
```

```bash
# PRELUDE first. Only after "OK dry run". OpenSearch and Dashboards are down from here.
keep_old opensearch opensearchproject/opensearch:rollback-3.9.0 3.9.0
keep_old opensearch-dashboards opensearchproject/opensearch-dashboards:rollback-3.9.0 3.9.0
docker exec opensearch curl -s localhost:9200/_cluster/health > "$BK/opensearch-health-before.json"; command cat "$BK/opensearch-health-before.json"
docker exec opensearch curl -s 'localhost:9200/_cat/indices?h=index,docs.count&s=index' > "$BK/opensearch-indices-before.txt"
dc stop opensearch-dashboards opensearch
if [ ! -f "$BK/opensearch_data.tgz" ]; then
  docker run --rm -u 0 --entrypoint sh -v 83rr-poweredge_opensearch_data:/src:ro -v "$BK":/dst opensearchproject/opensearch:rollback-3.9.0 \
    -c "tar -C /src -czf /dst/opensearch_data.tgz.part . && chown $(id -u):$(id -g) /dst/opensearch_data.tgz.part" \
  && gzip -t "$BK/opensearch_data.tgz.part" && tar -tzf "$BK/opensearch_data.tgz.part" | grep -q '/_state/' \
  && command mv -f "$BK/opensearch_data.tgz.part" "$BK/opensearch_data.tgz"
fi
[ -f "$BK/opensearch_data.tgz" ] && echo "OK opensearch_data.tgz $(du -h "$BK/opensearch_data.tgz" | cut -f1)" || echo "!! BAD opensearch backup: dc start opensearch opensearch-dashboards and stop"
nas_copy "$BK/opensearch_data.tgz"
```
If either line says `!!`, run `dc start opensearch opensearch-dashboards` (still 3.9.0, nothing has changed) and stop here.

```bash
# PRELUDE first. Only after both OK lines. From here, 3.9.0 can't read the volume.
dc up -d --no-deps opensearch
wait_healthy opensearch 600
docker exec opensearch curl -s localhost:9200 | grep '"number"'            # 3.10.1
docker exec opensearch curl -s localhost:9200/_cluster/health              # green or yellow, as before
docker exec opensearch curl -s 'localhost:9200/_cat/indices?h=index,docs.count&s=index' | diff - "$BK/opensearch-indices-before.txt" | head   # only today's index growing
```

## 3. OpenSearch Dashboards

```bash
# PRELUDE first
dryrun opensearch-dashboards
```

```bash
# PRELUDE first. Only after "OK dry run".
dc up -d --no-deps opensearch-dashboards
wait_healthy opensearch-dashboards 300
curl -s -m 10 -o /dev/null -w 'logs %{http_code}\n' https://logs.ops.markcheli.com/app/home   # 200 (from the LAN)
ix() { docker exec opensearch curl -s 'localhost:9200/_cat/indices?h=index,docs.count&s=index' | tail -3; }
ix; sleep 120; ix                                                          # the newest index's count rises: Fluent Bit is shipping again
dc logs --since 10m fluent-bit 2>&1 | grep -iE 'error|retry' | tail -5    # retries only during the downtime
```
Then open Alerting in Dashboards and check that the monitors are enabled and have run since the restart.

## 4. Finish

`make health`. After a week, `docker rmi` the three `rollback` tags. Keep `$BK` (and the NAS copy of
`opensearch_data.tgz`) until the nightly backups have rotated (7 days).

## Rollback

Set the override once, with only the services being rolled back. The PRELUDE keeps loading it until the revert PR is pulled.
Calls that skip the PRELUDE (`make up`, a plain `docker compose up`) bring the new images back.

```bash
# PRELUDE first
printf 'services:\n  seafile-db:\n    image: mariadb:rollback-10.11.19\n  opensearch:\n    image: opensearchproject/opensearch:rollback-3.9.0\n  opensearch-dashboards:\n    image: opensearchproject/opensearch-dashboards:rollback-3.9.0\n' > ~/rollback-2026-11-28-c.yml
echo "RB_OVERRIDE=$HOME/rollback-2026-11-28-c.yml" > ~/rollback-2026-11-28-c.env
```

- **seafile-db:** `dc up -d --no-deps seafile-db && db_up && q "SELECT VERSION()"` (expect 10.11.19), then the
  ping and nginx reload from step 1. If 10.11.19 won't start or the data is wrong, follow section 6b of
  `docs/seafile-db-mariadb-10.11.19.md` with `$BK/seafile-db-3db.sql.gz`.
- **opensearch** (restoring the tarball is mandatory, because 3.9.0 can't open 3.10 data). Writes since step 2 are lost:
  ```bash
  # PRELUDE first
  gzip -t "$BK/opensearch_data.tgz" && docker image inspect opensearchproject/opensearch:rollback-3.9.0 >/dev/null && echo GUARDS_OK
  # only after GUARDS_OK:
  dc stop opensearch-dashboards opensearch
  docker run --rm -u 0 --entrypoint sh -v 83rr-poweredge_opensearch_data:/dst -v "$BK":/src:ro opensearchproject/opensearch:rollback-3.9.0 \
    -c 'find /dst -mindepth 1 -delete && tar -C /dst -xzf /src/opensearch_data.tgz'
  dc up -d --no-deps opensearch && wait_healthy opensearch 600
  dc up -d --no-deps opensearch-dashboards && wait_healthy opensearch-dashboards 300
  ```
- **opensearch-dashboards alone:** it keeps no state of its own, so `dc up -d --no-deps opensearch-dashboards` with the override is enough. It must
  match OpenSearch's major.minor, so roll it back only together with OpenSearch, or keep 3.10.0 if OpenSearch stays on 3.10.1.
