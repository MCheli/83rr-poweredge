# Seafile patch runbook: seafile-mc 13.0.28 → 13.0.29, notification-server 13.0.21 → 13.0.29 (November 2026)

**Status:** planned (PR `upgrade/seafile-13.0.29`). Not deployed.
**Why:** `seafile` is internet-facing at files.markcheli.com. Dependency-Track triage (round 5, 2026-11-05)
measured that 13.0.29 clears about **17 critical / 98 high** on `seafile`. They come from Pillow 11.3.0 → 13.0.0
(×64), PyJWT → 2.15.1 (×26), curl (×13), cryptography, cairosvg, pyasn1 and openssl
3.0.13-0ubuntu3.15 → …3.16 (CVE-2026-84782). It clears another **0 C / 5 H** on `seafile-notification`.
13.0.29 is itself a security release: upstream fixed an API SQL injection, an SSRF in md-to-sdoc, XSS,
privilege bypass and a folder-share boundary bypass.
**Expected downtime:** about 2–3 minutes of 502 on files.markcheli.com while `seafile` is recreated and
becomes healthy. During the notification-server restart (seconds), desktop clients fall back to polling.
Book 30 minutes in total, backups included.
**Scope:** only `seafile` and `seafile-notification` are recreated (`--no-deps`). `seafile-db`,
`seafile-redis` and `seafile-memcached` keep running.
**Watchtower:** neither service has a `com.centurylinklabs.watchtower.enable` label, and watchtower only
acts on labelled containers. Merging this PR deploys nothing. It takes effect only at step 3.

New pins (both multi-arch indexes; amd64 checked against registry-1.docker.io on 2026-11-05):

| Service | Pin | linux/amd64 manifest | amd64 image ID |
|---|---|---|---|
| seafile | `seafileltd/seafile-mc:13.0.29@sha256:9506f49d…c61a` | `sha256:84437e37…f9b` | `sha256:44e51f89…8550` |
| seafile-notification | `seafileltd/notification-server:13.0.29@sha256:5b06f58b…1ccb` | `sha256:ec62a532…a92` | `sha256:10144e6e…a1ba` |

The old pins (rollback): `seafileltd/seafile-mc:13.0.28@sha256:b0c90832126bf432db908449f1bb450211e6bbf75a2193bab3399e2a9636eccf`
(image ID `sha256:d3b8f075…b490`) and `seafileltd/notification-server:13.0.21@sha256:1cac4101d0f4527ad08c00b5452ceb05d790db95d6c8ab6bbace82429c1e5217`
(image ID `sha256:d756e205…9713`). On 2026-11-05 these were the image IDs of the running containers.

---

## 0. Background (read once)

### Is 13.0.29 stable?

- **seafile-mc:** the official CE changelog (https://plus.seafile.com/wiki/publish/seafile-wiki/5L80/,
  linked from manual.seafile.com/13.0/changelog/server-changelog/) lists `13.0.29(2026-11-04)` under the
  13.0 section with no label. That wiki labels pre-releases explicitly (`14.0.9 beta (2026-10-14)`,
  `13.0.11 beta`, …), so an unlabelled entry is a stable release. The Pro changelog and the "Security fixes" wiki page
  also list `13.0.29(2026-11-04)` without a label.
- **notification-server:** upstream publishes no separate changelog. `manual.seafile.com/13.0/changelog/notification-server-changelog/`
  returns 404. The notification server is built from the `notification-server/` directory of
  haiwen/seafile-server and versioned with the server release, and the release tag `v13.0.29-server` exists.
  Docker Hub: `13.0.29-testing` was pushed 2026-11-03. On 2026-11-04 the identical amd64 manifest
  (`ec62a532…`) was promoted to `13.0.29` and `13.0-latest`, alongside the stable seafile-mc 13.0.29. The
  official 13.0 `notification-server.yml` (manual.seafile.com/13.0/repo/docker/) deploys
  `notification-server:13.0-latest`, which is this image. No file under `notification-server/` changed
  between `v13.0.21-server` and `v13.0.29-server`, so for us this image is a rebuild with newer
  dependencies and base image.

### Is there anything beyond pulling the image?

No. What I checked:

