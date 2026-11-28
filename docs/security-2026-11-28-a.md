# Security sweep 2026-11-28, PR A: stateless image bumps (runbook)

**Scope:** edge `nginx` (rebuild on `nginx:1.30.8-alpine`), `homelab-mcp` (rebuild on a
digest-pinned `python:3.13.18-slim`), `openclaw` (2026.10.9 → 2026.10.34, standalone compose) and
`obsidian-sync-notes` / `obsidian-sync-raw` (rebuild on `node:22.23.5-alpine3.24`).
**Order:** run this before PR B (`docs/security-2026-11-28-b.md`) and PR C.
**Backups:** none of these services keeps data in its image. The one exception is `openclaw`: its boot
runs `openclaw doctor`, which can rewrite `./openclaw-home`, so step 3 tars that directory first.
**Downtime:** a few seconds per service. For nginx this means every site. Avoid 02:00 ET, when the nightly backup runs.

Pins checked against the registries on 2026-11-28:

| Image | Pin (index) | linux/amd64 manifest |
|---|---|---|
| `nginx:1.30.8-alpine` | `sha256:8eb04fe3…c0d3` | `sha256:0616b208…b1c5` |
| `python:3.13.18-slim` | `sha256:168d3a5d…82a7` | `sha256:e123d49d…168d` |
| `node:22.23.5-alpine3.24` | `sha256:1314fb30…481a` | `sha256:12f54caf…062c` |
| `ghcr.io/openclaw/openclaw` 2026.10.34 | `sha256:62174326…8ecc` | `sha256:9bbe6d4e…b996` |

Healthcheck tools: nginx's `curl` comes from the base image (its last layer is `apk add curl ca-certificates`).
openclaw 2026.10.34 installs `curl` in its own apt layer, after the base's purge, so the compose healthcheck keeps working.
homelab-mcp checks itself with python.

## Conventions

- Run on 83rr-poweredge as `mcheli` in **bash** (`bash` first: the login shell is zsh, which does not
  word-split `$VARS`, and its `cat` is aliased to `cat -n`). Run the PRELUDE at the top of every block.
  State lives in `$S`, so any block can be resumed from a fresh shell.
- Lines starting `!!` mean stop. Every wait is bounded.
- Each service step starts with a compose `--dry-run` block on its own. If it says it would **create a
  volume**, stop and don't run the next block: the project or volume name has drifted, and the real run
  would start the service on empty data.

```bash
# PRELUDE (bash)
cd ~/83rr-poweredge
BK=/data/backups/2026-11-28; NAS=/mnt/nas/83rr-backup/pre-upgrade-2026-11-28; S=$BK/state-a.env
mkdir -p "$BK"; [ -f "$S" ] && . "$S"
dc() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }       # never the override file
oc() { docker compose -f infrastructure/openclaw/docker-compose.yml "$@"; }
ai() { docker compose -f infrastructure/ai-context/docker-compose.yml --profile obsidian "$@"; }
# dryrun <compose fn> <svc...>: prints the plan; non-zero (and !!) if it would create a volume
dryrun() { local out; out=$("$1" --dry-run up -d --no-deps "${@:2}" 2>&1); printf '%s\n' "$out"
  if printf '%s\n' "$out" | grep -qiE 'volume.*creat'; then echo "!! STOP: the dry run would create a volume"; return 1; fi
  printf '%s\n' "$out" | grep -qiE 'network.*creat' && echo "!! the dry run would create a network: check the project name before going on"
  echo "OK dry run: no new volume"; }
# keep_old <container> <rollback tag>: tags the running image once, records it in $S, never overwrites
keep_old() { local v id; v=OLD_$(printf %s "$1" | tr 'a-z-' 'A-Z_')
  if grep -q "^$v=" "$S" 2>/dev/null; then echo "OK $v already recorded, not overwritten"
  else id=$(docker inspect -f '{{.Image}}' "$1") || { echo "!! $1 is not running: stop"; return 1; }
       docker tag "$id" "$2" && echo "$v=$id" >> "$S"; fi
  . "$S"; [ "$(docker image inspect -f '{{.Id}}' "$2" 2>/dev/null)" = "${!v}" ] && echo "OK rollback tag $2 = ${!v}" || echo "!! rollback tag $2 missing or wrong"; }
# wait_healthy <container> <seconds>
wait_healthy() { local s i; for i in $(seq 1 $(( $2 / 5 ))); do
    s=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null)
    case $s in healthy) echo "OK $1 healthy after $((i*5))s"; return 0;; esac; sleep 5; done
  echo "!! $1 not healthy after $2 s (last: $s): see Rollback"; return 1; }
# nas_copy <file>: copies to $NAS and compares checksums
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
grep -q 'nginx:1.30.8-alpine@sha256:8eb04fe3' infrastructure/nginx/Dockerfile && echo "OK PR A is pulled" || echo "!! PR A not in the checkout"
command cat "$S"
```

## 1. Edge nginx

```bash
# PRELUDE first
dryrun dc nginx               # expect: Container nginx Running/Recreate, no volume
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old nginx ghcr.io/mcheli/nginx:rollback-2026-11-28
dc build nginx
dc up -d --no-deps nginx
wait_healthy nginx 120
dc exec nginx nginx -v 2>&1                                                     # nginx/1.30.8
dc exec nginx nginx -t
for u in https://www.markcheli.com https://files.markcheli.com/api2/ping/ https://tasks.markcheli.com; do
  printf '%s %s\n' "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$u")" "$u"; done   # 200 (or 30x)
dc logs --since 5m nginx 2>&1 | grep -iE 'emerg|crit|\[error\]' | tail -5        # nothing new
```

