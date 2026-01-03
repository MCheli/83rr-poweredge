#!/usr/bin/env python3
"""
Cloudflare SSL Certificate Management
Manages Cloudflare Origin Certificates for secure server connections
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

class CloudflareSSLManager:
    """Manages Cloudflare Origin Certificates"""

    def __init__(self):
        """Initialize SSL manager with API credentials"""
        load_dotenv()

        self.api_token = os.getenv('CLOUDFLARE_API_TOKEN')
        self.base_url = 'https://api.cloudflare.com/client/v4'

        if not self.api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN environment variable is required")

        # Certificate paths
        self.project_root = Path(__file__).parent.parent
        self.cert_dir = self.project_root / "infrastructure/nginx/certs"
        self.cert_dir.mkdir(parents=True, exist_ok=True)

        # Verify authentication
        self._verify_auth()

    def _verify_auth(self):
        """Verify API token works"""
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
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data)
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
        success, result = self._api_request('GET', f'/zones?name={domain}')
        if success and result['result']:
            zone_id = result['result'][0]['id']
            return zone_id
        else:
            print(f"❌ Could not find zone for domain: {domain}")
            return None

    def list_origin_certificates(self, zone_id: str = None) -> List[dict]:
        """List existing Origin Certificates"""
        print("🔍 Listing Origin Certificates...")

        # Get zone ID for markcheli.com if not provided
        if not zone_id:
            zone_id = self.get_zone_id('markcheli.com')
            if not zone_id:
                return []

        # Try the global origin certificates endpoint
        success, result = self._api_request('GET', f'/certificates?zone_id={zone_id}')
        if success:
            certificates = result['result']
            print(f"📋 Found {len(certificates)} Origin Certificates:")

            for cert in certificates:
                print(f"   🔒 {cert.get('id', 'N/A')[:8]}... - {', '.join(cert.get('hostnames', []))}")
                print(f"      Status: {cert.get('status', 'Unknown')}")
                print(f"      Expires: {cert.get('expires_on', 'Unknown')}")
                print()

            return certificates
        else:
            print(f"❌ Failed to list certificates: {result.get('errors', 'Unknown error')}")
            return []

    def create_origin_certificate(self, hostnames: List[str], validity_days: int = 5475) -> Optional[dict]:
        """Create a new Origin Certificate"""
        print(f"🔐 Creating Origin Certificate for: {', '.join(hostnames)}")

        # Get zone ID for the first hostname's domain
        domain = hostnames[0].replace('*.', '')  # Remove wildcard
        if '.' in domain:
            # For subdomains like ops.markcheli.com, get markcheli.com
            domain_parts = domain.split('.')
            if len(domain_parts) >= 2:
                domain = '.'.join(domain_parts[-2:])  # Get last two parts (domain.tld)

        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return None

        # Generate CSR and private key
        print(f"🔑 Generating CSR and private key...")
        csr_pem, private_key_pem = self._generate_csr_and_key(hostnames)

        cert_data = {
            'hostnames': hostnames,
            'requested_validity': validity_days,  # 15 years (max)
            'request_type': 'origin-rsa',
            'csr': csr_pem
        }

        # Use correct Origin Certificate API endpoint
        success, result = self._api_request('POST', f'/certificates', cert_data)
        if success:
            certificate = result['result']
            print(f"✅ Origin Certificate created successfully")
            print(f"   🆔 Certificate ID: {certificate.get('id')}")
            print(f"   🌐 Hostnames: {', '.join(certificate.get('hostnames', []))}")
            print(f"   📅 Valid until: {certificate.get('expires_on')}")

            # Store the private key with the certificate data for download
            certificate['_private_key'] = private_key_pem
            return certificate
        else:
            print(f"❌ Failed to create certificate: {result.get('errors', 'Unknown error')}")
            return None

    def download_certificate(self, certificate_id: str, cert_name: str, zone_id: str = None, private_key_pem: str = None) -> bool:
        """Download an Origin Certificate"""
        print(f"📥 Downloading certificate: {certificate_id}")

        # Get zone ID if not provided
        if not zone_id:
            zone_id = self.get_zone_id('markcheli.com')
            if not zone_id:
                return False

        success, result = self._api_request('GET', f'/certificates/{certificate_id}')
        if not success:
            print(f"❌ Failed to fetch certificate: {result.get('errors', 'Unknown error')}")
            return False

        certificate = result['result']

        # Get certificate and private key
        cert_pem = certificate.get('certificate')

        # Use provided private key or try to get from API response
        if private_key_pem:
            private_key = private_key_pem
        else:
            private_key = certificate.get('private_key')

        if not cert_pem or not private_key:
            print("❌ Certificate data incomplete")
            return False

        # Save certificate files
        cert_file = self.cert_dir / f"{cert_name}.crt"
        key_file = self.cert_dir / f"{cert_name}.key"
        fullchain_file = self.cert_dir / "fullchain.pem"
        privkey_file = self.cert_dir / "privkey.pem"

        try:
            # Write certificate
            with open(cert_file, 'w') as f:
                f.write(cert_pem)
            print(f"✅ Certificate saved: {cert_file}")

            # Write private key
            with open(key_file, 'w') as f:
                f.write(private_key)
            print(f"✅ Private key saved: {key_file}")

            # Create NGINX-compatible filenames
            with open(fullchain_file, 'w') as f:
                f.write(cert_pem)
            print(f"✅ Fullchain saved: {fullchain_file}")

            with open(privkey_file, 'w') as f:
                f.write(private_key)
            print(f"✅ Private key saved: {privkey_file}")

            # Set secure permissions
            os.chmod(cert_file, 0o644)
            os.chmod(key_file, 0o600)
            os.chmod(fullchain_file, 0o644)
            os.chmod(privkey_file, 0o600)

            print("🔒 Set secure file permissions")
            return True

        except Exception as e:
            print(f"❌ Failed to save certificate files: {str(e)}")
            return False

    def create_wildcard_certificates(self) -> bool:
        """Create wildcard certificates for both domains"""
        print("🌟 Creating wildcard certificates for infrastructure...")

        # Certificate configurations
        # Note: Both certificates are for the markcheli.com zone
        certificates_to_create = [
            {
                'name': 'wildcard-markcheli',
                'hostnames': ['*.markcheli.com', 'markcheli.com'],
                'description': 'Public services wildcard certificate'
            },
            {
                'name': 'wildcard-ops-markcheli',
                'hostnames': ['*.ops.markcheli.com'],
                'description': 'LAN services wildcard certificate (subdomain of markcheli.com)'
            }
        ]

        created_certificates = []

        for cert_config in certificates_to_create:
            print(f"\n🔐 Creating {cert_config['description']}...")

            certificate = self.create_origin_certificate(cert_config['hostnames'])
            if certificate:
                cert_id = certificate['id']
                cert_name = cert_config['name']
                private_key = certificate.get('_private_key')

                if self.download_certificate(cert_id, cert_name, private_key_pem=private_key):
                    created_certificates.append({
                        'id': cert_id,
                        'name': cert_name,
                        'hostnames': cert_config['hostnames']
                    })
                else:
                    print(f"❌ Failed to download {cert_name}")
                    return False
            else:
                print(f"❌ Failed to create {cert_config['name']}")
                return False

        # Create certificate info file
        self._save_certificate_info(created_certificates)

        print(f"\n🎉 Successfully created {len(created_certificates)} wildcard certificates!")
        return True

    def _save_certificate_info(self, certificates: List[dict]):
        """Save certificate information for reference"""
        cert_info_file = self.cert_dir / "certificate_info.json"

        cert_info = {
            'created_at': self._get_current_time(),
            'certificates': certificates,
            'file_mapping': {
                'public_cert': 'wildcard-markcheli.crt',
                'public_key': 'wildcard-markcheli.key',
                'lan_cert': 'wildcard-ops-markcheli.crt',
                'lan_key': 'wildcard-ops-markcheli.key',
                'nginx_fullchain': 'fullchain.pem',
                'nginx_privkey': 'privkey.pem'
            }
        }

        with open(cert_info_file, 'w') as f:
            json.dump(cert_info, f, indent=2)

        print(f"📋 Certificate info saved: {cert_info_file}")

    def _get_current_time(self):
        """Get current time in ISO format"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'

    def _generate_csr_and_key(self, hostnames: List[str]) -> Tuple[str, str]:
        """Generate CSR and private key for the certificate"""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create certificate subject
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Personal Infrastructure"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0]),
        ])

        # Create SAN extension for multiple hostnames
        san_list = []
        for hostname in hostnames:
            if hostname.startswith('*.'):
                # Wildcard domain
                san_list.append(x509.DNSName(hostname))
            else:
                san_list.append(x509.DNSName(hostname))

        # Generate CSR
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            subject
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        # Serialize to PEM format
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        return csr_pem, private_key_pem

    def validate_certificates(self) -> bool:
        """Validate that certificates exist and are readable"""
        print("🔍 Validating certificate files...")

        required_files = [
            'wildcard-markcheli.crt',
            'wildcard-markcheli.key',
            'wildcard-ops-markcheli.crt',
            'wildcard-ops-markcheli.key',
            'fullchain.pem',
            'privkey.pem'
        ]

        all_valid = True

        for filename in required_files:
            file_path = self.cert_dir / filename

            if not file_path.exists():
                print(f"❌ Missing: {filename}")
                all_valid = False
                continue

            # Check file size
            file_size = file_path.stat().st_size
            if file_size == 0:
                print(f"❌ Empty file: {filename}")
                all_valid = False
                continue

            # Check permissions
            file_mode = oct(file_path.stat().st_mode)[-3:]
            expected_mode = '600' if filename.endswith('.key') or filename == 'privkey.pem' else '644'

            if file_mode != expected_mode:
                print(f"⚠️  {filename}: Permissions {file_mode} (expected {expected_mode})")
                # Fix permissions
                os.chmod(file_path, int(expected_mode, 8))
                print(f"🔧 Fixed permissions for {filename}")

            print(f"✅ {filename}: {file_size} bytes, mode {file_mode}")

        if all_valid:
            print("🎉 All certificate files are valid!")
        else:
            print("❌ Certificate validation failed")

        return all_valid

    def revoke_certificate(self, certificate_id: str) -> bool:
        """Revoke an Origin Certificate"""
        print(f"🗑️ Revoking certificate: {certificate_id}")

        success, result = self._api_request('DELETE', f'/certificates/{certificate_id}')
        if success:
            print(f"✅ Certificate revoked successfully")
            return True
        else:
            print(f"❌ Failed to revoke certificate: {result.get('errors', 'Unknown error')}")
            return False

    def get_ssl_mode(self, zone_id: str = None) -> str:
        """Get current SSL mode for the zone"""
        if not zone_id:
            zone_id = self.get_zone_id('markcheli.com')
            if not zone_id:
                return None

        success, result = self._api_request('GET', f'/zones/{zone_id}/settings/ssl')
        if success:
            ssl_mode = result['result']['value']
            return ssl_mode
        else:
            print(f"❌ Failed to get SSL mode: {result.get('errors', 'Unknown error')}")
            return None

    def set_ssl_mode(self, mode: str, zone_id: str = None) -> bool:
        """Set SSL mode for the zone"""
        print(f"🔐 Setting SSL mode to: {mode}")

        if not zone_id:
            zone_id = self.get_zone_id('markcheli.com')
            if not zone_id:
                return False

        # Valid SSL modes: off, flexible, full, strict
        valid_modes = ['off', 'flexible', 'full', 'strict']
        if mode not in valid_modes:
            print(f"❌ Invalid SSL mode. Valid options: {', '.join(valid_modes)}")
            return False

        ssl_data = {'value': mode}
        success, result = self._api_request('PATCH', f'/zones/{zone_id}/settings/ssl', ssl_data)

        if success:
            new_mode = result['result']['value']
            print(f"✅ SSL mode updated to: {new_mode}")
            return True
        else:
            print(f"❌ Failed to set SSL mode: {result.get('errors', 'Unknown error')}")
            return False

    def configure_full_strict_ssl(self) -> bool:
        """Configure Full (Strict) SSL mode and related settings"""
        print("🔒 Configuring Full (Strict) SSL mode...")

        # Get zone ID
        zone_id = self.get_zone_id('markcheli.com')
        if not zone_id:
            return False

        # Check current SSL mode
        print("🔍 Checking current SSL mode...")
        current_mode = self.get_ssl_mode(zone_id)
        if current_mode:
            print(f"   Current SSL mode: {current_mode}")

        # Set SSL mode to Full (Strict)
        if not self.set_ssl_mode('strict', zone_id):
            return False

        # Additional SSL settings for security
        print("🔧 Configuring additional SSL settings...")

        ssl_settings = [
            ('always_use_https', 'on', 'Force HTTPS redirects'),
            ('tls_1_3', 'on', 'Enable TLS 1.3'),
            ('min_tls_version', '1.2', 'Set minimum TLS version to 1.2'),
            ('ssl_recommender', 'on', 'Enable SSL recommender')
        ]

        all_success = True
        for setting, value, description in ssl_settings:
            print(f"   🔧 {description}...")
            success, result = self._api_request('PATCH', f'/zones/{zone_id}/settings/{setting}', {'value': value})

            if success:
                print(f"      ✅ {setting}: {result['result']['value']}")
            else:
                print(f"      ⚠️  Failed to set {setting}: {result.get('errors', 'Unknown')}")
                # Don't fail the whole process for individual settings
                # all_success = False

        if all_success:
            print("🎉 Full (Strict) SSL configuration completed successfully!")
        else:
            print("⚠️  SSL mode set, but some additional settings failed")

        return True

