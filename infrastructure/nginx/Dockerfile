# NGINX Reverse Proxy for 83RR PowerEdge Infrastructure
# Supports both development (localhost) and production (domain) routing

FROM nginx:alpine

# Install OpenSSL for certificate generation and envsubst for environment substitution
RUN apk add --no-cache openssl gettext

# Create certificate directories
RUN mkdir -p /etc/nginx/certs /etc/nginx/dev-certs /etc/nginx/templates

# Copy all configuration files
COPY conf.d/ /etc/nginx/conf.d/

# Copy production certificates
COPY certs/ /etc/nginx/certs/

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