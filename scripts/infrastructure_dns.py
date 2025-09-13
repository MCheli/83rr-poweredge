#!/usr/bin/env python3
"""
Infrastructure-specific DNS management for homelab services
Manages DNS requirements for all infrastructure services
"""
import os
import sys
from dotenv import load_dotenv
from dns_manager import SquarespaceDNSManager

class InfrastructureDNS:
    def __init__(self):
        load_dotenv()
        self.dns = SquarespaceDNSManager()

        # Service to subdomain mapping
        self.services = {
            # Public services (accessible from internet)
            'public': {
                'jupyter': {
                    'subdomain': 'jupyter',
                    'ip': self.dns.public_ip,
                    'description': 'JupyterHub data science environment'
                },
                'hello': {
                    'subdomain': 'hello',
                    'ip': self.dns.public_ip,
                    'description': 'Hello world test container'
                },
                'whoami': {
                    'subdomain': '',  # Base domain ops.markcheli.com
                    'ip': self.dns.public_ip,
                    'description': 'Whoami test service at base domain'
                }
            },
            # Local services (internal network only)
            'local': {
                'traefik-dashboard': {
                    'subdomain': 'traefik-local',
                    'ip': self.dns.local_ip,
                    'description': 'Traefik dashboard (LAN only)'
                },
                'portainer': {
                    'subdomain': 'portainer-local',
                    'ip': self.dns.local_ip,
                    'description': 'Portainer container management (LAN only)'
                },
                'grafana': {
                    'subdomain': 'grafana',
                    'ip': self.dns.local_ip,  # Could be public, currently local
                    'description': 'Grafana logging dashboard'
                }
            }
        }

    def audit_all_services(self):
        """Audit DNS records for all infrastructure services"""
        print("🏗️  Infrastructure DNS Audit")
        print("=" * 60)

        missing_records = []

        for category, services in self.services.items():
            print(f"\n📋 {category.upper()} Services:")
            print("-" * 40)

            for service_name, config in services.items():
                subdomain = config['subdomain']
                expected_ip = config['ip']
                description = config['description']

                result = self.dns.check_dns_record(subdomain, expected_ip)

                service_fqdn = result['fqdn']
                status = result['status']
                current_ip = result.get('current_ip', 'NOT FOUND')

                print(f"{status} {service_fqdn}")
                print(f"   {description}")
                print(f"   Expected: {expected_ip} | Current: {current_ip}")

                if not result['matches']:
                    missing_records.append({
                        'service': service_name,
                        'subdomain': subdomain,
                        'expected_ip': expected_ip,
                        'description': description,
                        'category': category
                    })

                print()

        print("=" * 60)

        if missing_records:
            print(f"⚠️  Found {len(missing_records)} DNS records that need attention:")
            for record in missing_records:
                print(f"   • {record['service']}: {record['subdomain'] or 'root'}.{self.dns.domain}")
        else:
            print("✅ All infrastructure DNS records are configured correctly!")

        return missing_records

    def setup_service_dns(self, service_name):
        """Setup DNS for a specific service"""
        # Find service in both categories
        service_config = None
        category = None

        for cat, services in self.services.items():
            if service_name in services:
                service_config = services[service_name]
                category = cat
                break

        if not service_config:
            print(f"❌ Unknown service: {service_name}")
            print("Available services:")
            for cat, services in self.services.items():
                for svc in services:
                    print(f"  • {svc} ({cat})")
            return False

        print(f"🔧 Setting up DNS for {service_name} ({category} service)")
        print(f"📄 {service_config['description']}")
        print()

        return self.dns.request_new_record(
            service_config['subdomain'],
            service_config['ip']
        )

    def verify_deployment(self, service_name):
        """Verify DNS and connectivity for a deployed service"""
        service_config = None

        for cat, services in self.services.items():
            if service_name in services:
                service_config = services[service_name]
                break

        if not service_config:
            print(f"❌ Unknown service: {service_name}")
            return False

        subdomain = service_config['subdomain']
        expected_ip = service_config['ip']

        print(f"🔍 Verifying deployment: {service_name}")
        print("=" * 40)

        # Check DNS
        result = self.dns.check_dns_record(subdomain, expected_ip)
        print(f"DNS: {result['status']} {result['fqdn']} → {result.get('current_ip', 'NOT FOUND')}")

        if result['matches']:
            # Test connectivity
            if service_config['ip'] == self.dns.public_ip:
                success = self.dns.test_service_connectivity(subdomain)
                return success
            else:
                print("ℹ️  Local service - connectivity test skipped")
                return True
        else:
            print("❌ DNS verification failed")
            return False

    def generate_deployment_checklist(self, service_name):
        """Generate deployment checklist for a service"""
        service_config = None
        category = None

        for cat, services in self.services.items():
            if service_name in services:
                service_config = services[service_name]
                category = cat
                break

        if not service_config:
            print(f"❌ Unknown service: {service_name}")
            return

        subdomain = service_config['subdomain']
        ip = service_config['ip']
        description = service_config['description']
        fqdn = f"{subdomain}.{self.dns.domain}" if subdomain else self.dns.domain

        checklist = f"""
📋 Deployment Checklist: {service_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Service: {description}
FQDN: {fqdn}
Category: {category.upper()}
Target IP: {ip}

🔲 Prerequisites:
   □ Container/service deployed and running
   □ Traefik routing configured (if applicable)
   □ Firewall rules configured for ports 80/443

🔲 DNS Configuration:
   □ Add DNS A record: {subdomain or '@'} → {ip}
   □ Wait 5-15 minutes for DNS propagation
   □ Verify: dig {fqdn} A +short

🔲 SSL/TLS (for public services):
   □ Let's Encrypt certificate auto-requested by Traefik
   □ HTTPS redirect configured
   □ Security headers applied

🔲 Testing:
   □ DNS resolves correctly
   □ Service responds on HTTPS (public) or HTTP (local)
   □ Expected content/functionality works

🔲 Monitoring:
   □ Add to health check scripts
   □ Update documentation
   □ Commit changes to git

🔧 Quick Commands:
   # Check DNS
   python scripts/dns_manager.py check {subdomain}

   # Test service
   python scripts/dns_manager.py test {subdomain}

   # Full verification
   python scripts/infrastructure_dns.py verify {service_name}
        """

        print(checklist.strip())

