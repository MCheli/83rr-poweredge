# Observability — Logs, Dashboards, Alerting

Living reference for the homelab observability stack: what fields are
indexed, what dashboards exist (or *should* exist), what alerts to wire,
and how to extend each piece.

The data plumbing is described in
`infrastructure/opensearch/config/`. This doc is the consumer-side
manual — what you can do with what's there.

---

## Index pattern

- **Name**: `logs-homelab-*`
- **Time field**: `@timestamp`
- **Saved index pattern ID**: `logs-homelab` (created via Dashboards API)

Open Discover at <https://logs.ops.markcheli.com/app/discover> and it
should be the default index pattern.

## Available fields

Set in `infrastructure/opensearch/config/index_template_logs_homelab.json`.
Refreshing the index-pattern field list after schema changes:
*Stack Management → Index Patterns → logs-homelab → Refresh field list*.

| Field | Type | Where it comes from | Notes |
|---|---|---|---|
| `@timestamp` | date | Fluent Bit | Authoritative time field. Use this in dashboards. |
| `time` | date | Fluent Bit (docker JSON) | Original Docker write timestamp. Usually within 1 ms of `@timestamp`. |
| `app_time` | keyword | Per-app grok | App's own embedded timestamp (varied formats — kept as keyword to avoid mapping rejection). |
| `container_name` | keyword | Lua filter | One of the values shown by `docker ps`. |
| `container_id` | keyword | Lua filter | First 12 chars of the container ID. |
| `stream` | keyword | Docker | `stdout` / `stderr`. |
| `log` | text | Fluent Bit (raw) | Full unparsed line. Always present. |
| `msg` | text | Per-app grok | Parsed message body (no level/timestamp). |
| `level` | keyword | Per-app grok / fallback regex | Normalized to UPPERCASE. Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`. |
| `logger` | keyword | Per-app grok | Logger / module name (Python apps, Grafana, etc.). |
| `method` | keyword | nginx / app HTTP grok | `GET`, `POST`, etc. |
| `path` | keyword | nginx / app HTTP grok | URL path without query string. |
| `status` | integer | nginx / app HTTP grok | HTTP status code. |
| `bytes` | long | nginx / edge-tts grok | Response body size. |
| `request_time` | float | edge-tts grok | Seconds. |
| `client_ip` | ip | nginx / app HTTP grok | Real `ip` type — supports CIDR queries. |
| `x_forwarded_for` | keyword | nginx grok | The XFF chain (string). |
| `client_port` | integer | uvicorn / asgi grok | Source port from the request. |
| `referrer` | keyword | nginx grok | HTTP Referer. |
| `user_agent` | keyword | nginx grok | UA string. |
| `http_version` | keyword | nginx / app HTTP grok | `1.0`, `1.1`, `2.0`, `3.0`. |
| `healthcheck` | boolean | Pipeline | `true` if path matches `/health`, `/api/health`, `/api/v1/health`, etc. **Successful healthchecks are dropped at Fluent Bit, so any healthcheck doc with `status:!=200` is a real signal.** |
| `ingest_error` | text | Pipeline `on_failure` | Set when grok / a processor failed. Filter on `_exists_:ingest_error` to find broken parses. |
| `source` | keyword | Multiple | Either Prometheus's `source=...` field, or the Fluent Bit `source: file` marker for Plex/Seafile file inputs. |

---

## Recommended dashboards

Build these in OpenSearch Dashboards' UI from the queries below, then
export the saved-objects ndjson and add it to `infrastructure/opensearch/config/`
so a fresh deploy can re-import.

### 1. Service Health Overview

**Purpose**: single-pane "is anything on fire" view. First thing you
look at in the morning.

**Time picker**: last 24h, refresh 30s.

**Panels**:
- **Error rate by service** (line chart):
  - Y: count of `level:ERROR OR level:CRITICAL OR level:FATAL`
  - X: `@timestamp` 5-min buckets
  - Split: `container_name` keyword, top 10
- **Warning rate by service** (line chart, same as above with `level:WARNING`)
- **Log volume by service** (stacked area):
  - Y: count
  - X: `@timestamp` 5-min buckets
  - Split: `container_name`, top 10
- **Recent ERRORs** (saved search table):
  - Filter: `level:ERROR OR level:CRITICAL OR level:FATAL`
  - Columns: `@timestamp`, `container_name`, `logger`, `msg`, `log`
  - Sort: `@timestamp` desc
- **Top error messages** (data table):
  - Aggregation: terms on `msg.keyword` (or `log.keyword` if `msg` not parsed)
  - Filter: `level:ERROR`
  - Top 25

### 2. HTTP Edge (nginx)

**Purpose**: spot edge problems — 5xx spikes, slow paths, abuse.

**Filters available globally**: `container_name:nginx`, exclude `healthcheck:true`.

**Panels**:
- **Request rate** (line chart): count over `@timestamp` 5-min buckets.
- **Status code distribution** (stacked area):
  - Filters: `status:[200 TO 299]`, `[300 TO 399]`, `[400 TO 499]`, `[500 TO 599]`
  - Split each as a series.
- **5xx burst** (line chart):
  - Y: count where `status:[500 TO 599]`
  - This is the alert candidate.
- **Top paths** (data table):
  - Terms on `path`, top 25, exclude `healthcheck:true`
- **Top 4xx paths** (data table): same with `status:[400 TO 499]` filter.
- **Top client IPs** (data table): terms on `client_ip`, top 25.
- **Auth failures by IP** (data table): `status:401`, terms on `client_ip`. Catches brute-force.
- **User agent breakdown** (pie / table): terms on `user_agent`. Useful for spotting scanners.

### 3. Per-Service Detail (template)

**Purpose**: one reusable dashboard, parameterized by service name.

**Variable**: `container_name` (controls input on the dashboard).

**Panels**:
- Log volume over time (line)
- Level breakdown (pie: `level`)
- Recent ERROR / WARNING saved search
- Top loggers (terms on `logger`)
- Most-logged messages (terms on `msg.keyword`)

### 4. Container Lifecycle

**Purpose**: see what Watchtower is doing, who restarted, who failed.

**Panels**:
- **Watchtower sessions** (table): `container_name:watchtower AND msg:"Session done"`. Columns: `@timestamp`, `extras` (which contains `Failed`, `Scanned`, `Updated`).
- **Watchtower failures**: `container_name:watchtower AND level:ERROR`.
- **Container starts** (saved search): `log:"Starting" OR log:"started"` filtered to first-line-of-life patterns. (Cleaner version: ingest Docker daemon events — see "Future improvements" below.)
- **OOM events**: `log:"OOMKilled" OR log:"out of memory"` across all containers.

### 5. Security / Edge

**Purpose**: separate the "actual user" traffic from "internet noise."

**Panels**:
- **Failed auth attempts**: `status:401`, columns `@timestamp`, `client_ip`, `path`, `user_agent`.
- **Scanner traffic**: requests where `path` matches `/cgi-bin/`, `/.env`, `wp-`, `phpMyAdmin`, etc. Saved search.
- **TLS probe garbage** (the `\x16\x03\x01...` lines): `log:"\\x16\\x03\\x01"`.
- **LAN allowlist denies**: filter `nginx` for 403 on `*.ops.markcheli.com` host.

---

## Useful Discover queries

Copy-paste into the search bar at the top of Discover. Lucene syntax.

| What | Query |
|---|---|
| All errors right now | `level:(ERROR OR CRITICAL OR FATAL)` |
| All warnings | `level:WARNING` |
| Server errors at the edge | `container_name:nginx AND status:[500 TO 599]` |
| Failed auth | `container_name:nginx AND status:401` |
| Slow requests (edge-tts) | `container_name:edge-tts AND request_time:>1.0` |
| Healthcheck failures | `healthcheck:true AND status:!=200` |
| Watchtower update failures | `container_name:watchtower AND extras:"Failed=*" AND NOT extras:"Failed=0"` |
| Things the parser couldn't understand | `_exists_:ingest_error` |
| One specific service | `container_name:tallied` |
| Path pattern at the edge | `container_name:nginx AND path:/api/*` |
| One client IP | `client_ip:192.168.1.150` |
| External (non-LAN) requests | `container_name:nginx AND NOT client_ip:192.168.0.0/16 AND NOT client_ip:10.0.0.0/8` |

---

## Alerting

Set up via OpenSearch Dashboards → *Alerting* → *Monitors*. Each monitor
has triggers; each trigger has destinations (where to send the alert).

### Recommended monitors

Names matter — keep them stable so a status page can subscribe by name.

| Monitor | Query / threshold | Severity |
|---|---|---|
| `error-rate-5m` | per-service: `level:(ERROR OR CRITICAL OR FATAL)` count > 10 in 5 min | 2 (high) |
| `nginx-5xx-burst` | `container_name:nginx AND status:[500 TO 599]` count > 5 in 5 min | 1 (critical) |
| `auth-bruteforce` | `container_name:nginx AND status:401` from same `client_ip` count > 30 in 5 min | 2 |
| `healthcheck-failure` | `healthcheck:true AND status:!=200` any in 5 min | 2 |
| `watchtower-update-failure` | `container_name:watchtower AND extras:"Failed=*" AND NOT extras:"Failed=0"` any in 1h | 3 |
| `parser-failures-spike` | `_exists_:ingest_error` count > 100 in 1h | 4 (warning) |
| `backup-no-success-24h` | (separate cron job that writes a heartbeat doc to OpenSearch when backup succeeds; alert on its absence) | 1 |
| `disk-pressure` | (Prometheus side — `node_filesystem_avail_bytes` < 10%) | 2 |
| `service-down-prom` | (Prometheus `up{} == 0` for 5 min) | 1 |

The last three need separate plumbing — backup heartbeat needs a small
`echo '{"source":"backup","status":"ok"}' | curl ...` line at the end of
`scripts/backup.sh`, and the Prometheus alerts go through Prometheus
Alertmanager (or via OpenSearch's Prometheus integration if simpler).

### Destination notes

OpenSearch's built-in destinations: Slack, Microsoft Teams, custom webhook,
Amazon Chime, email (via SMTP).

For email from `status@markcheli.com`, you need an outbound SMTP relay.
Options the operator has called out (see status-page setup below):
- **Resend** — recommended. Configure with API key + verified domain.
- **SendGrid** — same shape.
- **AWS SES** — cheapest at scale; requires DNS verification.
- **Google Workspace SMTP relay** — if Workspace is in use.

The OpenSearch alerting destination type for SMTP is "Email": configure
host, port (587 STARTTLS), credentials, and the from-address. **Set the
display name to the monitor name** so the status page can route on it.

---

## Status page

External-facing status page lives at <https://status.markcheli.com>
(planned, see operator decisions). Two architectural patterns:

### Pattern A — Uptime Kuma as the source of truth

Uptime Kuma runs its own polling on every public endpoint
(`www.markcheli.com`, `flask.markcheli.com`, etc.) and exposes a status
page. OpenSearch alerts pipe in via webhook to update incident state in
Kuma. The page reflects Kuma's polling + Kuma's incident log.

**Pros**: status page is honest about reachability (it's a real probe,
not a log-derived inference). Kuma has a built-in public status page UI
that's reasonable out of the box.

**Cons**: now you have two systems doing checks (Kuma + OpenSearch
alerts). Need to keep them in sync.

### Pattern B — Static page generated from OpenSearch + Prometheus

A small script runs every minute, queries OpenSearch (recent error
counts, healthcheck failures) + Prometheus (`up{}`, latency), and writes
an HTML page nginx serves at `status.markcheli.com`.

**Pros**: single source of truth (the metrics+logs you already have).
No new service.

**Cons**: more code to maintain. No incident-tracking UI.

**Recommendation**: Pattern A with Uptime Kuma. It's the homelab default
for a reason — works well, low maintenance, integrates with everything.

---

## Future improvements

- **Docker daemon events** — currently no ingestion of "container started"
  / "container stopped" / "container died" events. The
  `docker events --format json` stream could be tailed by a tiny
  sidecar and shipped to OpenSearch under a `docker-events-*` index.
  This would give clean restart / OOM detection without grepping log
  text. Useful for the Container Lifecycle dashboard.
- **Trace IDs** — none of the apps emit request IDs that we propagate
  across nginx → app. Adding `X-Request-Id` headers and a parse field
  would make end-to-end debugging much easier.
- **Saved-object export** — once dashboards are built in the UI,
  export ndjson and check it in to
  `infrastructure/opensearch/config/saved_objects/`. Then a fresh
  deploy can `POST _dashboards/api/saved_objects/_import` to restore.
- **Alert inhibition** — if `nginx` goes down (alerts fire for every
  service that depends on it), suppress dependent alerts. OpenSearch
  alerting doesn't do inhibition natively; Prometheus Alertmanager does.
  Worth migrating service-down alerts there.

---

**Last updated**: 2026-05-03 (Phases 1-3 deployed; Phase 4-5 outlined,
not yet built).
