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

```bash
# From the host (uses LAN-only OpenSearch endpoint inside the container)
for f in infrastructure/opensearch/config/alerting/monitors/*.json; do
  name=$(basename "$f" .json)
  docker cp "$f" opensearch:/tmp/monitor.json
  docker exec opensearch curl -s -X POST \
    "http://localhost:9200/_plugins/_alerting/monitors" \
    -H 'Content-Type: application/json' -d @/tmp/monitor.json \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print('${name}:', r.get('_id','FAILED'), r.get('error',''))"
done
```

To update an existing monitor, use `PUT /_plugins/_alerting/monitors/<id>`.

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
| `error-rate-5m.json` | ERROR/CRITICAL/FATAL count > 10 in 5 min, per-service | 2 |
| `nginx-5xx-burst.json` | nginx status 500-599 count > 5 in 5 min | 1 |
| `auth-bruteforce.json` | nginx status 401 from same client_ip > 30 in 5 min | 2 |
| `healthcheck-failure.json` | healthcheck:true AND status != 200, any in 5 min | 2 |
| `watchtower-update-failure.json` | watchtower Failed != 0 in last 1h | 3 |

The files' actions already point at `ntfy-homelab`; run `wire-ntfy.py` once
after a fresh deploy so the channel exists. Live today: 9 of the 12 files
(`docker-exec-into-sock-container`, `security-external-db-conn` and
`security-unexpected-listen-port` are not applied).
