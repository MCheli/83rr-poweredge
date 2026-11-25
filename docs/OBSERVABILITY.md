# Observability: logs, metrics, dashboards, alerting

How the homelab watches itself: where logs and metrics come from, where they are
stored, which dashboards exist, and how alerts reach a phone. Config lives in the
repo; this page is the map.

| Piece | What it does | Config | UI |
|---|---|---|---|
| **Fluent Bit** | ships container logs, Docker events and a few host log files to OpenSearch | `infrastructure/fluent-bit/` | none |
| **OpenSearch** | log store (daily indices `logs-homelab-YYYY.MM.DD`), log-based alert monitors | `infrastructure/opensearch/config/` | <https://opensearch.ops.markcheli.com> (API) |
| **OpenSearch Dashboards** | Discover, saved searches, 4 log dashboards | `infrastructure/opensearch/config/saved_objects/` | <https://logs.ops.markcheli.com> |
| **Prometheus** | metrics, 15 s scrapes, 30-day retention | `infrastructure/monitoring/prometheus.yml` | <https://prometheus.ops.markcheli.com> |
| **node-exporter / cAdvisor / nginx-exporter** | host, container and nginx metrics; node-exporter also reads textfile metrics written by cron scripts | `docker-compose.yml` | <https://cadvisor.ops.markcheli.com> |
| **Grafana** | 7 provisioned dashboards, Prometheus alert rules | `infrastructure/monitoring/grafana/provisioning/` | <https://dashboard.ops.markcheli.com> |
| **Uptime Kuma** | external up/down probes and the public status page | `scripts/setup_uptime_kuma.py` | <https://status.markcheli.com> |
| **Dependency-Track** | CVEs in every running container's SBOM | `docs/dependency-track.md` | <https://deptrack.ops.markcheli.com> |
| **ntfy** | where every alert ends up (topic `homelab`) | `infrastructure/ntfy/server.yml` | <https://ntfy.markcheli.com> |

The `*.ops` hostnames are LAN-only (nginx allowlist, see `CLAUDE.md`).

---

## Logs

### Pipeline

```
docker logs ─┐
docker events ┤                                    ingest pipeline
plex, seafile ├─▶ Fluent Bit ──(filters)──▶ OpenSearch ──(homelab-logs)──▶ logs-homelab-YYYY.MM.DD
fail2ban.log ─┘        │                                                    (ISM: 7 d hot, delete at 90 d)
                       └─▶ /var/log/pg-auth/ (tallied-db auth lines, for fail2ban)
```

**Inputs** (`infrastructure/fluent-bit/fluent-bit.conf`):
- every container's JSON log under `/var/lib/docker/containers/`, with the
  container name added by `extract_container.lua`;
- the Docker event stream (`docker_events`), normalised by `docker_metadata.lua`:
  `die`/`kill`/`oom` become `level: ERROR`, and the record gets `event_type`,
  `compose_project`, `compose_oneoff`, `exit_code` and `image`, so restarts, OOMs and
  Watchtower updates are queryable without grepping log text;
- Plex's and Seafile's own log files, and the host's `/var/log/fail2ban.log`
  (tagged `container_name: plex`, `seafile`, `fail2ban`, `source: file`).

**Dropped before indexing** (noise with no signal): successful healthchecks (`GET
/health`, `/api/health`, `/api/v1/health` answered 200), Plex `DEBUG`/`VERBOSE`
lines, and tallied-db's routine connection lines (local-socket connections and the
"received"/"authenticated" lines; remote "connection authorized" lines are kept for
the `pg-tld-login` monitor). Background: `docs/log-noise-2026-11.md`.

