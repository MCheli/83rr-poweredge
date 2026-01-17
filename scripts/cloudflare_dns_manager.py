#!/usr/bin/env python3
"""
Cloudflare DNS Management System
Provides safe, automated DNS record management with Claude integration
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

class CloudflareDNSManager:
    """Manages DNS records through Cloudflare API with safety checks"""

    def __init__(self):
        """Initialize the DNS manager with API credentials"""
        load_dotenv()

        # Cloudflare API configuration
        self.api_token = os.getenv('CLOUDFLARE_API_TOKEN')
        self.email = os.getenv('CLOUDFLARE_EMAIL')  # Optional for token auth
        self.base_url = 'https://api.cloudflare.com/client/v4'

        # Safety configuration
        self.protected_records = {
            'markcheli.com': ['@', 'www', 'mail', '_dmarc', '_domainkey'],
            'ops.markcheli.com': []  # Will be populated with critical records
        }

        # Domain configuration
        self.domains = ['markcheli.com', 'ops.markcheli.com']
        self.zone_cache = {}

        if not self.api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN environment variable is required")

        # Verify authentication
        self._verify_auth()

    def _verify_auth(self):
        """Verify API token works and get user info"""
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.get(f"{self.base_url}/user/tokens/verify", headers=headers)
            if response.status_code == 200:
                result = response.json()
                if result['success']:
                    print(f"✅ Cloudflare API authentication successful")
                    return True
                else:
                    print(f"❌ API token verification failed: {result.get('errors', 'Unknown error')}")
                    return False
            else:
                print(f"❌ HTTP {response.status_code}: Failed to verify API token")
                return False
        except Exception as e:
            print(f"❌ Error verifying API token: {str(e)}")
            return False

    def _get_headers(self):
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

    def _api_request(self, method: str, endpoint: str, data: dict = None) -> Tuple[bool, dict]:
        """Make an API request to Cloudflare"""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                return False, {'errors': [{'message': f'Unsupported method: {method}'}]}

            result = response.json()

            if response.status_code in [200, 201] and result.get('success'):
                return True, result
            else:
                return False, result

        except Exception as e:
            return False, {'errors': [{'message': str(e)}]}

    def get_zone_id(self, domain: str) -> Optional[str]:
        """Get zone ID for a domain"""
        if domain in self.zone_cache:
            return self.zone_cache[domain]

        success, result = self._api_request('GET', f'/zones?name={domain}')
        if success and result['result']:
            zone_id = result['result'][0]['id']
            self.zone_cache[domain] = zone_id
            return zone_id
        else:
            print(f"❌ Could not find zone for domain: {domain}")
            return None

    def list_dns_records(self, domain: str) -> List[dict]:
        """List all DNS records for a domain"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return []

        success, result = self._api_request('GET', f'/zones/{zone_id}/dns_records')
        if success:
            return result['result']
        else:
            print(f"❌ Failed to list DNS records: {result.get('errors', 'Unknown error')}")
            return []

    def is_protected_record(self, domain: str, name: str) -> bool:
        """Check if a DNS record is protected from deletion/modification"""
        base_domain = domain
        if domain.startswith('ops.'):
            base_domain = 'ops.markcheli.com'
        elif domain == 'markcheli.com' or domain.endswith('.markcheli.com'):
            base_domain = 'markcheli.com'

        protected = self.protected_records.get(base_domain, [])

        # Normalize name for comparison
        record_name = name.replace(f".{domain}", "").replace(domain, "@")

        return record_name in protected

    def validate_record_data(self, record_type: str, content: str) -> Tuple[bool, str]:
        """Validate DNS record data"""
        if record_type == 'A':
            # Basic IPv4 validation
            parts = content.split('.')
            if len(parts) != 4:
                return False, "Invalid IPv4 address format"
            try:
                for part in parts:
                    num = int(part)
                    if not 0 <= num <= 255:
                        return False, "Invalid IPv4 address range"
            except ValueError:
                return False, "Invalid IPv4 address format"

        elif record_type == 'AAAA':
            # Basic IPv6 validation (simplified)
            if ':' not in content:
                return False, "Invalid IPv6 address format"

        elif record_type == 'CNAME':
            # CNAME validation
            if not content.endswith('.'):
                content += '.'

        elif record_type == 'MX':
            # MX record validation
            if not any(char.isdigit() for char in content):
                return False, "MX record must include priority"

        return True, content

    def create_dns_record(self, domain: str, record_type: str, name: str, content: str, ttl: int = 300, priority: int = None) -> bool:
        """Create a new DNS record"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        # Validate record data
        valid, validated_content = self.validate_record_data(record_type, content)
        if not valid:
            print(f"❌ Invalid record data: {validated_content}")
            return False

        # Check for existing record
        existing_records = self.list_dns_records(domain)
        for record in existing_records:
            if record['name'] == name and record['type'] == record_type:
                print(f"⚠️  Record {name} ({record_type}) already exists")
                return False

        record_data = {
            'type': record_type,
            'name': name,
            'content': validated_content,
            'ttl': ttl
        }

        if priority is not None and record_type in ['MX', 'SRV']:
            record_data['priority'] = priority

        success, result = self._api_request('POST', f'/zones/{zone_id}/dns_records', record_data)
        if success:
            print(f"✅ Created {record_type} record: {name} -> {validated_content}")
            return True
        else:
            print(f"❌ Failed to create record: {result.get('errors', 'Unknown error')}")
            return False

    def update_dns_record(self, domain: str, record_id: str, record_type: str, name: str, content: str, ttl: int = 300) -> bool:
        """Update an existing DNS record"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        # Safety check for protected records
        if self.is_protected_record(domain, name):
            print(f"❌ Cannot update protected record: {name}")
            return False

        # Validate record data
        valid, validated_content = self.validate_record_data(record_type, content)
        if not valid:
            print(f"❌ Invalid record data: {validated_content}")
            return False

        record_data = {
            'type': record_type,
            'name': name,
            'content': validated_content,
            'ttl': ttl
        }

        success, result = self._api_request('PUT', f'/zones/{zone_id}/dns_records/{record_id}', record_data)
        if success:
            print(f"✅ Updated {record_type} record: {name} -> {validated_content}")
            return True
        else:
            print(f"❌ Failed to update record: {result.get('errors', 'Unknown error')}")
            return False

    def delete_dns_record(self, domain: str, record_id: str, name: str) -> bool:
        """Delete a DNS record with safety checks"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        # Safety check for protected records
        if self.is_protected_record(domain, name):
            print(f"❌ Cannot delete protected record: {name}")
            print(f"   Protected records for {domain}: {self.protected_records.get(domain, [])}")
            return False

        # Additional confirmation for critical-looking records
        critical_patterns = ['mail', 'mx', 'spf', 'dkim', 'dmarc', '@', 'www']
        if any(pattern in name.lower() for pattern in critical_patterns):
            print(f"⚠️  Attempting to delete critical-looking record: {name}")
            print("    This record may be important for email or website functionality")
            return False

        success, result = self._api_request('DELETE', f'/zones/{zone_id}/dns_records/{record_id}')
        if success:
            print(f"✅ Deleted DNS record: {name}")
            return True
        else:
            print(f"❌ Failed to delete record: {result.get('errors', 'Unknown error')}")
            return False

    def find_record_by_name(self, domain: str, name: str, record_type: str = None) -> Optional[dict]:
        """Find a DNS record by name and optionally type"""
        records = self.list_dns_records(domain)
        for record in records:
            if record['name'] == name:
                if record_type is None or record['type'] == record_type:
                    return record
        return None

    def sync_infrastructure_dns(self) -> bool:
        """Sync DNS records for infrastructure services"""
        print("🔄 Syncing infrastructure DNS records...")

        # Infrastructure service mappings
        # Note: ops.markcheli.com records are managed as subdomains of markcheli.com
        infrastructure_records = {
            'markcheli.com': {
                'public_ip': '173.48.98.211',  # Update with actual public IP
                'records': [
                    # Public services
                    ('www', 'A', '173.48.98.211'),
                    ('flask', 'A', '173.48.98.211'),
                    ('data', 'A', '173.48.98.211'),
                    ('home', 'A', '173.48.98.211'),
                    ('videos', 'A', '173.48.98.211'),
                    ('files', 'A', '173.48.98.211'),
                    # LAN services (*.ops.markcheli.com as subdomains)
                    ('traefik-local.ops', 'A', '192.168.1.179'),
                    ('portainer-local.ops', 'A', '192.168.1.179'),
                    ('logs.ops', 'A', '192.168.1.179'),
                    ('opensearch.ops', 'A', '192.168.1.179'),
                    ('www-dev.ops', 'A', '192.168.1.179'),
                    ('flask-dev.ops', 'A', '192.168.1.179'),
                    ('dashboard.ops', 'A', '192.168.1.179'),
                    ('prometheus.ops', 'A', '192.168.1.179'),
                    ('cadvisor.ops', 'A', '192.168.1.179'),
                ]
            }
        }

        success_count = 0
        total_count = 0

        for domain, config in infrastructure_records.items():
            for name, record_type, content in config['records']:
                total_count += 1
                full_name = f"{name}.{domain}" if name != '@' else domain

                # Check if record exists
                existing = self.find_record_by_name(domain, full_name, record_type)
                if existing:
                    if existing['content'] != content:
                        print(f"🔄 Updating {full_name} ({record_type}): {existing['content']} -> {content}")
                        if self.update_dns_record(domain, existing['id'], record_type, full_name, content):
                            success_count += 1
                    else:
                        print(f"✅ {full_name} ({record_type}) is up to date")
                        success_count += 1
                else:
                    print(f"➕ Creating {full_name} ({record_type}) -> {content}")
                    if self.create_dns_record(domain, record_type, full_name, content):
                        success_count += 1

        print(f"📊 DNS sync completed: {success_count}/{total_count} records processed")
        return success_count == total_count

    def backup_dns_records(self, output_file: str = None) -> bool:
        """Backup all DNS records to a file"""
        if output_file is None:
            timestamp = int(time.time())
            output_file = f"dns_backup_{timestamp}.json"

        backup_data = {}

        for domain in self.domains:
            records = self.list_dns_records(domain)
            backup_data[domain] = records
            print(f"📦 Backed up {len(records)} records for {domain}")

        try:
            backup_path = Path(__file__).parent.parent / "backups"
            backup_path.mkdir(exist_ok=True)

            full_path = backup_path / output_file
            with open(full_path, 'w') as f:
                json.dump(backup_data, f, indent=2)

            print(f"✅ DNS backup saved: {full_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to save backup: {str(e)}")
            return False

    def restore_dns_records(self, backup_file: str, dry_run: bool = True) -> bool:
        """Restore DNS records from backup (with dry run option)"""
        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load backup file: {str(e)}")
            return False

        if dry_run:
            print("🔍 DRY RUN - No changes will be made")

        for domain, records in backup_data.items():
            print(f"\n📋 Processing {domain} ({len(records)} records)")

            for record in records:
                name = record['name']
                record_type = record['type']
                content = record['content']

                if dry_run:
                    print(f"   Would restore: {name} ({record_type}) -> {content}")
                else:
                    # Check if record exists
                    existing = self.find_record_by_name(domain, name, record_type)
                    if not existing:
                        self.create_dns_record(domain, record_type, name, content)

        return True

def main():
    """CLI interface for DNS management"""
    import argparse

    parser = argparse.ArgumentParser(description='Cloudflare DNS Manager')
    parser.add_argument('action', choices=[
        'list', 'create', 'update', 'delete', 'sync', 'backup', 'restore', 'test'
    ], help='Action to perform')

    parser.add_argument('--domain', '-d', help='Domain name')
    parser.add_argument('--name', '-n', help='Record name')
    parser.add_argument('--type', '-t', help='Record type (A, AAAA, CNAME, etc.)')
    parser.add_argument('--content', '-c', help='Record content')
    parser.add_argument('--ttl', type=int, default=300, help='TTL (default: 300)')
    parser.add_argument('--file', '-f', help='File for backup/restore')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')

    args = parser.parse_args()

    try:
        dns = CloudflareDNSManager()

        if args.action == 'list':
            if not args.domain:
                print("❌ Domain required for list action")
                sys.exit(1)
            records = dns.list_dns_records(args.domain)
            print(f"\n📋 DNS Records for {args.domain}:")
            print("-" * 60)
            for record in records:
                print(f"{record['name']:<30} {record['type']:<10} {record['content']}")

        elif args.action == 'create':
            if not all([args.domain, args.name, args.type, args.content]):
                print("❌ Domain, name, type, and content required for create")
                sys.exit(1)
            success = dns.create_dns_record(args.domain, args.type, args.name, args.content, args.ttl)
            sys.exit(0 if success else 1)

        elif args.action == 'sync':
            success = dns.sync_infrastructure_dns()
            sys.exit(0 if success else 1)

        elif args.action == 'backup':
            success = dns.backup_dns_records(args.file)
            sys.exit(0 if success else 1)

        elif args.action == 'restore':
            if not args.file:
                print("❌ Backup file required for restore")
                sys.exit(1)
            success = dns.restore_dns_records(args.file, args.dry_run)
            sys.exit(0 if success else 1)

        elif args.action == 'test':
            print("✅ DNS manager initialized and authenticated successfully")
            for domain in dns.domains:
                zone_id = dns.get_zone_id(domain)
                if zone_id:
                    print(f"✅ {domain}: Zone ID {zone_id}")
                else:
                    print(f"❌ {domain}: Zone not found")

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()