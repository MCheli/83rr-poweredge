#!/bin/bash
# Let's Encrypt Certificate Renewal Script
# Renews *.ops.markcheli.com wildcard certificate and reloads NGINX

set -e

# Emit a failure doc on any error so OpenSearch alerting fires.
emit_failure_doc() {
    local exit_code=$?
    [ "$exit_code" -eq 0 ] && return
    local now_iso=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
    docker exec opensearch curl -s -X POST \
        "http://localhost:9200/logs-homelab-$(date +%Y.%m.%d)/_doc" \
        -H 'Content-Type: application/json' \
        -d "{\"@timestamp\":\"${now_iso}\",\"container_name\":\"letsencrypt-renew\",\"event_type\":\"renew_failed\",\"level\":\"ERROR\",\"msg\":\"LE cert renewal failed (exit ${exit_code})\"}" \
        >/dev/null 2>&1 || true
}
trap emit_failure_doc EXIT ERR

# Configuration - use environment variables or defaults
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LETSENCRYPT_DIR="${LETSENCRYPT_DIR:-$HOME/letsencrypt}"
CLOUDFLARE_CREDENTIALS="${CLOUDFLARE_CREDENTIALS:-$HOME/.secrets/cloudflare.ini}"
DOMAIN="${DOMAIN:-ops.markcheli.com}"

# Activate virtual environment
cd "$PROJECT_ROOT"
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Renew certificate (certbot will only renew if within 30 days of expiration)
certbot renew \
    --dns-cloudflare \
    --dns-cloudflare-credentials "$CLOUDFLARE_CREDENTIALS" \
    --config-dir "$LETSENCRYPT_DIR/config" \
    --work-dir "$LETSENCRYPT_DIR/work" \
    --logs-dir "$LETSENCRYPT_DIR/logs" \
    --quiet

# Copy renewed certificates to NGINX directory
cp "$LETSENCRYPT_DIR/config/live/$DOMAIN/fullchain.pem" \
   "$PROJECT_ROOT/infrastructure/nginx/certs/letsencrypt-ops-markcheli.crt"

cp "$LETSENCRYPT_DIR/config/live/$DOMAIN/privkey.pem" \
   "$PROJECT_ROOT/infrastructure/nginx/certs/letsencrypt-ops-markcheli.key"

# status.markcheli.com is a separate single-name cert (LAN clients resolve
# to origin and would otherwise see the untrusted CloudFlare Origin CA).
# Mirror the renewed copy if certbot rolled it.
if [ -f "$LETSENCRYPT_DIR/config/live/status.markcheli.com/fullchain.pem" ]; then
    cp "$LETSENCRYPT_DIR/config/live/status.markcheli.com/fullchain.pem" \
       "$PROJECT_ROOT/infrastructure/nginx/certs/letsencrypt-status.crt"
    cp "$LETSENCRYPT_DIR/config/live/status.markcheli.com/privkey.pem" \
       "$PROJECT_ROOT/infrastructure/nginx/certs/letsencrypt-status.key"
fi

# Test NGINX configuration
docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec nginx nginx -t

# Reload NGINX to apply new certificates
docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec nginx nginx -s reload

echo "Certificate renewal completed successfully at $(date)"

# Emit success heartbeat to OpenSearch so we can alert on its absence.
NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
docker exec opensearch curl -s -X POST \
    "http://localhost:9200/logs-homelab-$(date +%Y.%m.%d)/_doc" \
    -H 'Content-Type: application/json' \
    -d "{\"@timestamp\":\"${NOW_ISO}\",\"container_name\":\"letsencrypt-renew\",\"event_type\":\"renew_completed\",\"level\":\"INFO\",\"msg\":\"LE cert renewal cycle completed\"}" \
    >/dev/null 2>&1 || true
