#!/bin/bash
# Let's Encrypt Certificate Renewal Script
# Renews *.ops.markcheli.com wildcard certificate and reloads NGINX

set -e

# Activate virtual environment
cd /home/mcheli/83rr-poweredge
source venv/bin/activate

# Renew certificate (certbot will only renew if within 30 days of expiration)
certbot renew \
    --dns-cloudflare \
    --dns-cloudflare-credentials ~/.secrets/cloudflare.ini \
    --config-dir ~/letsencrypt/config \
    --work-dir ~/letsencrypt/work \
    --logs-dir ~/letsencrypt/logs \
    --quiet

# Copy renewed certificates to NGINX directory
cp ~/letsencrypt/config/live/ops.markcheli.com/fullchain.pem \
   ~/83rr-poweredge/infrastructure/nginx/certs/letsencrypt-ops-markcheli.crt

cp ~/letsencrypt/config/live/ops.markcheli.com/privkey.pem \
   ~/83rr-poweredge/infrastructure/nginx/certs/letsencrypt-ops-markcheli.key

# Test NGINX configuration
docker compose -f /home/mcheli/83rr-poweredge/docker-compose.yml exec nginx nginx -t

# Reload NGINX to apply new certificates
docker compose -f /home/mcheli/83rr-poweredge/docker-compose.yml exec nginx nginx -s reload

echo "Certificate renewal completed successfully at $(date)"
