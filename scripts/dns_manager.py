#!/usr/bin/env python3
"""
DNS Management Helper for Squarespace Domains
Since Squarespace doesn't offer a public DNS API, this script provides:
1. DNS record templates and instructions
2. Automated DNS testing and validation
3. Step-by-step guidance for manual DNS configuration
"""
import os
import json
import subprocess
import requests
from datetime import datetime
from pathlib import Path
import time

class SquarespaceDNSManager:
    def __init__(self):
        self.domain = "ops.markcheli.com"
        self.public_ip = "173.48.98.211"  # Your server's public IP
        self.local_ip = "192.168.1.179"   # Your server's local IP

        # Define current DNS records based on investigation
        self.existing_records = {
            "ops.markcheli.com": self.public_ip,
            "jupyter.markcheli.com": self.public_ip,
            "traefik-local.ops.markcheli.com": self.local_ip,
            "portainer-local.ops.markcheli.com": self.local_ip
        }

    def check_dns_record(self, subdomain, expected_ip=None):
        """Check if a DNS record exists and return the result"""
        fqdn = f"{subdomain}.{self.domain}" if subdomain else self.domain

        try:
            result = subprocess.run(
                ["dig", fqdn, "A", "+short"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                current_ip = result.stdout.strip()
                if current_ip:
                    status = "✅" if (not expected_ip or current_ip == expected_ip) else "⚠️"
                    return {
                        "fqdn": fqdn,
                        "exists": True,
                        "current_ip": current_ip,
                        "expected_ip": expected_ip,
                        "status": status,
                        "matches": not expected_ip or current_ip == expected_ip
                    }
                else:
                    return {
                        "fqdn": fqdn,
                        "exists": False,
                        "current_ip": None,
                        "expected_ip": expected_ip,
                        "status": "❌",
                        "matches": False
                    }
            else:
                return {
                    "fqdn": fqdn,
                    "exists": False,
                    "current_ip": None,
                    "expected_ip": expected_ip,
                    "status": "❌",
                    "matches": False
                }
        except Exception as e:
            return {
                "fqdn": fqdn,
                "exists": False,
                "error": str(e),
                "status": "❌",
                "matches": False
            }

    def generate_dns_instructions(self, subdomain, target_ip=None, record_type="A"):
        """Generate manual DNS configuration instructions"""
        if not target_ip:
            target_ip = self.public_ip

        fqdn = f"{subdomain}.{self.domain}"

        instructions = f"""
🔧 Manual DNS Configuration Required for {fqdn}

Since Squarespace doesn't offer a DNS API, please add this record manually:

📋 DNS Record Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Record Type: {record_type}
Name:        {subdomain}
Target/Value: {target_ip}
TTL:         3600 (or use default)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 Steps to Add Record in Squarespace:
1. Log in to your Squarespace account
2. Go to Settings → Domains
3. Click on "{self.domain}"
4. Click "DNS" in the left sidebar
5. Scroll to "Custom Records" section
6. Click "Add Record"
7. Select "{record_type} Record"
8. Enter:
   - Host: {subdomain}
   - Points to: {target_ip}
   - TTL: 3600
9. Click "Add Record"
10. Wait 5-15 minutes for propagation

🔍 Verification Command:
dig {fqdn} A +short

Expected result: {target_ip}
        """
        return instructions.strip()

    def audit_current_dns(self):
        """Audit all current DNS records"""
        print("🔍 DNS Audit Report")
        print("=" * 60)

        # Check existing known records
        for fqdn, expected_ip in self.existing_records.items():
            if "." in fqdn and fqdn.endswith(self.domain):
                subdomain = fqdn.replace(f".{self.domain}", "")
            else:
                subdomain = ""

            result = self.check_dns_record(subdomain, expected_ip)
            print(f"{result['status']} {result['fqdn']} → {result.get('current_ip', 'NOT FOUND')}")

        print("\n" + "=" * 60)

        return True

    def request_new_record(self, subdomain, target_ip=None, record_type="A"):
        """Request a new DNS record with instructions"""
        if not target_ip:
            target_ip = self.public_ip

        print(f"📋 DNS Record Request: {subdomain}.{self.domain}")
        print("=" * 60)

        # Check if record already exists
        current = self.check_dns_record(subdomain)
        if current["exists"]:
            if current["current_ip"] == target_ip:
                print(f"✅ Record already exists with correct value: {target_ip}")
                return True
            else:
                print(f"⚠️  Record exists but points to: {current['current_ip']}")
                print(f"   Expected: {target_ip}")
                print("\n🔄 Update Required")
        else:
            print("❌ Record does not exist")
            print("\n➕ Addition Required")

        # Generate instructions
        instructions = self.generate_dns_instructions(subdomain, target_ip, record_type)
        print(instructions)

        return False

    def wait_for_propagation(self, subdomain, expected_ip, max_wait=900):
        """Wait for DNS propagation with progress updates"""
        fqdn = f"{subdomain}.{self.domain}"
        print(f"⏳ Waiting for DNS propagation of {fqdn} → {expected_ip}")
        print("   This may take 5-15 minutes...")

        start_time = time.time()
        check_interval = 30  # Check every 30 seconds

        while time.time() - start_time < max_wait:
            result = self.check_dns_record(subdomain, expected_ip)

            if result["matches"]:
                elapsed = int(time.time() - start_time)
                print(f"✅ DNS propagated successfully after {elapsed} seconds!")
                return True

            elapsed = int(time.time() - start_time)
            remaining = int(max_wait - elapsed)
            print(f"   ⏱  Still waiting... ({elapsed}s elapsed, {remaining}s remaining)")

            time.sleep(check_interval)

        print("⚠️  Timeout waiting for DNS propagation")
        print("   The record may still be propagating. Please try testing manually.")
        return False

    def test_service_connectivity(self, subdomain, port=443, protocol="https"):
        """Test if service is accessible after DNS propagation"""
        fqdn = f"{subdomain}.{self.domain}"

        print(f"🌐 Testing service connectivity: {protocol}://{fqdn}")

        try:
            url = f"{protocol}://{fqdn}"
            response = requests.get(url, timeout=10, verify=False)

            if response.status_code == 200:
                print(f"✅ Service accessible: {response.status_code}")
                return True
            else:
                print(f"⚠️  Service returned: {response.status_code}")
                return False

        except requests.exceptions.SSLError:
            print("⚠️  SSL certificate issue (may be normal for new domains)")
            # Try HTTP as fallback
            try:
                http_url = f"http://{fqdn}"
                response = requests.get(http_url, timeout=10)
                if response.status_code in [200, 301, 302]:
                    print("✅ HTTP connection works (redirects to HTTPS)")
                    return True
            except:
                pass

        except requests.exceptions.ConnectionError:
            print("❌ Connection failed")

        except Exception as e:
            print(f"❌ Error: {e}")

        return False

def main():
    import sys

    dns = SquarespaceDNSManager()

    if len(sys.argv) < 2:
        print("DNS Management Helper for Squarespace Domains")
        print("=" * 50)
        print("Usage:")
        print("  python dns_manager.py audit                    # Audit current DNS")
        print("  python dns_manager.py add <subdomain>          # Request new A record")
        print("  python dns_manager.py add <subdomain> <ip>     # Request specific A record")
        print("  python dns_manager.py check <subdomain>        # Check specific record")
        print("  python dns_manager.py wait <subdomain> <ip>    # Wait for propagation")
        print("  python dns_manager.py test <subdomain>         # Test service")
        print()
        print("Examples:")
        print("  python dns_manager.py add jupyter              # Add jupyter.markcheli.com")
        print("  python dns_manager.py check jupyter            # Check jupyter.markcheli.com")
        print("  python dns_manager.py test jupyter             # Test jupyter service")
        return

    command = sys.argv[1].lower()

    if command == "audit":
        dns.audit_current_dns()

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python dns_manager.py add <subdomain> [ip]")
            return
        subdomain = sys.argv[2]
        target_ip = sys.argv[3] if len(sys.argv) > 3 else None
        dns.request_new_record(subdomain, target_ip)

    elif command == "check":
        if len(sys.argv) < 3:
            print("Usage: python dns_manager.py check <subdomain>")
            return
        subdomain = sys.argv[2]
        result = dns.check_dns_record(subdomain, dns.public_ip)
        print(f"{result['status']} {result['fqdn']} → {result.get('current_ip', 'NOT FOUND')}")

    elif command == "wait":
        if len(sys.argv) < 4:
            print("Usage: python dns_manager.py wait <subdomain> <expected_ip>")
            return
        subdomain = sys.argv[2]
        expected_ip = sys.argv[3]
        dns.wait_for_propagation(subdomain, expected_ip)

    elif command == "test":
        if len(sys.argv) < 3:
            print("Usage: python dns_manager.py test <subdomain>")
            return
        subdomain = sys.argv[2]
        dns.test_service_connectivity(subdomain)

    else:
        print(f"Unknown command: {command}")
        print("Run without arguments to see usage help.")

if __name__ == "__main__":
    main()