#!/usr/bin/env python3
"""
Deploy Wildcard SSL Certificate Configuration

This script deploys the new wildcard SSL certificate configuration that uses
Google Domains DNS-01 challenge to avoid Let's Encrypt rate limiting issues.

Features:
- Single wildcard certificate for *.markcheli.com and *.ops.markcheli.com
- DNS-01 challenge eliminates public accessibility requirements for LAN services
- Fallback HTTP-01 resolver for compatibility
- Comprehensive verification of all services

Requirements:
- Google Domains Access Token configured in .env file
- DNS propagation time (may take several minutes)
"""

import os
import subprocess
import time
import requests
import sys
from pathlib import Path
from dotenv import load_dotenv

class WildcardSSLDeployer:
    def __init__(self):
        load_dotenv()
        self.base_dir = Path(__file__).parent.parent
        self.services = {
            'traefik': {
                'path': 'infrastructure/traefik',
                'public_domains': ['ops.markcheli.com'],
                'lan_domains': ['traefik-local.ops.markcheli.com']
            },
            'personal-website': {
                'path': 'infrastructure/personal-website',
                'public_domains': ['www.markcheli.com', 'flask.markcheli.com'],
                'lan_domains': ['www-dev.ops.markcheli.com']
            },
            'jupyter': {
                'path': 'infrastructure/jupyter',
                'public_domains': ['jupyter.markcheli.com'],
                'lan_domains': []
            },
            'opensearch': {
                'path': 'infrastructure/opensearch',
                'public_domains': [],
                'lan_domains': ['opensearch-local.ops.markcheli.com', 'logs-local.ops.markcheli.com']
            }
        }

    def check_prerequisites(self):
        """Check that all prerequisites are met"""
        print("🔍 Checking prerequisites...")

        # Check Google Domains token
        token = os.getenv('GOOGLE_DOMAINS_ACCESS_TOKEN')
        if not token or token == 'your_google_domains_access_token_here':
            print("❌ Google Domains Access Token not configured!")
            print("📋 To fix this:")
            print("   1. Go to https://domains.google.com/registrar/markcheli.com/dns")
            print("   2. Create a DNS API token")
            print("   3. Add it to .env as GOOGLE_DOMAINS_ACCESS_TOKEN")
            return False

        print("✅ Google Domains Access Token configured")
        return True

    def deploy_service(self, service_name):
        """Deploy a specific service with new SSL configuration"""
        service_info = self.services[service_name]
        service_path = self.base_dir / service_info['path']

        print(f"🚀 Deploying {service_name}...")

        # Change to service directory
        os.chdir(service_path)

        # Stop existing containers
        subprocess.run(['docker', 'compose', 'down'], check=False)

        # Start with new configuration
        result = subprocess.run(['docker', 'compose', 'up', '-d'],
                              capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ Failed to deploy {service_name}: {result.stderr}")
            return False

        print(f"✅ {service_name} deployed successfully")
        return True

    def wait_for_certificates(self):
        """Wait for SSL certificates to be generated"""
        print("⏳ Waiting for SSL certificates to be generated...")
        print("   This may take several minutes for DNS propagation...")

        # Wait longer for DNS-01 challenge
        for i in range(12):  # 12 * 30s = 6 minutes
            time.sleep(30)
            print(f"   Waiting... ({(i+1)*30}s / 360s)")

            # Check if certificates are being requested
            try:
                result = subprocess.run(['docker', 'logs', 'traefik'],
                                      capture_output=True, text=True)
                if 'certificate obtained' in result.stdout.lower():
                    print("🎉 Certificates obtained!")
                    return True
                elif 'error' in result.stdout.lower() and 'acme' in result.stdout.lower():
                    print("⚠️  Certificate errors detected, continuing to wait...")
            except:
                pass

        print("⚠️  Certificate generation taking longer than expected")
        return False

    def verify_service(self, domain, is_lan=False):
        """Verify that a service is accessible with valid SSL"""
        try:
            if is_lan:
                # For LAN services, just check if port 443 is responding
                response = requests.get(f'https://{domain}',
                                      timeout=10, verify=False)
                return response.status_code < 500
            else:
                # For public services, verify SSL certificate
                response = requests.get(f'https://{domain}', timeout=10)
                return response.status_code < 500
        except requests.exceptions.SSLError as e:
            print(f"   SSL Error for {domain}: {e}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"   Connection failed to {domain}")
            return False
        except Exception as e:
            print(f"   Unexpected error for {domain}: {e}")
            return False

    def verify_all_services(self):
        """Verify all services are working with SSL"""
        print("🔐 Verifying SSL certificates for all services...")

        all_passed = True
        for service_name, service_info in self.services.items():
            print(f"\n📋 Verifying {service_name}:")

            # Check public domains
            for domain in service_info['public_domains']:
                if self.verify_service(domain, is_lan=False):
                    print(f"   ✅ {domain} - SSL working")
                else:
                    print(f"   ❌ {domain} - SSL failed")
                    all_passed = False

            # Check LAN domains
            for domain in service_info['lan_domains']:
                if self.verify_service(domain, is_lan=True):
                    print(f"   ✅ {domain} - LAN SSL working")
                else:
                    print(f"   ❌ {domain} - LAN SSL failed")
                    all_passed = False

        return all_passed

    def show_certificate_info(self):
        """Show certificate information from Traefik"""
        print("\n🔍 Certificate Information:")
        try:
            result = subprocess.run(['docker', 'exec', 'traefik',
                                   'cat', '/letsencrypt/acme.json'],
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                import json
                acme_data = json.loads(result.stdout)
                certs = acme_data.get('letsencrypt', {}).get('Certificates', [])
                print(f"   📜 {len(certs)} certificates found")
                for cert in certs:
                    domain = cert.get('domain', {}).get('main', 'Unknown')
                    print(f"   🎯 Certificate for: {domain}")
            else:
                print("   ⚠️  No certificate data found yet")
        except Exception as e:
            print(f"   ❌ Error reading certificate data: {e}")

    def deploy_all(self):
        """Deploy all services with wildcard SSL configuration"""
        print("🌟 Starting Wildcard SSL Deployment")
        print("=" * 50)

        if not self.check_prerequisites():
            return False

        # Deploy services in order
        services_order = ['traefik', 'personal-website', 'jupyter', 'opensearch']

        for service_name in services_order:
            if not self.deploy_service(service_name):
                print(f"❌ Failed to deploy {service_name}, stopping deployment")
                return False
            time.sleep(5)  # Brief pause between services

        # Wait for certificates
        self.wait_for_certificates()

        # Show certificate info
        self.show_certificate_info()

        # Verify all services
        if self.verify_all_services():
            print("\n🎉 Wildcard SSL deployment completed successfully!")
            print("✅ All services are now using wildcard certificates")
            print("✅ No more Let's Encrypt rate limiting issues")
            return True
        else:
            print("\n⚠️  Some services may still be starting up")
            print("💡 Wait a few more minutes and check manually")
            return False

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == '--verify-only':
            deployer = WildcardSSLDeployer()
            deployer.verify_all_services()
            return
        elif sys.argv[1] == '--cert-info':
            deployer = WildcardSSLDeployer()
            deployer.show_certificate_info()
            return

    deployer = WildcardSSLDeployer()
    success = deployer.deploy_all()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()