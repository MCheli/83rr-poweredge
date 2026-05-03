# OpenSearch Alerting

Setup for the OpenSearch alerting plugin, which evaluates queries on a
schedule and sends notifications when triggers fire.

## Architecture

```
OpenSearch ───query───▶ Monitor ──fires─▶ Trigger ──sends─▶ Destination
                       (5 min)         (threshold)         (email / webhook)
```

- **Monitors** in `monitors/` — one JSON file per monitor.
- **Destinations** are configured per-environment (need API keys), so
  they're created via API after deploy, not stored in this repo.
- **Channel notes** below cover SendGrid + Uptime Kuma webhook.

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

### SendGrid email (status@markcheli.com)

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

After import, point each monitor's trigger `actions[].destination_id` at
the SendGrid + Kuma destinations created above.
