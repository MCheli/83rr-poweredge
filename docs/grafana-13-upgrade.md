# Grafana 12.4.14 → 13.3.0 upgrade (November 2026)

**Target:** `grafana/grafana:13.3.0@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205`. This is the multi-arch index digest; the amd64 manifest is `sha256:6e5d3063…ce63d`. The image config is the same as 12.x: entrypoint `/run.sh`, user 472.
**Fallback (13.0.x line):** `grafana/grafana:13.0.12@sha256:28476aa8096cd8d0f658a05a443b605fffb450e57f444335216175d604cfd23d` (amd64 `sha256:5e3f5270…9e2ab`, same image config). If Mark picks 13.0.x at approval, it takes a one-line follow-up PR to swap the compose pin before deploy. Then read `13.0.12` wherever this runbook expects `13.3.0`.
**Rollback image:** `grafana/grafana:12.4.14@sha256:ae509d9ae8c1021ca32ec370a9ca975d40165eda9fccd1e1102d317ff8787cd7`

## Why 13.3.0
- Mark asked for the latest stable, non-beta release. 13.3.0 is the "Latest" GA release on the upstream releases page (2026-10-27). The briefs' "13.0.x" was a mistake by the spawning session.
- **CVE-2026-14199** (Auth Proxy cache-key session takeover) was fixed upstream in v13.0.8, so 13.3.0 and the 13.0.12 fallback both cover it. It isn't exploitable here anyway: only the built-in admin login is used, not Auth Proxy.
- Both lines carry the later security fixes:
  - CVE-2026-13719, -13720 and -81841
  - CVE-2026-15577, -33374, -93294 and -95502
  - CVE-2026-100105, -88858 and -88967
- Trade-off: 13.3.0 is a fresh `.0` minor. The 13.0.0 migration bug only affected Git Sync setups, which this isn't, and it was fixed in 13.0.1.

## Breaking changes vs this setup
Inventory was taken read-only on 2026-11-03.

| 13.0 change | Applies here? |
|---|---|
| Unified storage: a **one-way** migration of dashboards and folders inside grafana.db, run once at startup and tracked in `unifiedstorage_migration_log` | **Yes.** SQLite grafana.db is 1.9 MB with 6 file-provisioned dashboards, no library panels, only the General folder and 1 user. The backup is the only rollback. If startup logs show `database is locked`, set `GF_UNIFIED_STORAGE_MIGRATION_PARQUET_BUFFER=true` |
| Image Renderer plugin removed; renderer auth now uses JWT | No. No renderer, no `[rendering]` server_url, no reports |
| `grafana-cli` / `grafana-server` removed | No. Compose has no command or entrypoint override |
| RBAC tightening for custom or provisioned roles | No. No custom roles or service accounts |
| `/api` deprecated (still served); numeric-id datasource APIs disabled | No. Only `/api/health` is called (healthcheck, Makefile, Uptime Kuma, `test_infrastructure.py`) |
| Legacy Alertmanager endpoints removed or restricted | No. 0 alert rules, no templates or mute timings. The only contact point is the default `email receiver` placeholder. ntfy alerting goes through OpenSearch and Uptime Kuma, not Grafana |
| `grafana_caching_*` metrics removed | No. Prometheus doesn't scrape Grafana |
| 13.1–13.3 breaking changes: Prometheus azure/sigv4 auth and Zipkin removed from core, `[marketplace]` renamed to `[plugins_marketplace]`, `alertingSaveStateCompressed` flag removed | No. The Prometheus datasource uses no auth, there's no Zipkin and no custom ini |
| React 19 / removed `@grafana/ui` Graph components | No for dashboards (timeseries/stat/gauge/bargauge/table only). The volume holds stale drilldown app copies (lokiexplore 1.0.10, metricsdrilldown 1.0.26, exploretraces 1.2.2, pyroscope 1.17.0); see the optional follow-up below |

Other notes:
- Stray UI-created datasource `Prometheus-1` (→ `https://prometheus.ops.markcheli.com`): harmless, left alone.
- `grafana-piechart-panel`: an Angular plugin left over from the Traefik era. It isn't loaded on 12.x and no dashboard uses it.

## Runbook
Run this on 83rr-poweredge as `mcheli`. The login shell there is **zsh**, so compose flags are written out on every call rather than kept in a variable: zsh doesn't word-split unquoted variables. The NAS is writable as `mcheli` (checked 2026-11-03). Step 4's `--dry-run` only works after the `pull`, because it needs the image locally. **No sudo is needed.** The volume is read and written through a throwaway container.

