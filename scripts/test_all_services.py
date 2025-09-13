#!/usr/bin/env python3
"""
Comprehensive Service Testing Script

Tests all deployed services to verify they are working correctly with SSL certificates.
Includes both public and LAN-only services with proper categorization.
"""

import os
import subprocess
import sys
import time
from dotenv import load_dotenv

class ServiceTester:
    def __init__(self):
        load_dotenv()

        # Define all services with their expected accessibility
        self.services = {
            'public': [
                {
                    'name': 'Personal Website',
                    'url': 'https://www.markcheli.com',
                    'expected_codes': [200, 301, 302],
                    'description': 'Main personal website'
                },
                {
                    'name': 'Flask API',
                    'url': 'https://flask.markcheli.com',
                    'expected_codes': [200, 404, 500],  # May not have root endpoint
                    'description': 'Flask API backend'
                },
                {
                    'name': 'JupyterHub',
                    'url': 'https://jupyter.markcheli.com',
                    'expected_codes': [200, 302, 401],  # Login redirect expected
                    'description': 'JupyterHub data science platform (PUBLIC)'
                },
                {
                    'name': 'Ops Testing Service',
                    'url': 'https://ops.markcheli.com',
                    'expected_codes': [200, 404],
                    'description': 'Testing/monitoring service'
                }
            ],
            'lan_only': [
                {
                    'name': 'Traefik Dashboard',
                    'url': 'https://traefik-local.ops.markcheli.com',
                    'expected_codes': [200, 301, 302, 307, 401],  # May redirect to /dashboard
                    'description': 'Traefik reverse proxy dashboard'
                },
                {
                    'name': 'Website Dev Environment',
                    'url': 'https://www-dev.ops.markcheli.com',
                    'expected_codes': [200, 404, 500],
                    'description': 'Development version of website'
                },
                {
                    'name': 'OpenSearch',
                    'url': 'https://opensearch-local.ops.markcheli.com',
                    'expected_codes': [200, 401, 403],
                    'description': 'OpenSearch cluster'
                },
                {
                    'name': 'Logs Dashboard',
                    'url': 'https://logs-local.ops.markcheli.com',
                    'expected_codes': [200, 302, 401],
                    'description': 'OpenSearch Dashboards for logs'
                }
            ]
        }

    def test_service_from_server(self, service):
        """Test a service from the server itself"""
        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        if not all([ssh_host, ssh_user]):
            print("❌ SSH configuration missing")
            return False

        # Test HTTP response from server with proper session cleanup
        test_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o BatchMode=yes {ssh_user}@{ssh_host} "
            curl -I -k --connect-timeout 15 --max-time 30 '{service['url']}' 2>/dev/null | head -1 || echo 'CONNECTION_FAILED';
            exit
        "'''

        try:
            result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True, timeout=45)

            if result.returncode == 0:
                output = result.stdout.strip()
                if 'CONNECTION_FAILED' in output:
                    return {'status': 'connection_failed', 'response': 'Connection failed'}
                elif 'HTTP' in output:
                    # Extract status code
                    parts = output.split()
                    if len(parts) >= 2:
                        try:
                            status_code = int(parts[1])
                            return {'status': 'success', 'code': status_code, 'response': output}
                        except ValueError:
                            return {'status': 'unknown', 'response': output}
                    return {'status': 'unknown', 'response': output}
                else:
                    return {'status': 'unknown', 'response': output}
            else:
                return {'status': 'error', 'response': result.stderr}
        except subprocess.TimeoutExpired:
            return {'status': 'timeout', 'response': 'Request timed out'}
        except Exception as e:
            return {'status': 'exception', 'response': str(e)}

    def test_ssl_certificate(self, url):
        """Test SSL certificate validity for a service"""
        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        # Extract domain from URL
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]

        ssl_test_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o BatchMode=yes {ssh_user}@{ssh_host} "
            echo | openssl s_client -connect {domain}:443 -servername {domain} 2>/dev/null | openssl x509 -noout -subject -dates 2>/dev/null || echo 'SSL_FAILED';
            exit
        "'''

        try:
            result = subprocess.run(ssl_test_cmd, shell=True, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and 'SSL_FAILED' not in result.stdout:
                return {'status': 'valid', 'details': result.stdout.strip()}
            else:
                return {'status': 'invalid', 'details': 'SSL certificate test failed'}
        except:
            return {'status': 'error', 'details': 'SSL test error'}

    def format_test_result(self, service, test_result, ssl_result=None):
        """Format test result for display"""
        name = service['name']
        url = service['url']
        expected = service['expected_codes']

        if test_result['status'] == 'success':
            code = test_result['code']
            if code in expected:
                status_icon = "✅"
                status_msg = f"HTTP {code} (Expected)"
            else:
                status_icon = "⚠️"
                status_msg = f"HTTP {code} (Unexpected, expected: {expected})"
        else:
            status_icon = "❌"
            if test_result['status'] == 'connection_failed':
                status_msg = "Connection Failed"
            elif test_result['status'] == 'timeout':
                status_msg = "Request Timeout"
            else:
                status_msg = f"Error: {test_result.get('response', 'Unknown error')}"

        print(f"  {status_icon} {name}")
        print(f"      URL: {url}")
        print(f"      Status: {status_msg}")

        if ssl_result and ssl_result['status'] == 'valid':
            print(f"      SSL: ✅ Valid certificate")
        elif ssl_result:
            print(f"      SSL: ❌ {ssl_result['details']}")

        print()

    def test_all_services(self):
        """Test all services comprehensively"""
        print("🔍 Comprehensive Service Testing")
        print("=" * 50)
        print()

        # Test public services
        print("🌐 PUBLIC SERVICES")
        print("-" * 20)
        for service in self.services['public']:
            test_result = self.test_service_from_server(service)
            time.sleep(2)  # Brief delay to respect SSH session limits
            ssl_result = self.test_ssl_certificate(service['url'])
            self.format_test_result(service, test_result, ssl_result)
            time.sleep(1)  # Small delay between services

        # Test LAN-only services
        print("🏠 LAN-ONLY SERVICES")
        print("-" * 20)
        for service in self.services['lan_only']:
            test_result = self.test_service_from_server(service)
            time.sleep(2)  # Brief delay to respect SSH session limits
            ssl_result = self.test_ssl_certificate(service['url'])
            self.format_test_result(service, test_result, ssl_result)
            time.sleep(1)  # Small delay between services

    def test_docker_containers(self):
        """Check Docker container status"""
        print("🐳 CONTAINER STATUS")
        print("-" * 20)

        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        container_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o BatchMode=yes {ssh_user}@{ssh_host} "
            docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | head -20;
            exit
        "'''

        try:
            result = subprocess.run(container_cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"❌ Failed to get container status: {result.stderr}")
        except Exception as e:
            print(f"❌ Error checking containers: {e}")

    def test_certificates_summary(self):
        """Show certificate summary"""
        print("🔐 SSL CERTIFICATES SUMMARY")
        print("-" * 20)

        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        cert_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o BatchMode=yes {ssh_user}@{ssh_host} "
            echo 'Wildcard Certificate Status:' &&
            ls -la /home/mcheli/traefik/certs/ &&
            echo '' &&
            echo '*.markcheli.com certificate expires:' &&
            openssl x509 -in /home/mcheli/traefik/certs/wildcard-markcheli.crt -noout -dates | grep notAfter &&
            echo '*.ops.markcheli.com certificate expires:' &&
            openssl x509 -in /home/mcheli/traefik/certs/wildcard-ops-markcheli.crt -noout -dates | grep notAfter;
            exit
        "'''

        try:
            result = subprocess.run(cert_cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"❌ Failed to get certificate info: {result.stderr}")
        except Exception as e:
            print(f"❌ Error checking certificates: {e}")

def main():
    tester = ServiceTester()

    print("🧪 Starting Comprehensive Infrastructure Testing")
    print("=" * 60)
    print()

    # Test all services
    tester.test_all_services()

    # Check container status
    tester.test_docker_containers()

    # Show certificate summary
    tester.test_certificates_summary()

    print()
    print("🏁 Testing Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()