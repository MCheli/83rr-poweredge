#!/bin/bash
set -e

# Manual Wildcard SSL Certificate Setup
# This script helps you obtain and configure wildcard SSL certificates manually
# for use with Traefik without requiring DNS API access.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="/home/mcheli/traefik/certs"
DYNAMIC_DIR="/home/mcheli/traefik/dynamic"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

create_directories() {
    print_step "Creating certificate directories..."

    sudo mkdir -p "$CERTS_DIR"
    sudo mkdir -p "$DYNAMIC_DIR"
    sudo mkdir -p "/home/mcheli/letsencrypt"

    # Set proper permissions
    sudo chown -R $USER:$USER "$CERTS_DIR"
    sudo chown -R $USER:$USER "$DYNAMIC_DIR"
    sudo chown -R $USER:$USER "/home/mcheli/letsencrypt"

    print_success "Directories created successfully"
}

check_certbot() {
    if ! command -v certbot &> /dev/null; then
        print_error "certbot is not installed"
        echo "Please install certbot:"
        echo "  sudo apt update && sudo apt install certbot"
        echo "  or"
        echo "  sudo snap install certbot --classic"
        exit 1
    fi
    print_success "certbot is available"
}

obtain_certificates() {
    print_step "Setting up certificate acquisition..."

    echo
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  MANUAL CERTIFICATE ACQUISITION REQUIRED${NC}"
    echo -e "${YELLOW}============================================${NC}"
    echo
    echo "You need to obtain wildcard certificates manually using certbot."
    echo "This requires DNS verification through your domain provider."
    echo
    echo "Run these commands in separate terminal sessions:"
    echo
    echo -e "${BLUE}1. For *.markcheli.com (public services):${NC}"
    echo "   sudo certbot certonly --manual --preferred-challenges dns \\"
    echo "     --email mpcheli7@gmail.com \\"
    echo "     --server https://acme-v02.api.letsencrypt.org/directory \\"
    echo "     --agree-tos \\"
    echo "     -d '*.markcheli.com' -d 'markcheli.com'"
    echo
    echo -e "${BLUE}2. For *.ops.markcheli.com (LAN services):${NC}"
    echo "   sudo certbot certonly --manual --preferred-challenges dns \\"
    echo "     --email mpcheli7@gmail.com \\"
    echo "     --server https://acme-v02.api.letsencrypt.org/directory \\"
    echo "     --agree-tos \\"
    echo "     -d '*.ops.markcheli.com'"
    echo
    echo -e "${YELLOW}During each process:${NC}"
    echo "1. certbot will ask you to create a TXT record"
    echo "2. Go to your DNS provider (Squarespace Domains)"
    echo "3. Add the TXT record as instructed"
    echo "4. Wait for DNS propagation (use: dig TXT _acme-challenge.markcheli.com)"
    echo "5. Press Enter to continue"
    echo
    echo -e "${GREEN}After both certificates are obtained, run this script again with --install${NC}"
    echo
}

