# NGINX Reverse Proxy for 83RR PowerEdge Infrastructure
# Supports both development (localhost) and production (domain) routing

# Pinned (was floating nginx:alpine). 1.30.8 (bumped 2026-11-28, was 1.30.7) fixes
# CVE-2026-132779 (this config doesn't enable ssl_early_data); 1.30.7 was the
# 2026-11-18 nginx security release (HTTP/2, HTTP/3, resolver, TLS 1.3 fixes).
# Alpine 3.24 base. Digest-pinned: bump tag and digest together.
FROM nginx:1.30.8-alpine@sha256:8eb04fe3b385090e9aa02961f77398ad09b6bf33ab07f6669a5bb7acce22c0d3

# Pick up Alpine security fixes newer than the base image (the 1.30.8 base still has
# zlib 1.3.2-r1 and libxml2 2.13.9-r3; this gets zlib 1.4-r0 and libxml2 2.13.9-r5).
# Install OpenSSL for certificate generation and
# envsubst for environment substitution
RUN apk upgrade --no-cache && apk add --no-cache openssl gettext

# Create certificate directories
RUN mkdir -p /etc/nginx/certs /etc/nginx/dev-certs /etc/nginx/templates

# Forward nginx logs to Docker (stdout/stderr) for log aggregation
RUN ln -sf /dev/stdout /var/log/nginx/access.log && \
    ln -sf /dev/stderr /var/log/nginx/error.log

# Copy main nginx.conf with rate limiting zones
COPY nginx.conf /etc/nginx/nginx.conf

# Copy all configuration files
COPY conf.d/ /etc/nginx/conf.d/

# Copy production certificates
COPY certs/ /etc/nginx/certs/

# Copy htpasswd for basic auth
COPY .htpasswd /etc/nginx/.htpasswd

# Set certificate permissions
RUN chmod -R 644 /etc/nginx/certs/*.crt 2>/dev/null || true && \
    chmod -R 600 /etc/nginx/certs/*.key 2>/dev/null || true

# Create entrypoint script
RUN cat > /docker-entrypoint.sh << 'EOF'
#!/bin/sh
set -e

echo "🔧 Configuring NGINX for environment: ${INFRASTRUCTURE_ENV:-development}"

# Test NGINX configuration
echo "🧪 Testing NGINX configuration..."
nginx -t

# Start NGINX
echo "🚀 Starting NGINX..."
exec nginx -g 'daemon off;'
EOF

# Make entrypoint executable
RUN chmod +x /docker-entrypoint.sh

# Expose ports
EXPOSE 80 443

# Use custom entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]