def main():
    if len(sys.argv) < 2:
        print("Infrastructure DNS Management")
        print("=" * 40)
        print("Usage:")
        print("  python infrastructure_dns.py audit                    # Audit all services")
        print("  python infrastructure_dns.py setup <service>         # Setup DNS for service")
        print("  python infrastructure_dns.py verify <service>        # Verify deployment")
        print("  python infrastructure_dns.py checklist <service>     # Generate checklist")
        print()
        print("Available services:")
        infra = InfrastructureDNS()
        for category, services in infra.services.items():
            print(f"  {category.upper()}:")
            for service_name, config in services.items():
                print(f"    • {service_name}: {config['description']}")
        return

    command = sys.argv[1].lower()
    infra = InfrastructureDNS()

    if command == "audit":
        infra.audit_all_services()

    elif command == "setup":
        if len(sys.argv) < 3:
            print("Usage: python infrastructure_dns.py setup <service>")
            return
        service = sys.argv[2]
        infra.setup_service_dns(service)

    elif command == "verify":
        if len(sys.argv) < 3:
            print("Usage: python infrastructure_dns.py verify <service>")
            return
        service = sys.argv[2]
        infra.verify_deployment(service)

    elif command == "checklist":
        if len(sys.argv) < 3:
            print("Usage: python infrastructure_dns.py checklist <service>")
            return
        service = sys.argv[2]
        infra.generate_deployment_checklist(service)

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()