## 2. homelab-mcp (profile `mcp`)

```bash
# PRELUDE first
dryrun dc homelab-mcp
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old homelab-mcp homelab-mcp:rollback-2026-11-28
dc build homelab-mcp
dc up -d --no-deps homelab-mcp
wait_healthy homelab-mcp 120                                                     # the image's own /health check
dc logs --since 5m homelab-mcp 2>&1 | grep -iE 'traceback|error' | tail -5        # nothing
```

## 3. openclaw (standalone compose)

Back up its state first, with the container stopped so the files are consistent. The tarball holds
credentials: it is written mode 600, and the NAS copy sits next to the nightly copy of the same directory.

```bash
# PRELUDE first
dryrun oc openclaw            # project "openclaw", networks already exist
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old openclaw ghcr.io/openclaw/openclaw:rollback-2026.10.9
oc pull openclaw
if [ ! -f "$BK/openclaw-home.tgz" ]; then
  oc stop openclaw
  (umask 077; tar -C infrastructure/openclaw -czf "$BK/openclaw-home.tgz" openclaw-home gogcli) \
    && gzip -t "$BK/openclaw-home.tgz" && tar -tzf "$BK/openclaw-home.tgz" | grep -q '^openclaw-home/' \
    && echo "OK openclaw-home.tgz $(du -h "$BK/openclaw-home.tgz" | cut -f1)" || echo "!! BAD openclaw backup: stop (oc start openclaw to resume)"
else echo "OK openclaw-home.tgz exists from an earlier run, not overwritten"; fi
nas_copy "$BK/openclaw-home.tgz"
```
Only continue if both lines say `OK`.

```bash
# PRELUDE first
oc up -d openclaw
wait_healthy openclaw 360        # boot runs `openclaw doctor` (~100 s) before the gateway binds; start_period 180 s
docker exec openclaw sh -c 'command -v curl' || echo "!! curl missing in the image: the healthcheck can't pass"
oc logs --since 10m openclaw 2>&1 | grep -iE 'error|fatal|migrat|doctor' | tail -15
```
Then check that the Discord bot answers a message. 2026.10.34 drops the retired MiniMax M2 models. If the
logs complain about a configured model, switch it to a supported one (it's config, not a rollback reason).

## 4. obsidian-sync (profile `obsidian`)

```bash
# PRELUDE first
dryrun ai obsidian-sync-notes obsidian-sync-raw
```

```bash
# PRELUDE first. Only after "OK dry run".
keep_old obsidian-sync-notes obsidian-headless:rollback-2026-11-28    # both containers run the same image
ai build obsidian-sync-notes
ai up -d --no-deps obsidian-sync-notes obsidian-sync-raw
sleep 60; docker ps --filter name=obsidian-sync --format '{{.Names}} {{.Status}}'   # both Up, not Restarting
docker exec obsidian-sync-notes node -v                                             # v22.23.5
ai logs --since 5m obsidian-sync-notes obsidian-sync-raw 2>&1 | grep -iE 'error|auth|login' | tail -10   # no login prompts
```

## 5. Finish

`make health`. Then, after a week, `docker rmi` the four `rollback` tags. Keep `$BK` until the nightly backups have rotated (7 days).

## Rollback (per service; nothing here deletes data)

```bash
# PRELUDE first. Built images: point the compose tag back at the old image and recreate.
docker tag ghcr.io/mcheli/nginx:rollback-2026-11-28 ghcr.io/mcheli/nginx:latest && dc up -d --no-deps --force-recreate nginx && wait_healthy nginx 120
docker tag homelab-mcp:rollback-2026-11-28 homelab-mcp:local && dc up -d --no-deps --force-recreate homelab-mcp && wait_healthy homelab-mcp 120
docker tag obsidian-headless:rollback-2026-11-28 obsidian-headless:local && ai up -d --no-deps --force-recreate obsidian-sync-notes obsidian-sync-raw
```
A later `build` brings the new base back, so open a revert PR before anyone rebuilds.

openclaw: the old image may not read state that the new `doctor` rewrote, so restore the tarball as well:
```bash
# PRELUDE first
[ "$(docker image inspect -f '{{.Id}}' ghcr.io/openclaw/openclaw:rollback-2026.10.9)" = "$OLD_OPENCLAW" ] && gzip -t "$BK/openclaw-home.tgz" && echo GUARDS_OK
# only after GUARDS_OK:
oc stop openclaw
command mv infrastructure/openclaw/openclaw-home infrastructure/openclaw/openclaw-home.failed-2026-11-28
command mv infrastructure/openclaw/gogcli infrastructure/openclaw/gogcli.failed-2026-11-28
tar -C infrastructure/openclaw -xzf "$BK/openclaw-home.tgz"
printf 'services:\n  openclaw:\n    image: ghcr.io/openclaw/openclaw:rollback-2026.10.9\n' > ~/openclaw-rollback.override.yml
docker compose -f infrastructure/openclaw/docker-compose.yml -f ~/openclaw-rollback.override.yml up -d openclaw
wait_healthy openclaw 360
```
Keep passing `~/openclaw-rollback.override.yml` until the revert PR is merged and pulled. Delete the
`*.failed-2026-11-28` directories once 2026.10.9 is confirmed working.
