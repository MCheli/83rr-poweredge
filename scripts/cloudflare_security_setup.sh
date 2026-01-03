#!/bin/bash
# Cloudflare Free Plan Security Configuration
# Enables maximum security features available on Free plan

set -e

# Load environment variables
source .env

ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
API_TOKEN="${CLOUDFLARE_API_TOKEN}"

if [ -z "$ZONE_ID" ]; then
    echo "❌ CLOUDFLARE_ZONE_ID not set in .env"
    echo "Get it from: Cloudflare Dashboard → Domain → Overview → Zone ID"
    exit 1
fi

echo "🔐 Configuring Cloudflare Security Features (Free Plan)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Function to update setting
update_setting() {
    local setting_id="$1"
    local value="$2"
    local description="$3"

    echo -n "Setting $description... "

    response=$(curl -s -X PATCH \
        "https://api.cloudflare.com/v4/zones/${ZONE_ID}/settings/${setting_id}" \
        -H "Authorization: Bearer ${API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"value\":\"${value}\"}")

    if echo "$response" | grep -q '"success":true'; then
        echo "✅"
    else
        echo "❌"
        echo "   Error: $(echo "$response" | python3 -c 'import sys, json; print(json.load(sys.stdin).get("errors", []))')"
    fi
}

echo ""
echo "1. Security Level Settings"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "security_level" "high" "Security Level → High"
update_setting "browser_check" "on" "Browser Integrity Check"
update_setting "challenge_ttl" "1800" "Challenge Passage → 30 minutes"

echo ""
echo "2. SSL/TLS Settings"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "ssl" "strict" "SSL Mode → Full (strict)"
update_setting "always_use_https" "on" "Always Use HTTPS"
update_setting "min_tls_version" "1.2" "Minimum TLS Version → 1.2"
update_setting "tls_1_3" "on" "TLS 1.3 Support"
update_setting "automatic_https_rewrites" "on" "Automatic HTTPS Rewrites"

echo ""
echo "3. Performance & Security"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "brotli" "on" "Brotli Compression"
update_setting "early_hints" "on" "Early Hints"
update_setting "http2" "on" "HTTP/2"
update_setting "http3" "on" "HTTP/3 (QUIC)"
update_setting "0rtt" "on" "0-RTT Connection"

echo ""
echo "4. DDoS Protection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "ipv6" "on" "IPv6 Compatibility"
update_setting "websockets" "on" "WebSockets"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Free plan security features configured!"
echo ""
echo "📋 Manual Steps (require dashboard access):"
echo ""
echo "1. Enable Bot Fight Mode:"
echo "   Dashboard → Security → Bots → Toggle 'Bot Fight Mode'"
echo ""
echo "2. Create Firewall Rules (5 max on free plan):"
echo "   Dashboard → Security → WAF → Firewall Rules"
echo "   Suggested rules:"
echo "   - Block known bad bots"
echo "   - Challenge suspicious countries"
echo "   - Block common attack patterns"
echo ""
echo "3. Configure Rate Limiting (1 free rule):"
echo "   Dashboard → Security → WAF → Rate Limiting Rules"
echo "   Example: Limit /api/* to 100 requests per minute"
echo ""
echo "4. Enable Email Security (Free):"
echo "   Dashboard → Email → Email Routing → Enable"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 To enable advanced features (WAF, OWASP, Super Bot):"
echo "   Upgrade to Pro plan: \$20/month"
echo "   cloudflare.com/plans"
echo ""