**Parsing** happens in the OpenSearch ingest pipeline `homelab-logs`
(`ingest_pipeline_homelab_logs.json`, the index template's default pipeline), one
grok branch per log format: nginx (combined + XFF + host/upstream/timing),
uvicorn/asgi apps, gunicorn, Watchtower, OpenSearch and Dashboards, Seafile, Fluent
Bit, fail2ban, and Postgres (`*-db`). Levels are normalised to upper case (`WARN` →
`WARNING`); lines no branch matches get a level from a fallback regex.

**Retention**: ISM policy `ism_policy_homelab_logs.json`, hot for 7 days, then
read-only, deleted at 90 days (about 90 daily indices at any time).

**Other writers**: a few cron scripts post documents straight into the same indices,
so they can be alerted on like logs: `backup.sh` (`event_type: backup_completed`),
`renew-letsencrypt-certs.sh` (`renew_completed` / `renew_failed`),
`emit_host_metrics.sh` (`metric`: disk, memory, CPU, load every 5 min) and
`emit_security_telemetry.sh` (`security_unexpected_port`,
`security_external_db_conn`).

Applying template, pipeline and Fluent Bit changes in the right order:
`infrastructure/opensearch/config/alerting/README.md`, "Rollout order".

### Index pattern and fields

Index pattern `logs-homelab-*` (saved object id `logs-homelab`), time field
`@timestamp`. Mappings: `index_template_logs_homelab.json`; after a mapping change,
refresh the field list in *Dashboards Management → Index patterns*.

| Field | Type | Set by | Notes |
|---|---|---|---|
| `@timestamp` | date | Fluent Bit | The time field to use everywhere. |
| `time` | date | Docker JSON | Original write time; within a millisecond of `@timestamp`. |
| `app_time` | keyword | grok | The app's own timestamp (formats vary, so kept as text). |
| `container_name`, `container_id` | keyword | Lua filters | Name as in `docker ps`; first 12 chars of the id. |
| `stream` | keyword | Docker | `stdout` / `stderr`. |
| `log` | text | Fluent Bit | The raw line; always present. |
| `msg` | text | grok | Message body without level/timestamp. |
| `level` | keyword | grok / fallback | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`. |
| `logger`, `scope`, `subscope`, `thread_id`, `pid` | keyword | grok | Logger/module and process details where the format has them. |
| `method`, `path`, `status`, `bytes`, `http_version` | keyword / integer / long | nginx and app access logs | `path` has no query string. |
| `client_ip` | ip | access logs, Postgres, fail2ban | A real `ip` type: CIDR queries work. |
| `client_port`, `remote_user`, `referrer`, `user_agent`, `x_forwarded_for` | various | access logs | |
| `host`, `upstream_addr`, `upstream_status`, `upstream_response_time`, `request_time` | keyword / float | nginx | Which vhost, which backend, how long. |
| `healthcheck` | boolean | pipeline | `true` only for genuine probes (Kuma, Docker HEALTHCHECK, LAN curl/wget). Successes are dropped at Fluent Bit, so any `healthcheck:true` document is a failure. |
| `event_type`, `event_scope` | keyword | Docker events, pipeline, scripts | e.g. `die`, `start`, `fail2ban_ban`, `pg_auth_failure`, `backup_completed`, `metric`. |
| `compose_project`, `compose_oneoff`, `exit_code`, `image` | keyword / integer | Docker events | `exit_code` 137 = SIGKILL/OOM, 143 = SIGTERM. |
| `wt_failed`, `wt_updated`, `wt_scanned`, `extras` | integer / text | Watchtower | Per update session. |
| `pg_user`, `pg_db` | keyword | Postgres | From the tallied-db log prefix. |
| `metric_name`, `metric_value` | keyword / float | `emit_host_metrics.sh` | |
| `source` | keyword | several | `file` for the Plex/Seafile/fail2ban file inputs. |
| `ingest_error` | text | pipeline `on_failure` | A processor failed: `_exists_:ingest_error` finds broken parses. |

### Log dashboards (OpenSearch Dashboards)

Exported in `infrastructure/opensearch/config/saved_objects/*.ndjson`; a fresh
install imports them with `POST /api/saved_objects/_import` on Dashboards.

| Dashboard | What's on it |
|---|---|
| **Service Health Overview** | log volume and error rate by service, level breakdown, recent errors and warnings |
| **HTTP Edge (nginx)** | status-code distribution, top paths, top client IPs, 5xx / 4xx / 401 events |
| **Operations & Lifecycle** | healthcheck failures, Watchtower update failures, lines the parser couldn't read |
| **Lifecycle History** | backups, image updates and container restarts over time |

### Querying logs

From a terminal, `scripts/logq.sh` runs read-only searches (on the server or from a
machine that can ssh to it): `logq.sh errors 6` (errors in the last 6 h),
`logq.sh errors 1 tasks`, `logq.sh 'container_name:tasks AND log:timeout' 2`. It
prints hits per container and the top messages, and exits 1 when anything matched,
so a deploy check can use it.

Discover queries (Lucene):

| What | Query |
|---|---|
| Errors right now | `level:(ERROR OR CRITICAL OR FATAL)` |
| Server errors at the edge | `container_name:nginx AND status:[500 TO 599]` |
| One vhost | `container_name:nginx AND host:"tasks.markcheli.com"` |
| Failed auth at the edge | `container_name:nginx AND status:401` |
| Healthcheck failures | `healthcheck:true` |
| Containers that died | `event_scope:container AND event_type:die AND NOT exit_code:0` |
| Watchtower failures | `container_name:watchtower AND wt_failed:>0` |
| fail2ban bans | `container_name:fail2ban AND event_type:fail2ban_ban` |
| Lines the parser couldn't read | `_exists_:ingest_error` |
| External (non-LAN) requests | `container_name:nginx AND NOT client_ip:192.168.0.0/16` |

---

## Metrics

**Prometheus** (`infrastructure/monitoring/prometheus.yml`) scrapes four jobs every
15 s: `prometheus`, `cadvisor`, `node-exporter`, `nginx-exporter`; retention is 30
days. Its port isn't published: from the host use `docker exec prometheus wget -qO-
http://localhost:9090/...`, or the LAN UI.

**Textfile metrics**: node-exporter reads `logs/textfile/*.prom`, written by cron
scripts (alert metrics, cron job results, Dependency-Track gauges). The list of
files and metrics is under "Alerting" below.

**Grafana dashboards** (provisioned from
`infrastructure/monitoring/grafana/provisioning/dashboards/`, picked up within 30 s):

| Dashboard | File |
|---|---|
| Infrastructure Overview | `infrastructure-overview.json` |
| System Metrics (node-exporter) | `system.json` |
| Docker Containers | `containers.json` |
| Containers — Glance | `containers-glance.json` |
| Docker Services | `docker-services.json` |
| NGINX | `nginx.json` |
| Dependency-Track trend | `dependency-track.json` |

The JSON files directly under `infrastructure/monitoring/` are older exports and are
not provisioned. More on the exporters and queries: `infrastructure/monitoring/README.md`.

---

## Alerting

Every alert ends up as a push from the self-hosted **ntfy** (`ntfy.markcheli.com`,
topic `homelab`, deny-all auth) to Mark's phone. Publishers use the write-only
`alerts` user's token (`NTFY_PUBLISH_TOKEN` in `.env`, never in the repo); the phone
reads with the read-only `mark` user (1Password Agents / "ntfy phone user"). ntfy setup,
users and token rotation: `infrastructure/opensearch/config/alerting/README.md`.

**Priorities:** 4–5 (high/urgent) buzz the phone; 3 makes a normal sound; 1–2 are
silent and only show in the ntfy app. Only things that need action soon use 4+.

### Routes

| Route | Source of truth | What it sends | Priority |
|---|---|---|---|
| OpenSearch alerting | `infrastructure/opensearch/config/alerting/monitors/*.json` (`apply-monitors.py`) | log-based monitors: error rate, nginx 5xx, auth brute force, healthcheck failures, container died, **backup heartbeat absent 26 h** (`backup-no-heartbeat`), **LE renewal failed**, **watchtower update failed**, root disk pressure, security telemetry, fail2ban, Postgres | per monitor (see that README, "Phone alerts: what each one means") |
| Uptime Kuma | `scripts/setup_uptime_kuma.py` | public endpoint up/down | 4 |
| Grafana unified alerting | `infrastructure/monitoring/grafana/provisioning/alerting/` (`rules.yaml`, `contact-points.yaml`, `policies.yaml`) | Prometheus rules below | 4 for `severity=critical`, 2 for `warning` |
| Watchtower | `WATCHTOWER_NOTIFICATION_URL` in `docker-compose.yml` (`logger://` + `ntfy://`) | each update session's report (what was updated, what failed) and its startup message | 2 (the loud failure alert is the OpenSearch `watchtower-update-failure` monitor on the `logger://` output) |
| Cron jobs | `scripts/cron-notify.sh` wrapping every crontab line | "cron job failed: NAME" once per failure streak; "recovered" on the next success | 4 failed, 2 recovered |
| NUT (UPS) | `infrastructure/nut/upssched-cmd` | on battery, low battery, shutdown, back on mains | 2–5 (`infrastructure/nut/README.md`) |
| Dependency-Track | `scripts/sbom-scan.sh`, `scripts/deptrack-setup.sh` | new HIGH/CRITICAL CVEs | 3 |

### Grafana rules (Prometheus)

Grafana-managed rules, evaluated every minute against the `prometheus` datasource and
provisioned read-only from the repo (edit the YAML, then recreate grafana; UI edits are
refused). Group key `alertname`, so one push per rule even when several series fire.
Critical alerts repeat every 4 h while firing, warnings once a day; resolved notices go
to the same contact point.

| Rule (uid) | Condition | For | Severity |
|---|---|---|---|
| Prometheus target down (`hl-target-down`) | `up < 1` (prometheus, cadvisor, node-exporter, nginx-exporter) | 5 m | critical |
| Disk above 85% (`hl-disk-85`) | `/`, `/data`, `/storage`, `/mnt/nas` used > 85% | 15 m | warning |
| Disk above 95% (`hl-disk-95`) | same mounts > 95% | 5 m | critical |
| Host memory pressure (`hl-memory-low`) | `MemAvailable/MemTotal < 10%` | 15 m | critical |
| Container restarting repeatedly (`hl-restart-loop`) | > 5 starts of one container name in 30 min (cAdvisor `container_start_time_seconds`) | 1 m | critical |
| Backup not succeeded in 26 h (`hl-backup-stale`) | `homelab_cron_last_success_timestamp_seconds{job="backup"}` older than 26 h | 10 m | warning (backstop to the OpenSearch heartbeat monitor) |
| Certificate expires in under 14 days (`hl-cert-expiry`) | any `ssl_certificate` in `production.conf` | 1 h | warning (LE renews at 30 days; renewal failures already alert) |
| UPS on battery (`hl-ups-on-battery`) | `homelab_ups_on_battery > 0` | 1 m | warning (backstop; NUT sends the loud push itself) |
| Alert metrics stale (`hl-alert-metrics-stale`) | `logs/textfile/homelab-alerts.prom` missing or > 10 min old | 5 m | warning |
| node-exporter textfile parse error (`hl-textfile-error`) | `node_textfile_scrape_error > 0` | 10 m | warning |

Query errors (Prometheus unreachable) raise a `DatasourceError` alert after the same
pending period. No Alertmanager: Grafana's built-in one does routing and grouping.

**Textfile metrics** (node-exporter, `logs/textfile/` → `/textfile`):
- `scripts/emit_alert_metrics.sh` (cron every minute) → `homelab-alerts.prom`:
  `homelab_cert_not_after_timestamp_seconds{cert}`, `homelab_ups_up`,
  `homelab_ups_on_battery`, `homelab_ups_low_battery`,
  `homelab_ups_battery_charge_percent`, `homelab_ups_battery_runtime_seconds`,
  `homelab_ups_load_percent` (from `upsc ups@localhost`, no login needed).
- `scripts/cron-notify.sh` → `cron-<job>.prom`: `homelab_cron_last_run_timestamp_seconds`,
  `homelab_cron_last_exit_code`, `homelab_cron_last_success_timestamp_seconds` (label `job`).
- `scripts/sbom-scan.sh` → `deptrack.prom` (Dependency-Track portfolio gauges).

### Cron wrapper

Every line in the server's crontab (`crontab -l` as `mcheli`; versioned in
`infrastructure/cron/crontab`) runs through
`scripts/cron-notify.sh NAME COMMAND [ARGS...]`; the log redirect stays at the end of
the line and env assignments go before the wrapper. A non-zero exit sends one push;
further failures stay quiet (state in `logs/cron-notify/NAME.failed`) until a success
sends "recovered". New cron jobs must be added the same way:

```cron
0 2 * * * /home/mcheli/83rr-poweredge/scripts/cron-notify.sh backup /home/mcheli/83rr-poweredge/scripts/backup.sh >> /home/mcheli/83rr-poweredge/logs/backup.log 2>&1
```

### Testing the routes

- OpenSearch + Kuma: `scripts/alert-test.sh` (weekly from the Mac mini's homelab check).
- Grafana: Alerting → Contact points → `ntfy-high` / `ntfy-low` → Test, or as admin
  `POST /apis/notifications.alerting.grafana.app/v1beta1/namespaces/default/receivers/<name>/test`
  (`<name>` from `GET …/receivers`, e.g. `bnRmeS1oaWdo` for ntfy-high) with body
  `{"integration": {"uid": "ntfy-high", "type": "webhook", "settings": {…url, httpMethod, authorization_scheme…}, "secureFields": {"authorization_credentials": true}}, "alert": {"labels": {"alertname": "TEST …"}, "annotations": {"summary": "TEST …"}}}`
  (the stored token is reused; Grafana 13 removed the old `/api/alertmanager/grafana/config/api/v1/receivers/test`).
- Watchtower: a `--run-once --monitor-only` watchtower container that matches no
  container sends only its startup message; set `WATCHTOWER_NOTIFICATION_TITLE_TAG=TEST`.
- Cron wrapper: `CRON_NOTIFY_STATE_DIR=$(mktemp -d) CRON_NOTIFY_TEXTFILE_DIR=/nonexistent scripts/cron-notify.sh TEST-cron-route false`
  sends one "cron job failed: TEST-cron-route" and leaves no state.
- Read what arrived: `GET https://ntfy.markcheli.com/homelab/json?poll=1&since=15m`
  as the `mark` user (or the cache.db query in `scripts/alert-test.sh`).

---

## Status page

<https://status.markcheli.com> is Uptime Kuma's public status page (slug
`homelab`), built by `scripts/setup_uptime_kuma.py` (re-runnable: it upserts the
monitors, tags, the ntfy notification and the page). Groups: **Public services**
(the `*.markcheli.com` sites), **LAN-only services** (the `*.ops` tools), and
**External SaaS dependencies**; it also checks the ARK and Minecraft game servers.
Kuma probes from the server itself, which is honest about reachability but not an
outside view: an outage of the whole host or its internet link takes the page down
with it. It has its own Let's Encrypt certificate (`letsencrypt-status.crt`) so LAN
clients get a trusted certificate too.

---

## Ideas not built yet

- **Request IDs**: no app propagates an `X-Request-Id` from nginx, so following one
  request across nginx and an app means matching times and paths by hand.
- **Alert inhibition**: when nginx or the whole host is down, every dependent check
  fires. Neither OpenSearch alerting nor Grafana's built-in Alertmanager is set up to
  suppress the dependants.
- **Off-host probe**: a check from outside the house (a free external monitor
  against `www.markcheli.com`) would catch the case the status page can't.

---

## History

- 2026-05: Fluent Bit → OpenSearch pipeline, ingest pipeline, saved dashboards.
- 2026-10-31: ntfy replaced email alerting (SendGrid, whose free plan had silently
  stopped sending on 2026-09-04).
- 2026-11: Docker events, nginx host/upstream fields, Postgres and fail2ban parsing,
  log-noise cleanup; Grafana alert rules, Watchtower reports and the cron wrapper
  joined ntfy (PRs #88, #89).

**Last updated**: 2026-11-25
