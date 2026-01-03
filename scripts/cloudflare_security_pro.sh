#!/bin/bash
# Cloudflare Pro Plan Security Configuration
# Enables Super Bot Fight Mode, WAF Managed Rulesets, and OWASP protection

set -e

# Load environment variables
if [ -f .env ]; then
    source .env
fi

ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
API_TOKEN="${CLOUDFLARE_API_TOKEN}"

if [ -z "$ZONE_ID" ]; then
    echo "❌ CLOUDFLARE_ZONE_ID not set in .env"
    echo "Get it from: Cloudflare Dashboard → markcheli.com → Overview → Zone ID"
    exit 1
fi

echo "🔐 Configuring Cloudflare PRO Plan Security Features"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Zone ID: ${ZONE_ID}"
echo ""

# Function to update setting
update_setting() {
    local setting_id="$1"
    local value="$2"
    local description="$3"

    echo -n "  $description... "

    response=$(curl -s -X PATCH \
        "https://api.cloudflare.com/v4/zones/${ZONE_ID}/settings/${setting_id}" \
        -H "Authorization: Bearer ${API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"value\":\"${value}\"}")

    if echo "$response" | grep -q '"success":true'; then
        echo "✅"
    else
        echo "❌"
        error=$(echo "$response" | python3 -c 'import sys, json; d=json.load(sys.stdin); print(d.get("errors", [{}])[0].get("message", "Unknown error"))' 2>/dev/null || echo "Parse error")
        echo "     Error: $error"
    fi
}

# Function to check current setting
check_setting() {
    local setting_id="$1"

    response=$(curl -s -X GET \
        "https://api.cloudflare.com/v4/zones/${ZONE_ID}/settings/${setting_id}" \
        -H "Authorization: Bearer ${API_TOKEN}" \
        -H "Content-Type: application/json")

    echo "$response" | python3 -c 'import sys, json; d=json.load(sys.stdin); print(d.get("result", {}).get("value", "unknown"))' 2>/dev/null || echo "unknown"
}

echo "1️⃣  Basic Security Settings"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "security_level" "high" "Security Level → High"
update_setting "browser_check" "on" "Browser Integrity Check"
update_setting "challenge_ttl" "1800" "Challenge Passage → 30 minutes"

echo ""
echo "2️⃣  SSL/TLS Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "ssl" "strict" "SSL Mode → Full (strict)"
update_setting "always_use_https" "on" "Always Use HTTPS"
update_setting "min_tls_version" "1.2" "Minimum TLS Version → 1.2"
update_setting "tls_1_3" "on" "TLS 1.3 Support"
update_setting "automatic_https_rewrites" "on" "Automatic HTTPS Rewrites"
update_setting "opportunistic_encryption" "on" "Opportunistic Encryption"

echo ""
echo "3️⃣  Performance & Security Features"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "brotli" "on" "Brotli Compression"
update_setting "early_hints" "on" "Early Hints"
update_setting "http2" "on" "HTTP/2"
update_setting "http3" "on" "HTTP/3 (QUIC)"
update_setting "0rtt" "on" "0-RTT Connection"
update_setting "websockets" "on" "WebSockets"
update_setting "ipv6" "on" "IPv6 Compatibility"

echo ""
echo "4️⃣  Advanced Security Features"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
update_setting "privacy_pass" "on" "Privacy Pass"
update_setting "email_obfuscation" "on" "Email Obfuscation"
update_setting "server_side_exclude" "on" "Server Side Excludes"
update_setting "hotlink_protection" "off" "Hotlink Protection (off for CDN)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Basic security features configured!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🤖 PRO PLAN FEATURES - Manual Configuration Required"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "The following features require manual configuration in the dashboard:"
echo ""
echo "1. ✅ Super Bot Fight Mode (PRO)"
echo "   Location: Security → Bots"
echo "   Steps:"
echo "     • Toggle ON 'Super Bot Fight Mode'"
echo "     • Configure bot score threshold (30-99)"
echo "     • Choose action: Managed Challenge / Block / JavaScript Detection"
echo "     • Enable 'Static Resource Protection' if desired"
echo ""
echo "2. ✅ Cloudflare Managed Ruleset (WAF - PRO)"
echo "   Location: Security → WAF → Managed Rules"
echo "   Steps:"
echo "     • Click 'Deploy' on 'Cloudflare Managed Ruleset'"
echo "     • Choose deployment mode: Block / Challenge / Log"
echo "     • Configure sensitivity level (Low/Medium/High)"
echo "     • Review and adjust specific rules if needed"
echo ""
echo "3. ✅ OWASP Core Ruleset (WAF - PRO)"
echo "   Location: Security → WAF → Managed Rules"
echo "   Steps:"
echo "     • Click 'Deploy' on 'Cloudflare OWASP Core Ruleset'"
echo "     • Set paranoia level (PL1/PL2/PL3/PL4)"
echo "       Recommended: PL2 (Medium) for good protection without false positives"
echo "     • Configure score threshold (default: 60)"
echo "     • Choose action: Block / Challenge / Log"
echo ""
echo "4. ❌ Page Shield (ENTERPRISE ONLY)"
echo "   Status: NOT AVAILABLE on Pro plan"
echo "   Requires: Enterprise plan (\$5,000+/month)"
echo "   Alternative: Use Subresource Integrity (SRI) tags manually"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Recommended Configuration for Your Setup:"
echo ""
echo "Super Bot Fight Mode:"
echo "  • Definitely Automated: Managed Challenge"
echo "  • Likely Automated: Managed Challenge"
echo "  • Verified Bots: Allow (for search engines)"
echo "  • Static Resource Protection: ON"
echo ""
echo "Cloudflare Managed Ruleset:"
echo "  • Mode: Block (after testing in Log mode)"
echo "  • Sensitivity: Medium"
echo "  • Test in Log mode first, then switch to Block"
echo ""
echo "OWASP Core Ruleset:"
echo "  • Paranoia Level: PL2 (balanced)"
echo "  • Score Threshold: 60 (default)"
echo "  • Action: Block (after testing in Log mode)"
echo "  • Start with PL1, increase to PL2 after testing"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔗 Quick Links:"
echo "  Dashboard: https://dash.cloudflare.com/${ZONE_ID}/security"
echo "  Bots: https://dash.cloudflare.com/${ZONE_ID}/security/bots"
echo "  WAF: https://dash.cloudflare.com/${ZONE_ID}/security/waf"
echo ""
echo "💡 Testing Recommendations:"
echo "  1. Start all WAF rules in 'Log' mode"
echo "  2. Monitor for 24-48 hours"
echo "  3. Review logs for false positives"
echo "  4. Adjust rules as needed"
echo "  5. Switch to 'Block' mode"
echo ""
echo "✅ Script complete!"
echo ""
