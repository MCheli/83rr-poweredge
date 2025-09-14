#!/usr/bin/env python3
"""
Comprehensive infrastructure health test suite
Tests all services, containers, URLs, and functionality to ensure system is working correctly.

This script should be run:
- Before any git commits
- After deployment changes
- When verifying system health
- During troubleshooting sessions
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import requests
import urllib3
from dotenv import load_dotenv

# Add scripts directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dns_manager import SquarespaceDNSManager as InfrastructureDNS

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InfrastructureHealthTest:
    def __init__(self):
        load_dotenv()
        self.ssh_user = os.getenv('SSH_USER')
        self.ssh_host = os.getenv('SSH_HOST')
        self.dns = InfrastructureDNS()

        # Test configuration
        self.public_services = {
            'whoami': {
                'url': 'https://ops.markcheli.com',
                'expected_content': 'Hostname:',
                'description': 'Whoami service at base domain'
            },
            'jupyter': {
                'url': 'https://jupyter.markcheli.com',
                'expected_content': 'JupyterHub',
                'description': 'JupyterHub login page'
            },
            'personal-website': {
                'url': 'https://www.markcheli.com',
                'expected_content': 'Mark Cheli Developer Terminal',
                'description': 'Personal website terminal interface'
            },
            'flask-api': {
                'url': 'https://flask.markcheli.com/health',
                'expected_content': 'healthy',
                'description': 'Flask API health endpoint'
            }
        }

        # LAN-only services (skip if not on LAN)
        self.lan_services = {
            'traefik': {
                'url': 'https://traefik-local.ops.markcheli.com',
                'expected_content': 'Dashboard',
                'description': 'Traefik dashboard',
                'auth_required': True
            },
            'portainer': {
                'url': 'https://portainer-local.ops.markcheli.com',
                'expected_content': 'Portainer',
                'description': 'Portainer container management',
                'auth_required': True
            },
            'opensearch-dashboards': {
                'url': 'https://logs-local.ops.markcheli.com',
                'expected_content': 'OpenSearch',
                'description': 'OpenSearch Dashboards',
                'auth_required': False
            },
            'website-dev': {
                'url': 'https://www-dev.ops.markcheli.com',
                'expected_content': 'Mark Cheli Developer Terminal',
                'description': 'Development website (LAN-only)',
                'auth_required': False
            },
            'flask-api-dev': {
                'url': 'https://flask-dev.ops.markcheli.com/health',
                'expected_content': 'healthy',
                'description': 'Flask API Development Environment (LAN-only)',
                'auth_required': False
            }
        }

        # Expected containers and their health criteria
        self.expected_containers = {
            'traefik': {'status': 'running', 'health': None},
            'whoami': {'status': 'running', 'health': None},
            'opensearch': {'status': 'running', 'health': None},
            'opensearch-dashboards': {'status': 'running', 'health': None},
            'logstash': {'status': 'running', 'health': None},
            'filebeat': {'status': 'running', 'health': None},
            'jupyterhub': {'status': 'running', 'health': None},
            'jupyterhub-proxy': {'status': 'running', 'health': None},
            'jupyterhub-db': {'status': 'running', 'health': 'healthy'},
            'portainer': {'status': 'running', 'health': None},
            'mark-cheli-flask-api': {'status': 'running', 'health': 'healthy'},
            'mark-cheli-flask-api-dev': {'status': 'running', 'health': 'healthy'},
            'mark-cheli-website': {'status': 'running', 'health': 'healthy'},
            'mark-cheli-website-dev': {'status': 'running', 'health': 'healthy'},
            'minecraft-server': {'status': 'running', 'health': 'healthy'}
        }

        self.results = []
        self.failures = []

    def log_test(self, test_name, status, message, details=None):
        """Log test result"""
        result = {
            'test': test_name,
            'status': status,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'details': details
        }
        self.results.append(result)

        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {message}")

        if status == "FAIL":
            self.failures.append(result)
            if details:
                print(f"   Details: {details}")

    def run_ssh_command(self, command):
        """Execute command on remote server via SSH"""
        try:
            full_command = f"ssh {self.ssh_user}@{self.ssh_host} '{command}'"
            result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=30)
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def test_dns_resolution(self):
        """Test DNS resolution for all services"""
        print("\n🔍 Testing DNS Resolution")
        print("=" * 50)

        dns_ok = self.dns.audit_current_dns()

        if dns_ok:
            self.log_test("DNS Resolution", "PASS", "DNS audit completed")
        else:
            self.log_test("DNS Resolution", "FAIL", "DNS audit failed")

    def test_container_health(self):
        """Test Docker container status on server"""
        print("\n🐳 Testing Container Health")
        print("=" * 50)

        success, output, error = self.run_ssh_command("docker ps --format '{{.Names}},{{.Status}},{{.Image}}'")

        if not success:
            self.log_test("Container Health", "FAIL", "Could not connect to server or get container status", error)
            return

        running_containers = {}
        for line in output.strip().split('\n'):
            if line:
                parts = line.split(',')
                if len(parts) >= 2:
                    name = parts[0]
                    status = parts[1]
                    running_containers[name] = status

        # Check expected containers
        for container, criteria in self.expected_containers.items():
            if container in running_containers:
                status = running_containers[container]
                if criteria['status'] == 'running' and 'Up' in status:
                    if criteria['health'] == 'healthy' and 'healthy' not in status.lower():
                        self.log_test(f"Container: {container}", "WARN", f"Running but not healthy: {status}")
                    else:
                        self.log_test(f"Container: {container}", "PASS", f"Running: {status}")
                else:
                    self.log_test(f"Container: {container}", "FAIL", f"Not running: {status}")
            else:
                self.log_test(f"Container: {container}", "FAIL", "Container not found")

    def test_opensearch_functionality(self):
        """Test OpenSearch cluster health and log ingestion"""
        print("\n🔎 Testing OpenSearch Functionality")
        print("=" * 50)

        # Test cluster health
        success, output, error = self.run_ssh_command("docker exec opensearch curl -s http://localhost:9200/_cluster/health")
        if success:
            try:
                health_data = json.loads(output)
                if health_data.get('status') in ['green', 'yellow']:
                    self.log_test("OpenSearch Cluster", "PASS", f"Cluster status: {health_data.get('status')}")
                else:
                    self.log_test("OpenSearch Cluster", "FAIL", f"Cluster unhealthy: {health_data.get('status')}")
            except json.JSONDecodeError:
                self.log_test("OpenSearch Cluster", "FAIL", "Could not parse cluster health response")
        else:
            self.log_test("OpenSearch Cluster", "FAIL", "Could not check cluster health", error)

        # Test log indices exist
        success, output, error = self.run_ssh_command("docker exec opensearch curl -s 'http://localhost:9200/_cat/indices?h=index' | grep logs-homelab")
        if success and output.strip():
            indices_count = len(output.strip().split('\n'))
            self.log_test("OpenSearch Indices", "PASS", f"Found {indices_count} log indices")

            # Test recent log ingestion
            today_index = f"logs-homelab-{datetime.now().strftime('%Y.%m.%d')}"
            success, output, error = self.run_ssh_command(f"docker exec opensearch curl -s 'http://localhost:9200/{today_index}/_count'")
            if success:
                try:
                    count_data = json.loads(output)
                    log_count = count_data.get('count', 0)
                    if log_count > 0:
                        self.log_test("Log Ingestion", "PASS", f"Today's logs: {log_count} entries")
                    else:
                        self.log_test("Log Ingestion", "WARN", "No logs found for today")
                except json.JSONDecodeError:
                    self.log_test("Log Ingestion", "WARN", "Could not check log count")
        else:
            self.log_test("OpenSearch Indices", "FAIL", "No log indices found")

    def test_web_service(self, name, config, timeout=10):
        """Test individual web service with proper SSL certificate validation"""
        url = config['url']
        expected_content = config.get('expected_content', '')
        auth_required = config.get('auth_required', False)

        # First test with SSL verification enabled
        ssl_valid = False
        try:
            response_verified = requests.get(url, timeout=timeout, verify=True, allow_redirects=True)
            ssl_valid = True
            self.log_test(f"SSL Certificate: {name}", "PASS", "Valid SSL certificate")
            response = response_verified
        except requests.exceptions.SSLError as ssl_error:
            self.log_test(f"SSL Certificate: {name}", "FAIL", f"Invalid SSL certificate: {str(ssl_error)}")

            # Try without SSL verification to test basic connectivity
            try:
                response = requests.get(url, timeout=timeout, verify=False, allow_redirects=True)
                self.log_test(f"Basic Connectivity: {name}", "WARN", "Service accessible but SSL certificate invalid")
            except Exception as e:
                self.log_test(f"Basic Connectivity: {name}", "FAIL", f"Service not accessible: {str(e)}")
                return
        except requests.exceptions.ConnectionError as e:
            self.log_test(f"Web Service: {name}", "FAIL", f"Connection error: {str(e)}")
            return
        except requests.exceptions.Timeout:
            self.log_test(f"Web Service: {name}", "FAIL", f"Request timeout ({timeout}s)")
            return
        except Exception as e:
            self.log_test(f"Web Service: {name}", "FAIL", f"Unexpected error: {str(e)}")
            return

        # Test HTTP response
        if response.status_code == 401 and auth_required:
            self.log_test(f"Web Service: {name}", "PASS", f"Authentication required (expected): {response.status_code}")
        elif response.status_code not in [200, 302]:
            self.log_test(f"Web Service: {name}", "FAIL", f"HTTP error: {response.status_code}")
            return
        else:
            self.log_test(f"Web Service: {name}", "PASS", f"HTTP response: {response.status_code}")

        # Check content if response is successful
        if response.status_code == 200 and expected_content:
            if expected_content.lower() in response.text.lower():
                self.log_test(f"Content Check: {name}", "PASS", f"Found expected content: '{expected_content}'")
            else:
                self.log_test(f"Content Check: {name}", "WARN", f"Expected content '{expected_content}' not found")

        # Check response time
        if response.elapsed.total_seconds() > 5:
            self.log_test(f"Performance: {name}", "WARN", f"Slow response: {response.elapsed.total_seconds():.2f}s")
        else:
            self.log_test(f"Performance: {name}", "PASS", f"Response time: {response.elapsed.total_seconds():.2f}s")

    def test_web_services(self):
        """Test all web services"""
        print("\n🌐 Testing Web Services (Public)")
        print("=" * 50)

        for name, config in self.public_services.items():
            self.test_web_service(name, config)

        print("\n🏠 Testing Web Services (LAN-only)")
        print("=" * 50)

        for name, config in self.lan_services.items():
            self.test_web_service(name, config, timeout=5)  # Shorter timeout for LAN services

    def test_minecraft_connectivity(self):
        """Test Minecraft server TCP connectivity"""
        print("\n🎮 Testing Minecraft Server")
        print("=" * 50)

        import socket

        # Test minecraft server port connectivity
        minecraft_host = "minecraft.markcheli.com"
        minecraft_port = 25565

        try:
            # Create socket connection with timeout
            sock = socket.create_connection((minecraft_host, minecraft_port), timeout=10)
            sock.close()
            self.log_test("Minecraft Port 25565", "PASS", f"TCP connection to {minecraft_host}:{minecraft_port} successful")
        except socket.timeout:
            self.log_test("Minecraft Port 25565", "FAIL", f"TCP connection to {minecraft_host}:{minecraft_port} timed out")
        except socket.error as e:
            self.log_test("Minecraft Port 25565", "FAIL", f"TCP connection to {minecraft_host}:{minecraft_port} failed: {e}")
        except Exception as e:
            self.log_test("Minecraft Port 25565", "FAIL", f"Unexpected error testing minecraft connectivity: {e}")

    def test_backup_integrity(self):
        """Test backup directory and recent backups"""
        print("\n💾 Testing Backup Integrity")
        print("=" * 50)

        backup_dir = Path("backups")
        if backup_dir.exists():
            backup_files = list(backup_dir.rglob("*backup*.yml"))
            if backup_files:
                # Check for recent backups (within last 7 days)
                recent_backups = []
                one_week_ago = time.time() - (7 * 24 * 60 * 60)

                for backup_file in backup_files:
                    if backup_file.stat().st_mtime > one_week_ago:
                        recent_backups.append(backup_file)

                if recent_backups:
                    self.log_test("Backup Files", "PASS", f"Found {len(recent_backups)} recent backup files")
                else:
                    self.log_test("Backup Files", "WARN", f"No recent backups found (found {len(backup_files)} total)")
            else:
                self.log_test("Backup Files", "WARN", "No backup files found")
        else:
            self.log_test("Backup Files", "WARN", "Backup directory does not exist")

    def test_git_status(self):
        """Test git repository status"""
        print("\n📝 Testing Git Repository Status")
        print("=" * 50)

        try:
            # Check for uncommitted changes
            result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
            if result.returncode == 0:
                if result.stdout.strip():
                    self.log_test("Git Status", "WARN", "Uncommitted changes detected")
                else:
                    self.log_test("Git Status", "PASS", "Working directory clean")
            else:
                self.log_test("Git Status", "WARN", "Could not check git status")

            # Check if we're ahead of remote
            result = subprocess.run(['git', 'status', '-b', '--porcelain'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                first_line = result.stdout.split('\n')[0]
                if 'ahead' in first_line:
                    self.log_test("Git Sync", "WARN", "Local commits not pushed to remote")
                else:
                    self.log_test("Git Sync", "PASS", "Repository synced with remote")
        except Exception as e:
            self.log_test("Git Status", "WARN", f"Git check failed: {str(e)}")

    def run_all_tests(self):
        """Run complete infrastructure health test suite"""
        print("🏥 Infrastructure Health Test Suite")
        print("=" * 70)
        print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)

        # Run all test categories
        self.test_dns_resolution()
        self.test_container_health()
        self.test_opensearch_functionality()
        self.test_web_services()
        self.test_minecraft_connectivity()
        self.test_backup_integrity()
        self.test_git_status()

        # Summary
        print("\n📊 Test Results Summary")
        print("=" * 70)

        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.results if r['status'] == 'FAIL'])
        warned_tests = len([r for r in self.results if r['status'] == 'WARN'])

        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"⚠️  Warnings: {warned_tests}")
        print(f"❌ Failed: {failed_tests}")

        if failed_tests > 0:
            print(f"\n❌ CRITICAL FAILURES ({failed_tests}):")
            for failure in self.failures:
                print(f"   • {failure['test']}: {failure['message']}")

        # Overall status
        if failed_tests == 0:
            if warned_tests == 0:
                print(f"\n🎉 ALL SYSTEMS OPERATIONAL")
                return True
            else:
                print(f"\n✅ SYSTEMS OPERATIONAL (with {warned_tests} warnings)")
                return True
        else:
            print(f"\n🚨 SYSTEM ISSUES DETECTED - {failed_tests} critical failures")
            return False

def main():
    """Main test execution"""
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print(__doc__)
        print("\nUsage:")
        print("  python scripts/test_infrastructure.py           # Run all tests")
        print("  python scripts/test_infrastructure.py --help    # Show this help")
        return

    # Ensure we're in the project root
    if not Path('.env').exists():
        print("❌ Error: Run this script from the project root directory")
        sys.exit(1)

    # Run tests
    tester = InfrastructureHealthTest()
    success = tester.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()