def main():
    """CLI interface for SSL management"""
    import argparse

    parser = argparse.ArgumentParser(description='Cloudflare Origin Certificate Manager')
    parser.add_argument('action', choices=[
        'list', 'create', 'create-wildcards', 'download', 'validate', 'revoke',
        'ssl-mode', 'configure-ssl'
    ], help='Action to perform')

    parser.add_argument('--hostnames', nargs='+', help='Hostnames for certificate')
    parser.add_argument('--cert-id', help='Certificate ID')
    parser.add_argument('--cert-name', help='Certificate name for saving')
    parser.add_argument('--validity', type=int, default=5475, help='Validity in days (default: 5475 = 15 years)')
    parser.add_argument('--mode', help='SSL mode (off, flexible, full, strict)')

    args = parser.parse_args()

    try:
        ssl_manager = CloudflareSSLManager()

        if args.action == 'list':
            certificates = ssl_manager.list_origin_certificates()
            sys.exit(0)

        elif args.action == 'create':
            if not args.hostnames:
                print("❌ Hostnames required for create action")
                sys.exit(1)
            certificate = ssl_manager.create_origin_certificate(args.hostnames, args.validity)
            sys.exit(0 if certificate else 1)

        elif args.action == 'create-wildcards':
            success = ssl_manager.create_wildcard_certificates()
            sys.exit(0 if success else 1)

        elif args.action == 'download':
            if not args.cert_id or not args.cert_name:
                print("❌ Certificate ID and name required for download")
                sys.exit(1)
            success = ssl_manager.download_certificate(args.cert_id, args.cert_name)
            sys.exit(0 if success else 1)

        elif args.action == 'validate':
            success = ssl_manager.validate_certificates()
            sys.exit(0 if success else 1)

        elif args.action == 'revoke':
            if not args.cert_id:
                print("❌ Certificate ID required for revoke action")
                sys.exit(1)
            success = ssl_manager.revoke_certificate(args.cert_id)
            sys.exit(0 if success else 1)

        elif args.action == 'ssl-mode':
            if args.mode:
                success = ssl_manager.set_ssl_mode(args.mode)
                sys.exit(0 if success else 1)
            else:
                current_mode = ssl_manager.get_ssl_mode()
                if current_mode:
                    print(f"Current SSL mode: {current_mode}")
                    sys.exit(0)
                else:
                    sys.exit(1)

        elif args.action == 'configure-ssl':
            success = ssl_manager.configure_full_strict_ssl()
            sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()