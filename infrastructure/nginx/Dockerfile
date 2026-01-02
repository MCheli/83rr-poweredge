# NGINX Reverse Proxy for 83RR PowerEdge Infrastructure
# Supports both development (localhost) and production (domain) routing

FROM nginx:alpine

# Install OpenSSL for certificate generation and envsubst for environment substitution
RUN apk add --no-cache openssl gettext

# Create certificate directories
RUN mkdir -p /etc/nginx/certs /etc/nginx/dev-certs /etc/nginx/templates

# Copy all configuration files
COPY conf.d/ /etc/nginx/conf.d/

# Copy certificates (if they exist)
COPY certs/ /etc/nginx/certs/ 2>/dev/null || true
COPY dev-certs/ /etc/nginx/dev-certs/ 2>/dev/null || true

# Set permissions
RUN chmod -R 644 /etc/nginx/certs/ /etc/nginx/dev-certs/ 2>/dev/null || true

# Create entrypoint script
RUN cat > /docker-entrypoint.sh << 'EOF'
#!/bin/sh
set -e

echo "🔧 Configuring NGINX for environment: ${INFRASTRUCTURE_ENV:-development}"

# Determine which configuration to use
if [ "${INFRASTRUCTURE_ENV:-development}" = "production" ]; then
    echo "📋 Using production configuration with domain routing"
    # Ensure production config exists
    if [ ! -f /etc/nginx/conf.d/production.conf ]; then
        echo "❌ Production config missing!"
        exit 1
    fi
    # Remove development config to avoid conflicts
    rm -f /etc/nginx/conf.d/default.conf
else
    echo "📋 Using development configuration with localhost routing"
    # Remove production config to avoid conflicts
    rm -f /etc/nginx/conf.d/production.conf
fi

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