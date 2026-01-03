#!/usr/bin/env python3
"""
Quick Cloudflare Environment Setup
Simple script to add Cloudflare credentials to .env file
"""

import os
from pathlib import Path

def update_env_file(api_token, email):
    """Update .env file with Cloudflare credentials"""
    env_file = Path(__file__).parent.parent / '.env'

    # Read existing .env file or create new one
    env_lines = []
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                # Skip existing Cloudflare settings
                if not line.startswith(('CLOUDFLARE_API_TOKEN=', 'CLOUDFLARE_EMAIL=', 'CLOUDFLARE_DOMAINS=')):
                    env_lines.append(line.rstrip())
    else:
        # Copy from example if .env doesn't exist
        env_example = env_file.parent / '.env.example'
        if env_example.exists():
            with open(env_example, 'r') as f:
                for line in f:
                    if not line.startswith(('CLOUDFLARE_API_TOKEN=', 'CLOUDFLARE_EMAIL=', 'CLOUDFLARE_DOMAINS=')):
                        env_lines.append(line.rstrip())

    # Add Cloudflare configuration
    env_lines.extend([
        '',
        '# Cloudflare DNS Management - Added by setup script',
        f'CLOUDFLARE_API_TOKEN={api_token}',
        f'CLOUDFLARE_EMAIL={email}',
        'CLOUDFLARE_DOMAINS=markcheli.com,ops.markcheli.com',
        ''
    ])

    # Write updated .env file
    with open(env_file, 'w') as f:
        f.write('\n'.join(env_lines))

    # Set restrictive permissions
    os.chmod(env_file, 0o600)

    print(f"✅ Updated .env file: {env_file}")
    print("🔒 Set secure file permissions (600)")

def main():
    """Main function"""
    print("🔧 Quick Cloudflare Credentials Setup")
    print("=" * 50)

    # Get credentials from command line arguments or environment
    import sys

    if len(sys.argv) == 3:
        # Command line arguments
        email = sys.argv[1]
        api_token = sys.argv[2]
    else:
        # Check environment variables
        email = os.getenv('CF_EMAIL')
        api_token = os.getenv('CF_TOKEN')

        if not email or not api_token:
            print("Usage:")
            print("  python set_cloudflare_env.py <email> <api_token>")
            print("  OR set CF_EMAIL and CF_TOKEN environment variables")
            print("")
            print("Example:")
            print("  python set_cloudflare_env.py user@example.com abc123token456")
            print("  # OR")
            print("  export CF_EMAIL=user@example.com")
            print("  export CF_TOKEN=abc123token456")
            print("  python set_cloudflare_env.py")
            sys.exit(1)

    print(f"📧 Email: {email}")
    print(f"🔑 Token: {api_token[:8]}...{api_token[-4:] if len(api_token) > 12 else '***'}")

    # Update .env file
    update_env_file(api_token, email)

    print("\n🧪 Testing configuration...")

    # Test the configuration
    os.environ['CLOUDFLARE_API_TOKEN'] = api_token
    os.environ['CLOUDFLARE_EMAIL'] = email

    try:
        # Import and test
        sys.path.append(str(Path(__file__).parent))
        from cloudflare_dns_manager import CloudflareDNSManager

        dns = CloudflareDNSManager()
        print("✅ DNS manager initialized successfully")

        # Test zones
        for domain in ['markcheli.com', 'ops.markcheli.com']:
            zone_id = dns.get_zone_id(domain)
            if zone_id:
                print(f"✅ {domain}: Zone found")
            else:
                print(f"⚠️  {domain}: Zone not found (may need to be added to Cloudflare)")

        print("\n🎉 Cloudflare setup complete!")
        print("\n🔬 Next steps:")
        print("   python scripts/cloudflare_dns_manager.py test")
        print("   python scripts/cloudflare_dns_manager.py list --domain markcheli.com")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("   Double-check your API token and email")
        sys.exit(1)

if __name__ == '__main__':
    main()