Every block starts by sourcing `$D/state.env`, so any step can be resumed from a new shell.

### 0. Prepare (before `git pull`)
```bash
cd ~/83rr-poweredge
D=/data/backups/upgrade-20261103; mkdir -p $D/before
cat > $D/state.env <<EOF
D=$D
OLD_REV=$(git rev-parse HEAD)
OLD_IMAGE_ID=$(docker inspect grafana --format '{{.Image}}')
OLD_DIGEST=grafana/grafana@sha256:ae509d9ae8c1021ca32ec370a9ca975d40165eda9fccd1e1102d317ff8787cd7
VOL=83rr-poweredge_grafana_data
EOF
git pull --ff-only
```

### 1. Before-state (Grafana still running on 12.4.14)
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
docker image inspect grafana/grafana:12.4.14 --format '{{.Id}} {{json .RepoDigests}}' > $D/before/image.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g "search?type=dash-db" | grep -o "\"uid\":\"[^\"]*\"" | sort
' > $D/before/dashboards.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g datasources | grep -o "\"uid\":\"[^\"]*\",\"orgId\":[0-9]*,\"name\":\"[^\"]*\"" | sort
' > $D/before/datasources.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g v1/provisioning/alert-rules | grep -o "\"uid\":\"[^\"]*\"" | sort
' > $D/before/alert-rules.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g v1/provisioning/contact-points | grep -o "\"name\":\"[^\"]*\",\"type\":\"[^\"]*\"" | sort
' > $D/before/contact-points.txt
docker exec grafana grafana cli plugins ls > $D/before/plugins.txt 2>&1
wc -l $D/before/*.txt     # expect 6 dashboards, 2 datasources, 0 alert rules, 1 contact point
```

### 2. Back up the volume (stopped, so SQLite is consistent) and verify
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop grafana
docker run --rm -u 0 --entrypoint sh -v $VOL:/src:ro -v $D:/dst $OLD_DIGEST \
  -c "tar -C /src -czf /dst/grafana_data.tgz . && chown $(id -u):$(id -g) /dst/grafana_data.tgz"
tar -tzf $D/grafana_data.tgz | grep -qx './grafana.db' && echo "db present"
echo "BACKUP_SHA=$(sha256sum $D/grafana_data.tgz | cut -d' ' -f1)" >> $D/state.env
N=/mnt/nas/83rr-backup/upgrade-20261103
mountpoint -q /mnt/nas && mkdir -p $N && cp $D/grafana_data.tgz $D/state.env $N/ \
  && [ "$(sha256sum $N/grafana_data.tgz | cut -d' ' -f1)" = "$(sha256sum $D/grafana_data.tgz | cut -d' ' -f1)" ] && echo "NAS copy verified"
```
If the NAS isn't writable as `mcheli`, stop and copy it by another route. Don't use sudo. Don't continue without an off-box copy.

### 3. Tag the old image
```bash
. /data/backups/upgrade-20261103/state.env
docker tag $OLD_DIGEST grafana/grafana:rollback-12.4.14
```

### 4. Dry run, then upgrade
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q && docker compose -f docker-compose.yml -f docker-compose.prod.yml config --images | grep grafana   # expect 13.3.0@sha256:488984b7…
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull grafana
docker compose -f docker-compose.yml -f docker-compose.prod.yml --dry-run up -d --no-deps grafana
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps grafana
```

### 5. Bounded health wait (at most 5 minutes)
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
for i in $(seq 1 30); do s=$(docker inspect -f '{{.State.Health.Status}}' grafana); echo "$i $s"; [ "$s" = healthy ] && break; sleep 10; done
[ "$s" = healthy ] || { docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 200 grafana; echo "NOT HEALTHY: go to Rollback"; }
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs grafana | grep -iE 'level=error|migration.*(fail|error)' | tail -20   # expect nothing
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs grafana | grep -i 'unifiedstorage\|migration' | tail -5
echo "RESTARTS0=$(docker inspect -f '{{.RestartCount}}' grafana)" >> $D/state.env
```

### 6. Health check (diff against the before-state)
```bash
. /data/backups/upgrade-20261103/state.env; mkdir -p $D/after
docker exec grafana wget -qO- http://localhost:3000/api/health      # "version": "13.3.0", "database": "ok"
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g "search?type=dash-db" | grep -o "\"uid\":\"[^\"]*\"" | sort' > $D/after/dashboards.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g datasources | grep -o "\"uid\":\"[^\"]*\",\"orgId\":[0-9]*,\"name\":\"[^\"]*\"" | sort' > $D/after/datasources.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g v1/provisioning/alert-rules | grep -o "\"uid\":\"[^\"]*\"" | sort' > $D/after/alert-rules.txt
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  g v1/provisioning/contact-points | grep -o "\"name\":\"[^\"]*\",\"type\":\"[^\"]*\"" | sort' > $D/after/contact-points.txt
for f in dashboards datasources alert-rules contact-points; do diff -q $D/before/$f.txt $D/after/$f.txt >/dev/null && echo "same $f" || { echo "DIFF $f"; diff $D/before/$f.txt $D/after/$f.txt; }; done
docker exec grafana sh -c 'H="Authorization: Basic $(printf %s "admin:$GF_SECURITY_ADMIN_PASSWORD"|base64)"; g(){ wget -qO- --header="$H" "http://localhost:3000/api/$1"; echo; }
  for u in containers-glance containers-dashboard docker-services infrastructure-overview nginx-dashboard system-dashboard; do g "dashboards/uid/$u" | grep -q "\"uid\":\"$u\"" && echo "ok $u" || echo "FAIL $u"; done
  g datasources/uid/prometheus/health'                                 # "status":"OK"
```
Then load each dashboard at https://dashboard.ops.markcheli.com and check the panels render with data. Finish with `make health`.

### 7. 10-minute watch
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in $(seq 1 10); do
  sleep 60
  h=$(docker inspect -f '{{.State.Health.Status}}' grafana); r=$(docker inspect -f '{{.RestartCount}}' grafana)
  db=$(docker exec grafana wget -qO- http://localhost:3000/api/health | grep -o '"database": *"[a-z]*"')
  e=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --since "$T0" grafana | grep -c 'level=error')
  echo "$i health=$h restarts=$r ($RESTARTS0) $db errors=$e"
done
```
Pass condition: `healthy` every minute, the restart count unchanged, `database ok`, and errors at 0. Look into any error before calling it done.

### Rollback
The migration is one-way, and 12.4 would read the stale legacy tables. Always restore the tarball; never just swap the image.
```bash
. /data/backups/upgrade-20261103/state.env; cd ~/83rr-poweredge
if [ "$(sha256sum $D/grafana_data.tgz | cut -d' ' -f1)" = "$BACKUP_SHA" ]; then
  docker compose -f docker-compose.yml -f docker-compose.prod.yml stop grafana
  docker run --rm -u 0 --entrypoint sh -v $VOL:/dst -v $D:/src:ro $OLD_DIGEST \
    -c 'find /dst -mindepth 1 -delete && tar -C /dst -xzf /src/grafana_data.tgz'
  git checkout $OLD_REV -- docker-compose.yml      # back to the 12.4.14 pin; no commit on the server
  docker compose -f docker-compose.yml -f docker-compose.prod.yml config --images | grep grafana  # expect grafana/grafana:12.4.14
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps grafana
else
  echo "BACKUP SHA MISMATCH: STOP. Nothing changed. Verify the NAS copy (/mnt/nas/83rr-backup/upgrade-20261103/) and restore from it instead"
fi
```
Then run steps 5 and 6 again, expecting version 12.4.14, and open a revert PR on GitHub. Once that PR is merged, `git checkout -- docker-compose.yml && git pull --ff-only` returns the server to a clean tree. Anything changed in the UI while 13.x was running is lost, but in practice that's nothing, because the dashboards are file-provisioned.

## Optional follow-up (only after the 10-minute watch passes)
These change state after the backup. Do them separately, if at all.
- Update the stale bundled app plugins: `docker exec grafana grafana cli plugins update-all && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart grafana`
- Remove the dead Angular plugin: `docker exec grafana rm -rf /var/lib/grafana/plugins/grafana-piechart-panel`
- Delete the stale Traefik-era `infrastructure/monitoring/docker-compose.yml` (Grafana 10.2.0, unused). This needs a PR.

## Worth using now
- **Recently deleted → restore:** dashboards deleted in the UI can be restored without a DB restore. Useful because `allowUiUpdates: true` lets UI edits drift from the repo JSON.
- **Grafana Advisor:** weekly checks for failing datasources and outdated plugins. It would flag the stale drilldown apps and the orphan `Prometheus-1` datasource.
- **Dynamic dashboards** (on by default): tabs, conditional rows and section-level variables. Use them to merge the overlapping Docker Containers / Docker Services / Containers — Glance boards into one tabbed board.
- **Legend series limits:** keeps the per-container timeseries panels (30+ containers) readable.
- **Revamped gauge** and visualization suggestions, for the stat/gauge-heavy System and Infrastructure boards.
