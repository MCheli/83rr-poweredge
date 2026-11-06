# OpenSearch Alerting

Setup for the OpenSearch alerting plugin, which evaluates queries on a
schedule and sends notifications when triggers fire.

## Architecture

```
OpenSearch ───query───▶ Monitor ──fires─▶ Trigger ──sends─▶ Destination
                       (5 min)         (threshold)         (email / webhook)
```

- **Monitors** in `monitors/` — one JSON file per monitor. Their actions
  publish to the notification channel `ntfy-homelab` (see "ntfy" below).
- **Destinations** hold a token, so they're created via API after deploy
  (`wire-ntfy.py`), not stored in this repo.
- **Channel notes** below cover ntfy (current), the retired SendGrid setup,
  and the Uptime Kuma push-webhook idea.

## Apply monitors

`apply-monitors.py` upserts `monitors/*.json` by monitor name: it PUTs over the
live monitor with the same name (same id, so alert history stays attached) or
POSTs a new one. It never deletes. `--dry-run` changes nothing: it runs every
monitor once through `_execute?dryrun=true` and prints, per trigger, whether
it fired and the rendered ntfy message (and fails if a query, trigger script or
template errors, or if the rendered body isn't valid JSON).

```bash
# On the server, from the repo root
python3 infrastructure/opensearch/config/alerting/apply-monitors.py --dry-run
python3 infrastructure/opensearch/config/alerting/apply-monitors.py                  # all
python3 infrastructure/opensearch/config/alerting/apply-monitors.py nginx-5xx-burst   # just one
# From the Mac mini
python3 infrastructure/opensearch/config/alerting/apply-monitors.py --ssh 83rr-poweredge --dry-run
```

`wire-ntfy.py` is separate: it owns the `ntfy-homelab` channel (token) and only
rewrites leftover SendGrid-format actions; it leaves these monitors alone.

### Rollout order for log-format / pipeline changes

The monitors read fields that only exist once the log pipeline produces them
(`host`, `upstream_addr`, `upstream_status`, `upstream_response_time`,
`request_time` from nginx; `compose_project`, `compose_oneoff`, `exit_code`
from Docker events),
so apply in this order:

1. **Index template + ingest pipeline** (new mappings, nginx parsing, the
   stricter `healthcheck` tag). The template only affects indices created after
   it (tomorrow's daily index); the pipeline applies to new documents at once.
   ```bash
   docker cp infrastructure/opensearch/config/index_template_logs_homelab.json opensearch:/tmp/t.json
   docker exec opensearch curl -s -X PUT localhost:9200/_index_template/logs-homelab -H 'Content-Type: application/json' -d @/tmp/t.json
   docker cp infrastructure/opensearch/config/ingest_pipeline_homelab_logs.json opensearch:/tmp/p.json
   docker exec opensearch curl -s -X PUT localhost:9200/_ingest/pipeline/homelab-logs -H 'Content-Type: application/json' -d @/tmp/p.json
   ```
2. **nginx log format**: reload, don't recreate.
   `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload`
3. **Fluent Bit** (Lua filter adds `compose_project` / `compose_oneoff` /
   `exit_code`): `docker compose restart fluent-bit`. Docker events emitted
   while Fluent Bit restarts are lost (the docker_events input has no replay),
   and the *old* `container-died` monitor (any die, any container) pages on
   Fluent Bit's own die. Expect that one page; do it in a quiet window.
4. **Monitors**, straight after the step-3 check so the old `container-died`
   doesn't keep running against the new fields: `apply-monitors.py --dry-run`,
   then `apply-monitors.py`.

Check between steps: an nginx line in Discover should have `host` and
`upstream_addr`, and a `docker container start …` event should have
`compose_project`. Until step 3 is live, `container-died` sees no events
(it requires `compose_project`), so don't apply the monitors early.

`--dry-run` itself is quiet, but dry-running *bucket-level* probe monitors makes
OpenSearch log "Failed to retrieve sample documents for alert …" at ERROR
(~40 lines in 5 min, 2026-11-05). `error-rate-5m` excludes that message from
`opensearch` so experiments don't self-page.

## Destinations

### ntfy push (current, since 2026-10-31)

OpenSearch and Uptime Kuma both alert through the self-hosted ntfy service
(`ntfy` in `docker-compose.yml`, config `infrastructure/ntfy/server.yml`),
public at `https://ntfy.markcheli.com` so phones can subscribe. Everything
publishes to topic **`homelab`**.

Auth is deny-all; users and tokens live in `user.db` in the `ntfy_data` volume:

| User | Access | Used by |
|---|---|---|
| `alerts` | write-only `homelab` | its token is `NTFY_PUBLISH_TOKEN` in `.env`; OpenSearch + Kuma send `Authorization: Bearer <token>` |
| `mark` | read-only `homelab` | the ntfy app on Mark's phone (server `https://ntfy.markcheli.com`, subscribe to `homelab`) |

```bash
docker exec ntfy ntfy user list                 # users + access
docker exec -it ntfy ntfy user add mark         # prompts for a password
docker exec ntfy ntfy access mark homelab ro
docker exec ntfy ntfy token list alerts         # rotate: token add / token remove, then update .env and re-run both wire steps
```

**OpenSearch:** `python3 infrastructure/opensearch/config/alerting/wire-ntfy.py`
(re-runnable) creates/updates channel `ntfy-homelab` (webhook `http://ntfy/`
on the infrastructure network, Bearer token read from `.env`) and rewrites any
action still in SendGrid mail JSON into an ntfy JSON publish:
`{"topic":"homelab","title":…,"message":…,"priority":…}`. Priority follows the
trigger severity (1→5 … 5→1). `--dry-run` shows the plan; `--test` /
`--test-only` fire a one-off monitor through the channel. (OpenSearch's own
"Send test message" button can't work here: its body isn't ntfy JSON.)

**Uptime Kuma:** notification "ntfy → homelab" (type ntfy, server `http://ntfy`,
access-token auth), linked to every monitor that had the SendGrid notification
and set as the default for new monitors. `infrastructure/ntfy/kuma-ntfy.js`
does this from inside the container (`wire`, token on stdin) and sends a test
through Kuma's own ntfy provider (`test`).

**Weekly proof it still works:** `scripts/alert-test.sh` sends one test via each
path and checks both landed in ntfy's cache. The Mac mini's weekly homelab
check runs it every week (`act.sh alert-test`) and reports a failure as
"alerting broken".

### SendGrid email (retired 2026-10-31)

Every alert from 2026-09-04 to 2026-10-31 failed with HTTP 401 "Maximum
credits exceeded": the account is on SendGrid's retired free plan, which has
0 send credits. The API key itself was valid. The old webhook channel
`sendgrid-mail`, Kuma's SendGrid notification and `SENDGRID_API_KEY` were
removed the same day. Kept below for reference only.

Once you have a SendGrid API key with **Full Access** scope and a verified
sender for `status@markcheli.com`:

```bash
export SENDGRID_API_KEY='SG.xxxxxxxx'
docker exec opensearch curl -s -X POST "http://localhost:9200/_plugins/_alerting/destinations" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "name": "sendgrid-email",
  "type": "email",
  "email": {
    "email_account_id": "<email-account-id-from-step-below>",
    "recipients": [{"type":"email","email":"mpcheli7@gmail.com"}]
  }
}
JSON
)"
```

OpenSearch's email destination needs an "email account" first, which holds
the SMTP creds:

```bash
docker exec opensearch curl -s -X POST "http://localhost:9200/_plugins/_alerting/destinations/email_accounts" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "name": "sendgrid-smtp",
  "host": "smtp.sendgrid.net",
  "port": 587,
  "method": "start_tls",
  "from": "status@markcheli.com",
  "username": "apikey",
  "password": "${SENDGRID_API_KEY}"
}
JSON
)"
```

(SendGrid's SMTP convention: username is literally the string `apikey`,
password is the API key itself.)

### Uptime Kuma webhook

Kuma can ingest "Push" monitors via incoming webhooks. The pattern:
1. Create a "Push" monitor in Kuma's UI for the alert family (e.g.,
   "OpenSearch error-rate-5m").
2. Kuma generates a token URL like `https://status.markcheli.com/api/push/<token>?status=up&msg=OK&ping=`.
3. Configure an OpenSearch alerting destination of type `custom_webhook`
   pointing at that URL with `status=down` (or `up` on resolution).
4. Wire monitors to call the destination on trigger.

This lets the status page reflect "OpenSearch says X is broken" even
though Kuma isn't probing X itself.

```bash
docker exec opensearch curl -s -X POST "http://localhost:9200/_plugins/_alerting/destinations" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "kuma-error-rate-push",
    "type": "custom_webhook",
    "custom_webhook": {
      "url": "https://status.markcheli.com/api/push/<token>?status=down&msg=opensearch+detected+errors",
      "method": "GET",
      "header_params": {}
    }
  }'
```

## Monitor templates in monitors/

| File | What | Severity |
|---|---|---|
| `error-rate-5m.json` | ERROR/CRITICAL/FATAL count > 10 in 5 min, per-service (see below) | 2 |
| `nginx-5xx-burst.json` | nginx 5xx > 5 in 5 min (see below) | 1 |
| `container-died.json` | a compose container OOMed, or died and stayed down (see below) | 1 |
| `healthcheck-failure.json` | 3+ failed genuine healthchecks in 5 min (see below) | 2 |
| `auth-bruteforce.json` | nginx status 401 from same client_ip > 30 in 5 min | 2 |
| `watchtower-update-failure.json` | watchtower Failed != 0 in last 1h | 3 |

The files' actions already point at `ntfy-homelab`; run `wire-ntfy.py` once
after a fresh deploy so the channel exists. As of 2026-11-05 all 12 files are
live.

### Phone alerts: what each one means (redesign, 2026-11)

A 2026-11-05 audit found 86% of alerts since the ntfy cutover fired within 10
minutes of a container restart (Watchtower, compose up, the demo reseed cron,
backup/SBOM scratch containers). So the noisy monitors now look at restarts
before deciding how loudly to tell you.

**Restart gating** (`nginx-5xx-burst`, `error-rate-5m`, `healthcheck-failure`).
Each monitor runs one search that is "primary condition OR lifecycle events";
filter aggregations split it into `aggregations.p` (the primary hits) and
`aggregations.lc` (start/die/kill/stop/restart/oom events in the last 10 min for
real containers). Alerting only allows one search input per monitor, hence the
single combined search. Two triggers share the condition:

- no restart in the last 10 min: normal priority (5 for 5xx, 4 for the others),
  tag `rotating_light`;
- a restart happened: priority 2 (no buzz), title prefixed `[deploy noise]`,
  first line "During restart of … - likely deploy noise", tags
  `arrows_counterclockwise`, `deploy-noise`.

**A crash loop is not a deploy.** A third filter aggregation, `aggregations.cl`,
lists real containers with 3+ `die` events in the last 15 min. If there is one,
the gate counts as closed: the normal-priority trigger fires and its message
says "Crash-looping: X died N× in 15 min, so this is not deploy noise". Without
this, a container in a restart loop would keep the gate open forever and turn
every other alert into priority 2.

"Real containers" means Docker events with a `compose_project` label, minus
Compose one-offs (`compose_oneoff: True`, i.e. `docker compose run`, and as a
fallback any `*-run-*` name), the reseed-cron demos (`tallied-demo`,
`tasks-demo`), `zz-scratch-*`, `*-test` (incl. `*-nginx-test`), Docker's
auto-names (`adjective_name`), Compose's temporary `<12 hex>_name` renames,
`watchtower` and `uptime-kuma`. The same list is used by `container-died`.

**Every message** carries: a title with the service and count; the time of the
first and last matching event in ET (computed by a Painless script field; Mustache
can't convert time zones), plus the monitor window in UTC; the breakdowns below;
which containers restarted in the last 10 min; a likely cause and what to do; and a
Discover link with the query and time range filled in (also the notification's
tap action and a button, next to a Dashboard button). Log values are cleaned up
by script (quotes, backslashes and control characters removed, length capped)
because Mustache here does no JSON escaping and the message is a JSON body.

| Monitor | Fires when | Suppressed / ignored | Message shows |
|---|---|---|---|
| `nginx-5xx-burst` | > 5 nginx 5xx in 5 min | Home Assistant 502/504 (upstream `192.168.1.121:*` or vhost `home.markcheli.com`). Restart: priority 2 | status split, vhosts, top 3 paths, clients, upstream |
| `error-rate-5m` | > 10 ERROR/CRITICAL/FATAL lines in 5 min | known scanner noise on `*-db` and plex; Docker die/kill events (they're `container-died`'s job). Restart: priority 2 | top services with their top 3 messages |
| `healthcheck-failure` | ≥ 3 genuine probe failures (5xx, 401, 403 or 404) in 5 min | 2xx/3xx. Restart: priority 2 | per-service status, top probes as "container status path from client UA" |
| `container-died` | (a) an `oom` event in the last 5 min (priority 4, throttled 30 min), (b) a `die` 3-8 min ago with no later `start` (priority 5), or (c) 3+ `die`s of one container in 15 min, a crash loop (priority 4, throttled 30 min) | everything that isn't a "real container" (above) | per container: time, exit code, whether it came back (OOM), die count (crash loop) |

Clients are summarised as "your own devices" (XFF is exactly `173.48.155.66`),
"LAN client" (no XFF, private IP), "internet <ip>", or "internet (bad XFF)" when
the value isn't an IP. Cloudflare appends the address it saw to any XFF the
client sent, so only the last hop is used, and a multi-hop chain is labelled
"client-set XFF" (and never counts as your own devices).

`container-died` is a query-level monitor whose search does the "stayed down"
logic itself: per container, a `bucket_selector` keeps only those whose latest
start is older than their latest die. The die window (`{{period_end}}` -8 min
to -3 min, half-open) moves with the 5-minute schedule and is anchored to the
scheduled period rather than `now`, so windows tile exactly and each death is
judged once; that's why stayed-down has no throttle. "Stayed down 3+ min"
really means "no start between the die and the evaluation": a container that
was down for 6 min but is back by the time the monitor runs stays silent. A
crash loop (die, auto-restart, die …) always has a later start, which is why
it has its own `container-crash-loop` trigger. (Bucket-level monitors were tried: their Mustache context only has
the bucket key, not the per-bucket numbers.) Exit codes: 137 = SIGKILL
(OOM-kill or `docker kill`), 143 = SIGTERM (`docker stop`), 0 = clean exit,
-1 = not recorded.

**healthcheck:true** is set by the ingest pipeline only for a health path plus
one of: an Uptime Kuma UA (no XFF, or XFF starting with our own `173.48.155.66`:
Kuma hairpins through Cloudflare); a loopback client (Docker HEALTHCHECK inside
the container); or, at nginx, a LAN client with no X-Forwarded-For and a probe
UA (curl/wget/python). Since only genuine probes are tagged, the monitor doesn't
filter on XFF again, and a probe getting 404 counts (a route broke). Before 2026-11 any request to `/api/health` counted, so an
internet scanner getting 404/301 paged as a healthcheck failure.

**Home Assistant availability is owned by Uptime Kuma** (monitor "Home
Assistant", 60 s interval with retries), not by `nginx-5xx-burst`. HA runs on
its own box and is restarted by hand; the HA phone app's reconnect loop then
produces dozens of 502s that say nothing Kuma doesn't already know.
