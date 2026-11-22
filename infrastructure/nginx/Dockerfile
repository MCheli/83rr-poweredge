# NGINX Reverse Proxy for 83RR PowerEdge Infrastructure
# Supports both development (localhost) and production (domain) routing

# Pinned (was floating nginx:alpine). 1.30.7 (2026-11-21, was 1.30.6) is the
# 2026-11-18 nginx security release (HTTP/2, HTTP/3, resolver, TLS 1.3 fixes);
# 1.30.6 already covered CVE-2026-15176 and CVE-2026-97629. Digest-pinned:
# bump tag and digest together.
FROM nginx:1.30.7-alpine@sha256:caf4e1e032a20f9c3c5e28fc7f25ffd768ad8677b4975c54193075997b3a97e3

# Pick up Alpine security fixes newer than the base image (e.g. zlib 1.4-r0, brotli-libs
# for CVE-2026-111497). Install OpenSSL for certificate generation and
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