- **Release notes (13.0.29):** security fixes, keyboard navigation, OnlyOffice logging and five UI bug fixes.
  There are no upgrade instructions, no config or env changes, and no new settings.
- **Upgrade notes:** manual.seafile.com/13.0/upgrade/upgrade_notes_for_13.0.x/ covers only 12.0 → 13.0.
  upgrade_docker/ says that for a maintenance upgrade you "just download the new image … modify the Seafile
  image version … then start with docker compose up".
- **Image start logic** (`scripts_13.0/upgrade.py`): when `current_version` (13.0.28) and `SEAFILE_VERSION`
  (13.0.29) share the major version, it runs only `upgrade/minor-upgrade.sh` and rewrites the stamp. That
  script (seahub `v13.0.29-server`) runs no SQL and no Django `migrate`, and edits no seafile.conf,
  seahub_settings.py or .env. It only renames gunicorn.conf (already done on 13.0.28), relinks
  avatars/custom media and the `seafile-server-latest` symlink. No `upgrade_13.0_*.sh` script exists.
- **Source diff 13.0.28 → 13.0.29:**
  - seahub has 56 commits. The only dependency change is `requirements.txt` pillow 11.3 → 13.0, and no commit touches
    a migrations directory or SQL file.
  - seafile-server has 6 commits, touching `fileserver/go.mod` and no SQL.

Step 2 still records the schema and the applied Django migrations, and step 4 diffs them. If anything
changed after all, we know it, and the rollback includes the dump restore.

### Conventions

