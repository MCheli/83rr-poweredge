#!/bin/bash
# Let's Encrypt Certificate Renewal Script
# Renews *.ops.markcheli.com wildcard certificate and reloads NGINX

set -e

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