install_certificates() {
    print_step "Installing certificates for Traefik..."

    # Check if certificates exist
    MARKCHELI_CERT="/etc/letsencrypt/live/markcheli.com"
    OPS_CERT="/etc/letsencrypt/live/ops.markcheli.com"

    if [[ ! -d "$MARKCHELI_CERT" ]]; then
        print_error "Certificate for *.markcheli.com not found at $MARKCHELI_CERT"
        echo "Please obtain the certificate first using the commands above."
        exit 1
    fi

    if [[ ! -d "$OPS_CERT" ]]; then
        print_error "Certificate for *.ops.markcheli.com not found at $OPS_CERT"
        echo "Please obtain the certificate first using the commands above."
        exit 1
    fi

    # Copy certificates to Traefik directory
    print_step "Copying certificates..."

    sudo cp "$MARKCHELI_CERT/fullchain.pem" "$CERTS_DIR/wildcard-markcheli.crt"
    sudo cp "$MARKCHELI_CERT/privkey.pem" "$CERTS_DIR/wildcard-markcheli.key"

    sudo cp "$OPS_CERT/fullchain.pem" "$CERTS_DIR/wildcard-ops-markcheli.crt"
    sudo cp "$OPS_CERT/privkey.pem" "$CERTS_DIR/wildcard-ops-markcheli.key"

    # Set proper permissions
    sudo chown $USER:$USER "$CERTS_DIR"/*.crt "$CERTS_DIR"/*.key
    sudo chmod 644 "$CERTS_DIR"/*.crt
    sudo chmod 600 "$CERTS_DIR"/*.key

    print_success "Certificates installed successfully"

    # Copy dynamic configuration
    print_step "Installing Traefik dynamic configuration..."
    cp "$BASE_DIR/infrastructure/traefik/dynamic/certificates.yml" "$DYNAMIC_DIR/"
    print_success "Dynamic configuration installed"
}

verify_certificates() {
    print_step "Verifying certificate installation..."

    # Check certificate files
    for cert in "wildcard-markcheli.crt" "wildcard-markcheli.key" "wildcard-ops-markcheli.crt" "wildcard-ops-markcheli.key"; do
        if [[ -f "$CERTS_DIR/$cert" ]]; then
            print_success "Found: $cert"
        else
            print_error "Missing: $cert"
            return 1
        fi
    done

    # Check certificate validity
    print_step "Checking certificate validity..."

    echo "*.markcheli.com certificate:"
    openssl x509 -in "$CERTS_DIR/wildcard-markcheli.crt" -text -noout | grep -E "(Subject|DNS:|Not After)"

    echo
    echo "*.ops.markcheli.com certificate:"
    openssl x509 -in "$CERTS_DIR/wildcard-ops-markcheli.crt" -text -noout | grep -E "(Subject|DNS:|Not After)"

    print_success "Certificate verification complete"
}

deploy_services() {
    print_step "Deploying services with manual certificates..."

    # Deploy Traefik first
    cd "$BASE_DIR/infrastructure/traefik"
    docker compose down
    docker compose up -d

    sleep 10

    # Deploy other services
    cd "$BASE_DIR/infrastructure/personal-website"
    docker compose down
    docker compose up -d

    cd "$BASE_DIR/infrastructure/jupyter"
    docker compose down
    docker compose up -d

    cd "$BASE_DIR/infrastructure/opensearch"
    docker compose down
    docker compose up -d

    print_success "All services deployed"
}

test_ssl() {
    print_step "Testing SSL certificates..."

    echo "Testing public services:"
    curl -I -k https://www.markcheli.com 2>/dev/null | head -1 || echo "❌ www.markcheli.com failed"
    curl -I -k https://flask.markcheli.com 2>/dev/null | head -1 || echo "❌ flask.markcheli.com failed"

    echo
    echo "Testing LAN services (from local network):"
    curl -I -k https://traefik-local.ops.markcheli.com 2>/dev/null | head -1 || echo "❌ traefik-local.ops.markcheli.com failed"
    curl -I -k https://jupyter.ops.markcheli.com 2>/dev/null | head -1 || echo "❌ jupyter.ops.markcheli.com failed"

    print_success "SSL testing complete"
}

create_renewal_script() {
    print_step "Creating certificate renewal script..."

    cat > "$BASE_DIR/scripts/renew_wildcard_ssl.sh" << 'EOF'
#!/bin/bash
# Wildcard SSL Certificate Renewal Script
# Run this script 30 days before certificates expire

set -e

CERTS_DIR="/home/mcheli/traefik/certs"

echo "🔄 Starting certificate renewal process..."

# Renew certificates
echo "📋 Renewing *.markcheli.com certificate..."
sudo certbot renew --cert-name markcheli.com

echo "📋 Renewing *.ops.markcheli.com certificate..."
sudo certbot renew --cert-name ops.markcheli.com

# Copy renewed certificates
echo "📁 Updating Traefik certificates..."
sudo cp /etc/letsencrypt/live/markcheli.com/fullchain.pem $CERTS_DIR/wildcard-markcheli.crt
sudo cp /etc/letsencrypt/live/markcheli.com/privkey.pem $CERTS_DIR/wildcard-markcheli.key
sudo cp /etc/letsencrypt/live/ops.markcheli.com/fullchain.pem $CERTS_DIR/wildcard-ops-markcheli.crt
sudo cp /etc/letsencrypt/live/ops.markcheli.com/privkey.pem $CERTS_DIR/wildcard-ops-markcheli.key

# Set permissions
sudo chown $USER:$USER $CERTS_DIR/*.crt $CERTS_DIR/*.key
sudo chmod 644 $CERTS_DIR/*.crt
sudo chmod 600 $CERTS_DIR/*.key

# Restart Traefik to load new certificates
echo "🔄 Restarting Traefik..."
cd "$(dirname "$0")/../infrastructure/traefik"
docker compose restart

echo "✅ Certificate renewal complete!"
EOF

    chmod +x "$BASE_DIR/scripts/renew_wildcard_ssl.sh"
    print_success "Renewal script created at scripts/renew_wildcard_ssl.sh"
}

show_usage() {
    echo "Manual Wildcard SSL Certificate Setup"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --install     Install already-obtained certificates"
    echo "  --verify      Verify certificate installation"
    echo "  --deploy      Deploy services with certificates"
    echo "  --test        Test SSL certificate functionality"
    echo "  --renew       Create renewal script"
    echo "  --help        Show this help message"
    echo
    echo "Typical workflow:"
    echo "1. $0                    # Shows certificate acquisition commands"
    echo "2. [Obtain certificates manually using provided commands]"
    echo "3. $0 --install          # Install certificates for Traefik"
    echo "4. $0 --deploy           # Deploy all services"
    echo "5. $0 --test             # Test SSL functionality"
}

main() {
    echo -e "${BLUE}🔐 Manual Wildcard SSL Certificate Setup${NC}"
    echo "========================================"

    case "${1:-}" in
        --install)
            create_directories
            install_certificates
            verify_certificates
            create_renewal_script
            ;;
        --verify)
            verify_certificates
            ;;
        --deploy)
            deploy_services
            ;;
        --test)
            test_ssl
            ;;
        --renew)
            create_renewal_script
            ;;
        --help)
            show_usage
            ;;
        *)
            create_directories
            check_certbot
            obtain_certificates
            ;;
    esac
}

main "$@"