- Run on `83rr-poweredge` in `~/83rr-poweredge`, in **bash**. Start every block with the PRELUDE, so a fresh
  shell (a new SSH session or an agent's tool call) reloads its state from `~/seafile-13029.state`.
- **`cat` is aliased to `cat -n` in the server's zsh.** Pasting a block into zsh by mistake would
  number every line `cat` prints, which breaks comparisons and anything piped. Host-side reads therefore use
  `command cat`, which bypasses aliases. `cat` inside `docker exec` runs in the container, where there is no alias.
- Every compose call goes through `dc`: `-f docker-compose.yml -f docker-compose.prod.yml` explicitly,
  and never the override file.
- Credentials: DB commands run **inside** `seafile-db` and use its own `$MYSQL_ROOT_PASSWORD`. Nothing is
  echoed or put on a host command line.
- Every wait is bounded and prints `OK …` or `!! …`. Lines starting with `!!` mean stop.
- Don't start within 15 minutes of **23:55 UTC** (19:55 ET), when Seafile rotates its logs: step 4's seahub-log
  check counts lines from step 3. Also avoid 02:00 ET, when the nightly backup runs.

```bash
# PRELUDE: run at the top of every block, in bash
cd ~/83rr-poweredge
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }   # never the override file
q() { docker exec seafile-db sh -c "exec mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"$1\""; }
SCHEMA_SQL="SELECT table_schema,table_name,column_name,column_type FROM information_schema.columns WHERE table_schema IN ('ccnet_db','seafile_db','seahub_db') ORDER BY 1,2,ordinal_position"
MIGR_SQL="SELECT app,name FROM seahub_db.django_migrations ORDER BY id"
COUNT_SQL="SELECT 'users',COUNT(*) FROM ccnet_db.EmailUser UNION ALL SELECT 'repos',COUNT(*) FROM seafile_db.Repo UNION ALL SELECT 'branches',COUNT(*) FROM seafile_db.Branch"
[ -f ~/seafile-13029.state ] && . ~/seafile-13029.state        # BK, OLD_SF_ID, OLD_NS_ID, HEAD0 (step 1); T0, SEAHUB_LINES (step 3)
[ -f ~/seafile-13029.rollback ] && . ~/seafile-13029.rollback  # exists only after rollback 6a: keeps the old images pinned
```

---

## 1. Before: record the rollback state (no downtime)

This block is **re-run safe**. The state file and the `-rollback` tags are written only when no state file
exists and both running containers are still the known old images. Pasting it again after step 3 therefore
can't point the rollback at 13.0.29.

```bash
# PRELUDE first
OLD_SF_EXPECT=sha256:d3b8f07584d05a6cc1443bb86b48f916b452bbd49b0d6fea9f127fcf354bb490   # seafile-mc 13.0.28 (amd64)
OLD_NS_EXPECT=sha256:d756e205de28bcb032bd06f35dbd38e77955a2f95a429fae579917b50d269713   # notification-server 13.0.21 (amd64)
git status --porcelain | grep -v '^??' && echo "!! tracked changes in the checkout: stop"
findmnt /mnt/nas >/dev/null && echo "OK NAS mounted" || echo "!! NAS not mounted"
CUR_SF_ID=$(docker inspect seafile --format '{{.Image}}')
CUR_NS_ID=$(docker inspect seafile-notification --format '{{.Image}}')
if [ -f ~/seafile-13029.state ]; then
  echo "!! state file exists from an earlier run: NOT overwritten, tags NOT touched. Check it:"; command cat ~/seafile-13029.state
elif [ "$CUR_SF_ID" != "$OLD_SF_EXPECT" ] || [ "$CUR_NS_ID" != "$OLD_NS_EXPECT" ]; then
  echo "!! running images are not the expected 13.0.28 / 13.0.21 (seafile=$CUR_SF_ID notif=$CUR_NS_ID): nothing written, stop"
else
  BK=/data/backups/seafile-13029-$(date +%Y%m%d)
  OLD_SF_ID=$CUR_SF_ID; OLD_NS_ID=$CUR_NS_ID; HEAD0=$(git rev-parse HEAD)
  printf 'BK=%s\nOLD_SF_ID=%s\nOLD_NS_ID=%s\nHEAD0=%s\n' "$BK" "$OLD_SF_ID" "$OLD_NS_ID" "$HEAD0" > ~/seafile-13029.state
  # keep the old images from being pruned, under names the rollback uses
  docker tag "$OLD_SF_ID" seafileltd/seafile-mc:13.0.28-rollback
  docker tag "$OLD_NS_ID" seafileltd/notification-server:13.0.21-rollback
  echo "OK state written, rollback tags set"; command cat ~/seafile-13029.state
fi
docker exec seafile cat /shared/seafile/seafile-data/current_version          # 13.0.28
# pre-pull the new images (cuts the downtime to the container start)
docker pull seafileltd/seafile-mc:13.0.29@sha256:9506f49d5e5065082c134e6348498eed5a5866ddbd94bd5a3e479a6c285bc61a
docker pull seafileltd/notification-server:13.0.29@sha256:5b06f58b9e67d7429a4ca5488610501b0ebc5286982c2934183d27543ebd1ccb
docker image inspect seafileltd/seafile-mc:13.0.29@sha256:9506f49d5e5065082c134e6348498eed5a5866ddbd94bd5a3e479a6c285bc61a --format '{{.Id}}'                   # sha256:44e51f89…8550
docker image inspect seafileltd/notification-server:13.0.29@sha256:5b06f58b9e67d7429a4ca5488610501b0ebc5286982c2934183d27543ebd1ccb --format '{{.Id}}'          # sha256:10144e6e…a1ba
```

Tell the clients: **pause sync** on the desktop client and hold iOS uploads until step 4 passes. Writes made after the
step 2 dump would be lost if 6b has to restore it.

## 2. Before: back up (gate: everything must print OK)

The dump runs while Seafile is up. `--single-transaction` gives a consistent InnoDB snapshot.

```bash
# PRELUDE first
mkdir -p "$BK"                                   # /data/backups is mcheli-owned; no sudo (it needs a password)
docker exec seafile-db sh -c 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
  --routines --triggers --events --databases ccnet_db seafile_db seahub_db' | gzip > "$BK/seafile-3db.sql.gz"
f="$BK/seafile-3db.sql.gz"
gzip -t "$f" && zcat "$f" | tail -1 | grep -q 'Dump completed' && echo "OK $f $(du -h "$f" | cut -f1)" || echo "!! BAD $f"
[ "$(zcat "$f" | grep -cE '^CREATE DATABASE')" = 3 ] && echo "OK 3 databases" || echo "!! dump doesn't hold 3 databases"
# what step 4 compares against
q "$COUNT_SQL"  > "$BK/baseline.txt"   && command cat "$BK/baseline.txt"
q "$SCHEMA_SQL" > "$BK/schema.txt"     && echo "OK schema: $(wc -l < "$BK/schema.txt") columns"
q "$MIGR_SQL"   > "$BK/migrations.txt" && echo "OK migrations: $(wc -l < "$BK/migrations.txt") applied"   # 83 on 2026-11-05
# Seafile conf (a patch upgrade doesn't touch it, but it's 1 s and makes a restore complete)
docker exec seafile tar -C /shared/seafile -czf - conf > "$BK/seafile-conf.tgz"
tar -tzf "$BK/seafile-conf.tgz" | grep -q 'conf/seahub_settings.py' && echo "OK conf tarball" || echo "!! BAD conf tarball"
# off-host copy, under dated names so the nightly seafile_*.sql.gz rotation can't clash with it
NAS=/mnt/nas/83rr-backup/databases
if findmnt /mnt/nas >/dev/null && [ -d "$NAS" ]; then
  (cd "$BK" && sha256sum seafile-3db.sql.gz seafile-conf.tgz > SHA256SUMS)
  for f in seafile-3db.sql.gz seafile-conf.tgz; do cp "$BK/$f" "$NAS/pre-seafile-13.0.29-${BK##*-}-$f"; done
  (cd "$BK" && sed "s#  #  $NAS/pre-seafile-13.0.29-${BK##*-}-#" SHA256SUMS | sha256sum -c) && echo "OK NAS copy" || echo "!! NAS copy checksum mismatch"
else
  echo "!! NAS NOT MOUNTED: no off-host copy. Stop and fix the mount (or get Mark's OK to continue with the local copy only)"
fi
```

The dump should be about 20 MB compressed, the size of the nightly `seafile_*.sql.gz`. A much smaller file
means something failed. **Gate:** don't continue until every line says `OK`.

## 3. Deploy (downtime starts at `up -d … seafile`)

```bash
# PRELUDE first
[ -f ~/seafile-13029.rollback ] && echo "!! ~/seafile-13029.rollback exists: a rollback is pinned; resolve that first"
git pull --ff-only
[ "$(grep -cE 'seafileltd/(seafile-mc|notification-server):13\.0\.29@sha256:' docker-compose.yml)" = 2 ] && echo "OK new pins present" || echo "!! pins missing: is this PR merged?"
dc config -q && echo "OK compose config"
dc config seafile seafile-notification | grep 'image: seafileltd'      # both 13.0.29@sha256:…
dc config seafile seafile-notification | grep -i watchtower || echo "OK no watchtower label"
# where step 4 starts reading the logs
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SEAHUB_LINES=$(docker exec seafile sh -c 'wc -l < /shared/seafile/logs/seahub.log')
printf 'T0=%s\nSEAHUB_LINES=%s\n' "$T0" "$SEAHUB_LINES" >> ~/seafile-13029.state
dc up -d --no-deps --dry-run seafile seafile-notification          # must list only these two (Recreate)
```

If the dry run lists any other service, or pulls anything other than the two pins, stop. That means the
checkout has drifted from main.

```bash
# PRELUDE first
dc up -d --no-deps seafile                                          # 502 from here until healthy
s=; for i in $(seq 1 60); do                                        # bounded: 5 min
  s=$(docker inspect seafile --format '{{.State.Health.Status}}')
  [ "$s" = healthy ] && { echo "OK seafile healthy after $((i*5))s"; break; }; sleep 5
done
[ "$s" = healthy ] || echo "!! seafile not healthy after 5 min (last: $s): docker inspect -f '{{json .State.Health}}' seafile | jq; then Rollback"
docker exec seafile cat /shared/seafile/seafile-data/current_version          # 13.0.29
docker logs --since "$T0" seafile 2>&1 | grep -iE 'upgrade|traceback|error' | tail -10   # minor-upgrade only, no Traceback
# the static `upstream seafile` holds the old container IP until nginx reloads
dc exec nginx nginx -t && dc exec nginx nginx -s reload
dc up -d --no-deps seafile-notification
r=; for i in $(seq 1 24); do                                        # bounded: 2 min
  r=$(curl -s -m 5 https://files.markcheli.com/notification/ping)
  echo "$r" | grep -q pong && { echo "OK notification up after $((i*5))s"; break; }; sleep 5
done
echo "$r" | grep -q pong || echo "!! notification ping failing after 2 min (last: $r): docker logs seafile-notification; then Rollback"
```

## 4. Checks (gate)

```bash
# PRELUDE first
# 4a. Edge paths (all non-interactive)
curl -s -m 10 -o /dev/null -w 'web %{http_code}\n' https://files.markcheli.com/accounts/login/   # web 200
curl -s -m 10 -w ' %{http_code}\n' https://files.markcheli.com/api2/ping/                        # "pong" 200
curl -s -m 10 https://files.markcheli.com/api2/server-info/ | grep -o '"version": "[^"]*"'      # "version": "13.0.29"
curl -s -m 10 -w ' %{http_code}\n' https://files.markcheli.com/seafhttp/protocol-version        # {"version": 2} 200
curl -s -m 10 -w ' %{http_code}\n' https://files.markcheli.com/notification/ping                 # {"ret": "pong"} 200
# 4b. notification-server websocket handshake through Cloudflare + edge. -m 5 bounds it: curl then
#     exits 28 on the open socket, which is expected. Only the first line matters.
curl -s --http1.1 -i -m 5 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' https://files.markcheli.com/notification | head -1   # HTTP/1.1 101 Switching Protocols
docker inspect seafile --format '{{.State.Health.Status}}'                                      # healthy
docker logs --since "$T0" seafile-notification 2>&1 | grep -iE 'error|fatal|fail' | tail -5      # nothing
# 4c. Did anything touch the DB? (expected: no)
q "$SCHEMA_SQL" | diff - "$BK/schema.txt" && echo "OK schema unchanged" || echo "!! SCHEMA CHANGED: a migration ran; a rollback must include 6b"
q "$MIGR_SQL" | diff - "$BK/migrations.txt" && echo "OK no new Django migrations" || echo "!! NEW MIGRATIONS: a rollback must include 6b"
q "$COUNT_SQL" | diff - "$BK/baseline.txt" && echo "OK counts match" || echo "!! counts differ: fine only if someone created a library meanwhile"
# 4d. Logs clean: seahub lines written since step 3, plus the other server logs
docker exec seafile sh -c "tail -n +$((SEAHUB_LINES+1)) /shared/seafile/logs/seahub.log" | grep -iE 'error|traceback|critical' | tail -10   # nothing
docker exec seafile sh -c 'grep -hiE "error|traceback|critical" /shared/seafile/logs/seafile.log /shared/seafile/logs/fileserver.log /shared/seafile/logs/seafevents.log 2>/dev/null' | tail -10   # nothing new (look at timestamps)
docker logs --since "$T0" nginx 2>&1 | grep files.markcheli.com | grep -E '" 5[0-9]{2} ' | tail -5   # only during the restart minute
```

**Gate:** web 200, ping `"pong"` 200, server-info 13.0.29, seafhttp 200, notification pong 200, WebSocket `101`,
`healthy`, `OK schema unchanged`, `OK no new Django migrations`, and no new seahub `ERROR`/`Traceback`. If anything
fails and the fix isn't obvious, go to [Rollback](#6-rollback).

**Optional (Mark, afterwards, not a gate): authenticated library list.** The password is read without echoing:

```bash
read -rp 'Seafile admin email: ' U; read -rsp 'Seafile password: ' PW; echo
TOKEN=$(curl -s -m 10 -d "username=$U" --data-urlencode "password=$PW" https://files.markcheli.com/api2/auth-token/ | jq -r .token); unset PW
curl -s -m 10 -H "Authorization: Token $TOKEN" https://files.markcheli.com/api2/repos/ | jq -r '.[].name'   # the 3 libraries
unset TOKEN
```

Then resume the desktop client. Edit a file in the web UI, and the client should pick it up within seconds
(that's the notification server; without it, the client polls every 30 s).

## 5. Watch for 10 minutes

```bash
# PRELUDE first
for i in $(seq 1 10); do
  printf '%s seafile=%s/%s notif=%s/%s ping=%s npong=%s\n' "$(date +%T)" \
    "$(docker inspect seafile --format '{{.State.Health.Status}}')" "$(docker inspect seafile --format '{{.RestartCount}}')" \
    "$(docker inspect seafile-notification --format '{{.State.Status}}')" "$(docker inspect seafile-notification --format '{{.RestartCount}}')" \
    "$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://files.markcheli.com/api2/ping/)" \
    "$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://files.markcheli.com/notification/ping)"
  sleep 60
done
docker exec seafile sh -c "tail -n +$((SEAHUB_LINES+1)) /shared/seafile/logs/seahub.log" | grep -ciE 'error|traceback'   # 0
docker logs --since "$T0" seafile-notification 2>&1 | grep -ciE 'error|fatal'                                         # 0
```

If every line shows `healthy/0 running/0 200 200`, it's done.

**Afterwards:**
- Dependency-Track: the nightly `scripts/sbom-scan.sh` (03:30) uploads the new BOMs. To see the clears now, run
  `scripts/sbom-scan.sh --only seafile` and then `--only seafile-notification`. Expect about −17 C / −98 H on `seafile`
  and −5 H on `seafile-notification`. The round-5 distro mark on `seafile` perl CVE-2026-4176 is tied to the old
  component version, so check that it carried over and mark it again if not.
- Seahub's static assets are content-hashed, so a Cloudflare purge isn't required. If the web UI looks stale, run
  `source venv/bin/activate && python scripts/cloudflare_cache_purge.py`.
- After a week: `docker rmi seafileltd/seafile-mc:13.0.28-rollback seafileltd/notification-server:13.0.21-rollback`,
  `rm ~/seafile-13029.state`. Keep `$BK` until the nightly backups have rotated (7 days).

---

## 6. Rollback

**Guard first.** This block destroys nothing, but it must print `GUARDS_OK` before you run the next one.

```bash
# PRELUDE first
rb=1
[ -n "$BK" ] && [ -n "$OLD_SF_ID" ] && [ -n "$OLD_NS_ID" ] || { echo "!! state not loaded: check ~/seafile-13029.state"; rb=0; }
# the tags must exist AND be the real old images (a mis-tag would "roll back" to 13.0.29)
[ "$(docker image inspect seafileltd/seafile-mc:13.0.28-rollback --format '{{.Id}}' 2>/dev/null)" = sha256:d3b8f07584d05a6cc1443bb86b48f916b452bbd49b0d6fea9f127fcf354bb490 ] || \
  { echo "!! seafile-mc:13.0.28-rollback missing or wrong: docker pull seafileltd/seafile-mc:13.0.28@sha256:b0c90832126bf432db908449f1bb450211e6bbf75a2193bab3399e2a9636eccf and re-tag it"; rb=0; }
[ "$(docker image inspect seafileltd/notification-server:13.0.21-rollback --format '{{.Id}}' 2>/dev/null)" = sha256:d756e205de28bcb032bd06f35dbd38e77955a2f95a429fae579917b50d269713 ] || \
  { echo "!! notification-server:13.0.21-rollback missing or wrong: docker pull seafileltd/notification-server:13.0.21@sha256:1cac4101d0f4527ad08c00b5452ceb05d790db95d6c8ab6bbace82429c1e5217 and re-tag it"; rb=0; }
zcat "$BK/seafile-3db.sql.gz" 2>/dev/null | tail -1 | grep -q 'Dump completed' || { echo "!! no complete dump in $BK"; rb=0; }
[ "$rb" = 1 ] && echo GUARDS_OK
```

**6a. Image rollback** (the usual case). Compose already honours `SEAFILE_IMAGE` / `SEAFILE_NOTIFICATION_IMAGE`.
The rollback file sets them, and the PRELUDE keeps loading it, so later `dc` calls don't bring 13.0.29 back
before main is reverted. **Only shells that ran the PRELUDE see it.** A plain `docker compose up -d`, `make up`
or any other compose call without the PRELUDE would bring 13.0.29 back. Until main is reverted, run every compose
command through the PRELUDE (or `. ~/seafile-13029.rollback` first). On start, 13.0.28 sees the stamp 13.0.29, treats it as a same-major change, and runs
only `minor-upgrade.sh` (symlinks) again, which is harmless.

```bash
# PRELUDE first. Only after GUARDS_OK.
printf 'export SEAFILE_IMAGE=seafileltd/seafile-mc:13.0.28-rollback\nexport SEAFILE_NOTIFICATION_IMAGE=seafileltd/notification-server:13.0.21-rollback\n' > ~/seafile-13029.rollback
. ~/seafile-13029.rollback
dc config seafile seafile-notification | grep 'image: seafileltd'   # both …-rollback
dc up -d --no-deps --dry-run seafile seafile-notification           # only these two
dc up -d --no-deps seafile seafile-notification
s=; for i in $(seq 1 60); do s=$(docker inspect seafile --format '{{.State.Health.Status}}'); [ "$s" = healthy ] && break; sleep 5; done
echo "seafile: $s"                                                   # healthy
docker exec seafile cat /shared/seafile/seafile-data/current_version  # 13.0.28
dc exec nginx nginx -t && dc exec nginx nginx -s reload
# then re-run step 4 (expect server-info 13.0.28)
```

If step 4c printed `!! SCHEMA CHANGED` or `!! NEW MIGRATIONS`, also do **6b**: 13.0.28 code on a 13.0.29 schema is
untested. Otherwise 6a is the whole rollback. Then open a revert PR of this change on main. Once that is
merged and pulled, `rm ~/seafile-13029.rollback`.

**6b. Data restore** (only if a migration ran, or the data is wrong). Database writes made after the step 2 dump
are lost. File blocks uploaded since then stay in storage, unreferenced, until the next GC. Desktop clients that synced
in between may need their library re-synced.

```bash
# PRELUDE first. Only after GUARDS_OK and 6a (seafile-db keeps running throughout).
dc stop -t 60 seafile-notification seafile
for d in ccnet_db seafile_db seahub_db; do q "DROP DATABASE IF EXISTS $d"; done
zcat "$BK/seafile-3db.sql.gz" | docker exec -i seafile-db sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'
q "$SCHEMA_SQL" | diff - "$BK/schema.txt" && echo "OK schema restored" || echo "!! schema differs from the step 2 baseline"
q "$MIGR_SQL" | diff - "$BK/migrations.txt" && echo "OK migrations restored" || echo "!! migrations differ from the step 2 baseline"
q "$COUNT_SQL" | diff - "$BK/baseline.txt" && echo "OK counts restored" || echo "!! counts differ from the step 2 baseline"
dc up -d --no-deps seafile seafile-notification                     # still the -rollback images (PRELUDE loaded the file)
s=; for i in $(seq 1 60); do s=$(docker inspect seafile --format '{{.State.Health.Status}}'); [ "$s" = healthy ] && break; sleep 5; done
echo "seafile: $s"
dc exec nginx nginx -t && dc exec nginx nginx -s reload             # refresh the static upstream IP
# then re-run step 4
```

The grants live in the `mysql` schema, which isn't dropped, so the `seafile` user keeps working. The conf files
aren't touched by a patch upgrade. If they turn out to be wrong, `$BK/seafile-conf.tgz` holds the step 2 copy.

**Rollback timing:** image only, about 3 minutes. With a data restore, about 6 minutes (the dump is about 20 MB).

---

## Downtime

| Phase | Estimate | User-visible |
|---|---|---|
| 1–2: record, pull, dump, NAS copy | 5 min | no |
| 3: recreate seafile → healthy, nginx reload | 2–3 min | **502 on files.markcheli.com** |
| 3: recreate seafile-notification | < 30 s | desktop clients fall back to polling |
| 4–5: checks + 10-minute watch | 15 min | no |
| **Total** | **about 2–3 min of downtime** (book 30 min; add 5 min if you roll back) | |

## References

- CE changelog: https://plus.seafile.com/wiki/publish/seafile-wiki/5L80/
- Security fixes: https://plus.seafile.com/wiki/publish/seafile-wiki/O50D/
- Docker upgrade guide: https://manual.seafile.com/13.0/upgrade/upgrade_docker/
- Image upgrade logic: https://github.com/haiwen/seafile-docker/blob/master/scripts/scripts_13.0/upgrade.py
- Previous runbooks: `docs/seafile-upgrade-2026-11.md` (11.0 → 13.0.28), `docs/seafile-db-mariadb-10.11.19.md`
- Dependency-Track: `docs/dependency-track.md`; triage round 5 (2026-11-05)
