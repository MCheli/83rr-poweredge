#!/usr/bin/env python3
"""
Cloudflare Authentication Setup
Interactive script to configure Cloudflare API credentials securely
"""

import os
import sys
import getpass
from pathlib import Path
import requests

def check_api_token(token, email=None):
    """Test if API token is valid"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get('https://api.cloudflare.com/client/v4/user/tokens/verify', headers=headers)
        if response.status_code == 200:
            result = response.json()
            if result['success']:
                print(f"✅ API token is valid")
                return True
            else:
                print(f"❌ API token verification failed: {result.get('errors', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}: Failed to verify API token")
            return False
    except Exception as e:
        print(f"❌ Error testing API token: {str(e)}")
        return False

def get_user_zones(token):
    """Get list of zones (domains) accessible to the token"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get('https://api.cloudflare.com/client/v4/zones', headers=headers)
        if response.status_code == 200:
            result = response.json()
            if result['success']:
                zones = result['result']
                return [(zone['name'], zone['id']) for zone in zones]
        return []
    except Exception as e:
        print(f"⚠️  Could not fetch zones: {str(e)}")
        return []

def update_env_file(token, email, domains):
    """Update .env file with Cloudflare credentials"""
    env_file = Path(__file__).parent.parent / '.env'
    env_lines = []

    # Read existing .env file if it exists
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                # Skip existing Cloudflare settings
                if not line.startswith(('CLOUDFLARE_API_TOKEN=', 'CLOUDFLARE_EMAIL=', 'CLOUDFLARE_DOMAINS=')):
                    env_lines.append(line.rstrip())

    # Add Cloudflare configuration
    env_lines.extend([
        '',
        '# Cloudflare DNS Management',
        f'CLOUDFLARE_API_TOKEN={token}',
        f'CLOUDFLARE_EMAIL={email}',
        f'CLOUDFLARE_DOMAINS={",".join(domains)}',
        ''
    ])

    # Write updated .env file
    with open(env_file, 'w') as f:
        f.write('\n'.join(env_lines))

    # Set restrictive permissions on .env file
    os.chmod(env_file, 0o600)

    print(f"✅ Updated .env file: {env_file}")

def interactive_setup():
    """Interactive setup process"""
    print("🔧 Cloudflare API Token Setup")
    print("=" * 60)

    print("\n📋 You'll need:")
    print("   1. Cloudflare account with your domains added")
    print("   2. API token with DNS edit permissions")
    print("   3. Your Cloudflare email address")

    print("\n🔗 To create an API token:")
    print("   1. Go to: https://dash.cloudflare.com/profile/api-tokens")
    print("   2. Click 'Create Token'")
    print("   3. Use 'Custom token' template")
    print("   4. Set permissions:")
    print("      - Zone:Zone Settings:Read")
    print("      - Zone:Zone:Read")
    print("      - Zone:DNS:Edit")
    print("   5. Include your domains in 'Zone Resources'")
    print("   6. Click 'Continue' and 'Create Token'")

    # Get email
    print("\n📧 Cloudflare Account Email:")
    email = input("   Enter your Cloudflare email: ").strip()

    if not email or '@' not in email:
        print("❌ Valid email address required")
        return False

    # Get API token
    print("\n🔑 Cloudflare API Token:")
    print("   (Input will be hidden for security)")
    token = getpass.getpass("   Enter your API token: ").strip()

    if not token:
        print("❌ API token required")
        return False

    # Test the token
    print("\n🧪 Testing API token...")
    if not check_api_token(token, email):
        return False

    # Get accessible zones
    print("\n🌍 Checking accessible domains...")
    zones = get_user_zones(token)

    if not zones:
        print("⚠️  No zones found - make sure your token has the right permissions")
        domains = ['markcheli.com', 'ops.markcheli.com']  # Default
        print(f"   Using default domains: {', '.join(domains)}")
    else:
        print("   Found domains:")
        domains = []
        for domain, zone_id in zones:
            print(f"   ✅ {domain} (ID: {zone_id})")
            domains.append(domain)

    # Update .env file
    print("\n💾 Saving configuration...")
    update_env_file(token, email, domains)

    print("\n🎉 Cloudflare configuration complete!")
    print("\n🔬 Testing DNS manager...")

    # Test the DNS manager
    try:
        # Set environment variables for the test
        os.environ['CLOUDFLARE_API_TOKEN'] = token
        os.environ['CLOUDFLARE_EMAIL'] = email

        # Import and test the DNS manager
        sys.path.append(str(Path(__file__).parent))
        from cloudflare_dns_manager import CloudflareDNSManager

        dns = CloudflareDNSManager()
        print("✅ DNS manager initialized successfully")

        # Test zone access
        for domain in domains:
            zone_id = dns.get_zone_id(domain)
            if zone_id:
                print(f"✅ {domain}: Zone accessible (ID: {zone_id[:8]}...)")
            else:
                print(f"❌ {domain}: Zone not accessible")

        return True

    except Exception as e:
        print(f"❌ Error testing DNS manager: {str(e)}")
        return False

def main():
    """Main setup function"""
    try:
        success = interactive_setup()

        if success:
            print("\n" + "=" * 60)
            print("🚀 Next steps:")
            print("   1. Test DNS management:")
            print("      python scripts/cloudflare_dns_manager.py test")
            print("   2. List current DNS records:")
            print("      python scripts/cloudflare_dns_manager.py list --domain markcheli.com")
            print("   3. Sync infrastructure DNS:")
            print("      python scripts/cloudflare_dns_manager.py sync")

            sys.exit(0)
        else:
            print("\n❌ Setup failed. Please check your credentials and try again.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n🛑 Setup cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()