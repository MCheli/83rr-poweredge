#!/bin/bash
# Generate Self-Signed SSL Certificates for Local Development
# This script creates certificates for localhost HTTPS access

set -e

CERT_DIR="infrastructure/nginx/dev-certs"
DAYS=365

echo "🔐 Generating self-signed certificates for local development..."

# Create certificate directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Generate private key
echo "  🔑 Generating private key..."
openssl genrsa -out "$CERT_DIR/localhost.key" 2048

# Generate certificate signing request
echo "  📝 Generating certificate signing request..."
openssl req -new -key "$CERT_DIR/localhost.key" -out "$CERT_DIR/localhost.csr" -subj "/C=US/ST=Local/L=Development/O=83RR PowerEdge/OU=Dev/CN=localhost"

# Create extensions file for Subject Alternative Names
echo "  📋 Creating certificate extensions..."
cat > "$CERT_DIR/localhost.ext" << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

# Generate self-signed certificate
echo "  🏆 Generating self-signed certificate..."
openssl x509 -req -in "$CERT_DIR/localhost.csr" -signkey "$CERT_DIR/localhost.key" -out "$CERT_DIR/localhost.crt" -days $DAYS -extfile "$CERT_DIR/localhost.ext"

# Create combined certificate file for NGINX
echo "  🔗 Creating combined certificate..."
cp "$CERT_DIR/localhost.crt" "$CERT_DIR/fullchain.pem"
cp "$CERT_DIR/localhost.key" "$CERT_DIR/privkey.pem"

# Set proper permissions
echo "  🔒 Setting certificate permissions..."
chmod 644 "$CERT_DIR"/*.crt "$CERT_DIR"/*.pem
chmod 600 "$CERT_DIR"/*.key

# Clean up intermediate files
rm "$CERT_DIR/localhost.csr" "$CERT_DIR/localhost.ext"

echo "✅ Development certificates generated successfully!"
echo "📁 Certificates located in: $CERT_DIR/"
echo "🌐 You can now access services via HTTPS at localhost"
echo ""
echo "ℹ️  Note: Your browser will show a security warning for self-signed certificates."
echo "   This is normal for development. Click 'Advanced' and 'Proceed to localhost'."