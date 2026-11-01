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

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InfrastructureHealthTest:
    def __init__(self):
        load_dotenv()

        # Test configuration
        self.public_services = {
            'personal-website': {
                'url': 'https://www.markcheli.com',
                'expected_content': 'Mark Cheli',
                'description': 'Personal website'
            },
            'flask-api': {
                'url': 'https://flask.markcheli.com/health',
                'expected_content': 'healthy',
                'description': 'Flask API health endpoint'
            },
            'cookbook': {
                'url': 'https://cookbook.markcheli.com',
                'expected_content': 'Cookbook',
                'description': 'Recipe cookbook (static site)'
            },
            'plex': {
                # /web is the public login page; "/" returns 401 since
                # 2026-10-18 (Plex no longer trusts nginx traffic as LAN).
                'url': 'https://videos.markcheli.com/web/index.html',
                'expected_content': 'plex',
                'description': 'Plex Media Server'
            },
            'seafile': {
                'url': 'https://files.markcheli.com',
                'expected_content': 'seafile',
                'description': 'Seafile file sync and share'
            },
            'seafile-notification': {
                'url': 'https://files.markcheli.com/notification/ping',
                'expected_content': 'pong',
                'description': 'Seafile notification server (desktop sync push)'
            },
            'home-assistant': {
                'url': 'https://home.markcheli.com',
                'expected_content': 'Home Assistant',
                'description': 'Home Assistant (proxied by nginx)'
            },
            'tallied': {
                # App UI is Google SSO; the unauthenticated API health endpoint
                # is the meaningful liveness check.
                'url': 'https://money.markcheli.com/api/v1/health',
                'expected_content': '"status":"ok"',
                'description': 'Tallied personal finance API health'
            },
            'tasks': {
                'url': 'https://tasks.markcheli.com/api/health',
                'expected_content': '"status":"ok"',
                'description': 'Tasks API health'
            },
            'tasks-demo': {
                'url': 'https://tasks-demo.markcheli.com/api/auth/config',
                'expected_content': '"demo_mode":true',
                'description': 'Tasks public demo (read-only, made-up data)'
            },
            'uptime-kuma': {
                # "/" is a deliberate nginx 302 to the public status page.
                'url': 'https://status.markcheli.com/status/homelab',
                'expected_content': 'homelab status',
                'description': 'Uptime Kuma public status page'
            }
        }

        # Basic-auth credentials for the "Ops Services" nginx gate
        # (infrastructure/nginx/.htpasswd, gitignored, baked into the nginx
        # image). Optional: if set in .env / the environment, gated services are
        # tested end-to-end (expect 200 + content); otherwise the test verifies
        # the gate itself (401 + Basic challenge from nginx).
        self.ops_auth = None
        ops_user = os.getenv('OPS_BASIC_AUTH_USER')
        ops_password = os.getenv('OPS_BASIC_AUTH_PASSWORD')
        if ops_user and ops_password:
            self.ops_auth = (ops_user, ops_password)

        # LAN-only services (skip if not on LAN)
        # 'auth_gate': nginx auth_basic realm configured for that vhost in
        # infrastructure/nginx/conf.d/production.conf (commit b5158c3).
        self.lan_services = {
            'opensearch-dashboards': {
                'url': 'https://logs.ops.markcheli.com',
                'expected_content': 'OpenSearch',
                'description': 'OpenSearch Dashboards',
                'auth_gate': 'Ops Services'
            },
            'opensearch-api': {
                'url': 'https://opensearch.ops.markcheli.com',
                'expected_content': 'cluster_name',
                'description': 'OpenSearch REST API',
                'auth_gate': 'Ops Services'
            },
            'grafana': {
                'url': 'https://dashboard.ops.markcheli.com',
                'expected_content': 'Grafana',
                'description': 'Grafana monitoring dashboard'
            },
            'prometheus': {
                'url': 'https://prometheus.ops.markcheli.com',
                'expected_content': 'Prometheus',
                'description': 'Prometheus metrics database',
                'auth_gate': 'Ops Services'
            },
            'cadvisor': {
                'url': 'https://cadvisor.ops.markcheli.com',
                'expected_content': 'cAdvisor',
                'description': 'Container metrics monitoring',
                'auth_gate': 'Ops Services'
            },
            'daily-report': {
                'url': 'https://report.ops.markcheli.com/health',
                'expected_content': '"status": "ok"',
                'description': 'Daily report preview service health'
            },
            'energy-monitor': {
                'url': 'https://energy.ops.markcheli.com/api/health',
                'expected_content': '"ok": true',
                'description': 'Energy monitor panel tool health'
            },
            'openclaw': {
                'url': 'https://openclaw.ops.markcheli.com',
                'expected_content': 'OpenClaw',
                'description': 'OpenClaw control UI'
            },
            'edge-tts': {
                # Host-published on LOCAL_IP (not 0.0.0.0), no nginx vhost (plain HTTP).
                'url': f"http://{os.getenv('LOCAL_IP', 'localhost')}:5050/v1/models",
                'expected_content': 'tts-1',
                'description': 'Edge TTS (OpenAI-compatible) model list'
            },
            'faster-whisper': {
                'url': f"http://{os.getenv('LOCAL_IP', 'localhost')}:5051/health",
                'expected_content': 'OK',
                'description': 'Faster Whisper STT health'
            }
        }

        # Hostnames that must resolve. *.ops records are DNS-only and must
        # point at the LAN IP (LOCAL_IP in .env).
        self.dns_domains = [
            'www.markcheli.com',
            'flask.markcheli.com',
            'cookbook.markcheli.com',
            'videos.markcheli.com',
            'files.markcheli.com',
            'home.markcheli.com',
            'money.markcheli.com',
            'tasks.markcheli.com',
            'tasks-demo.markcheli.com',
            'status.markcheli.com',
            'minecraft.markcheli.com',
            'dashboard.ops.markcheli.com',
            'prometheus.ops.markcheli.com',
            'cadvisor.ops.markcheli.com',
            'logs.ops.markcheli.com',
            'opensearch.ops.markcheli.com',
            'report.ops.markcheli.com',
            'energy.ops.markcheli.com',
            'openclaw.ops.markcheli.com'
        ]

        # Expected containers and their health criteria
        # (health 'healthy' = compose defines a healthcheck for it)
        self.expected_containers = {
            'nginx': {'status': 'running', 'health': 'healthy'},
            'nginx-exporter': {'status': 'running', 'health': None},
            'opensearch': {'status': 'running', 'health': 'healthy'},
            'opensearch-dashboards': {'status': 'running', 'health': 'healthy'},
            'fluent-bit': {'status': 'running', 'health': None},
            'flask-api': {'status': 'running', 'health': 'healthy'},
            'personal-website': {'status': 'running', 'health': 'healthy'},
            'cookbook': {'status': 'running', 'health': 'healthy'},
            'minecraft': {'status': 'running', 'health': 'healthy'},
            'asa': {'status': 'running', 'health': None},
            'plex': {'status': 'running', 'health': 'healthy'},
            'seafile': {'status': 'running', 'health': 'healthy'},
            'seafile-db': {'status': 'running', 'health': None},
            'seafile-memcached': {'status': 'running', 'health': None},
            'seafile-redis': {'status': 'running', 'health': None},
            'seafile-notification': {'status': 'running', 'health': None},
            'grafana': {'status': 'running', 'health': 'healthy'},
            'prometheus': {'status': 'running', 'health': 'healthy'},
            'cadvisor': {'status': 'running', 'health': 'healthy'},
            'node-exporter': {'status': 'running', 'health': 'healthy'},
            'tallied': {'status': 'running', 'health': 'healthy'},
            'tallied-db': {'status': 'running', 'health': 'healthy'},
            'tallied-scheduler': {'status': 'running', 'health': 'healthy'},
            'tasks': {'status': 'running', 'health': 'healthy'},
            'tasks-db': {'status': 'running', 'health': 'healthy'},
            'tasks-demo': {'status': 'running', 'health': 'healthy'},
            'tasks-demo-db': {'status': 'running', 'health': 'healthy'},
            'daily-report': {'status': 'running', 'health': 'healthy'},
            'energy-monitor': {'status': 'running', 'health': 'healthy'},
            'energy-monitor-db': {'status': 'running', 'health': 'healthy'},
            'uptime-kuma': {'status': 'running', 'health': 'healthy'},
            'openclaw': {'status': 'running', 'health': 'healthy'},
            'edge-tts': {'status': 'running', 'health': 'healthy'},
            'faster-whisper': {'status': 'running', 'health': 'healthy'},
            'watchtower': {'status': 'running', 'health': 'healthy'}
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

    def run_command(self, command):
        """Execute command locally"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def test_dns_resolution(self):
        """Test DNS resolution for all services"""
        print("\n🔍 Testing DNS Resolution")
        print("=" * 50)

        import socket
        local_ip = os.getenv('LOCAL_IP')
        unresolved = []
        wrong_lan_ip = []
        for domain in self.dns_domains:
            try:
                addrs = sorted({ai[4][0] for ai in socket.getaddrinfo(domain, None, socket.AF_INET)})
            except socket.gaierror:
                print(f"❌ {domain} failed to resolve")
                unresolved.append(domain)
                continue
            if domain.endswith('.ops.markcheli.com') and local_ip and local_ip not in addrs:
                print(f"❌ {domain} resolves to {', '.join(addrs)} (expected LAN IP {local_ip})")
                wrong_lan_ip.append(domain)
            else:
                print(f"✅ {domain} resolves")

        if unresolved:
            self.log_test("DNS Resolution", "FAIL", f"Unresolvable: {', '.join(unresolved)}")
        else:
            self.log_test("DNS Resolution", "PASS", f"All {len(self.dns_domains)} hostnames resolve")

        if local_ip and wrong_lan_ip:
            self.log_test("DNS LAN Records", "FAIL", f"*.ops not pointing at LOCAL_IP: {', '.join(wrong_lan_ip)}")
        elif local_ip:
            self.log_test("DNS LAN Records", "PASS", "All *.ops records point at LOCAL_IP")

    def test_container_health(self):
        """Test Docker container status"""
        print("\n🐳 Testing Container Health")
        print("=" * 50)

        success, output, error = self.run_command("docker ps --format '{{.Names}},{{.Status}},{{.Image}}'")

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
        success, output, error = self.run_command("docker exec opensearch curl -s http://localhost:9200/_cluster/health")
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
        success, output, error = self.run_command("docker exec opensearch curl -s 'http://localhost:9200/_cat/indices?h=index' | grep logs-homelab")
        if success and output.strip():
            indices_count = len(output.strip().split('\n'))
            self.log_test("OpenSearch Indices", "PASS", f"Found {indices_count} log indices")

            # Test recent log ingestion
            today_index = f"logs-homelab-{datetime.now().strftime('%Y.%m.%d')}"
            success, output, error = self.run_command(f"docker exec opensearch curl -s 'http://localhost:9200/{today_index}/_count'")
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
            self.log_test("OpenSearch Indices", "WARN", "No log indices found (logging not configured)")

    def test_web_service(self, name, config, timeout=10):
        """Test individual web service with proper SSL certificate validation"""
        url = config['url']
        expected_content = config.get('expected_content', '')
        auth_gate = config.get('auth_gate')
        auth = self.ops_auth if auth_gate else None

        # Plain-HTTP endpoints (host-published ports) have no certificate to check
        if not url.startswith('https://'):
            try:
                response = requests.get(url, timeout=timeout, allow_redirects=True)
            except requests.exceptions.RequestException as e:
                self.log_test(f"Web Service: {name}", "FAIL", f"Connection error: {str(e)}")
                return
        else:
            response = None

        # First test with SSL verification enabled
        try:
            if response is None:
                response = requests.get(url, timeout=timeout, verify=True, allow_redirects=True, auth=auth)
                self.log_test(f"SSL Certificate: {name}", "PASS", "Valid SSL certificate")
        except requests.exceptions.SSLError as ssl_error:
            self.log_test(f"SSL Certificate: {name}", "FAIL", f"Invalid SSL certificate: {str(ssl_error)}")

            # Try without SSL verification to test basic connectivity
            try:
                response = requests.get(url, timeout=timeout, verify=False, allow_redirects=True, auth=auth)
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
        if auth_gate and auth is None:
            # No credentials available: verify the deliberate nginx basic-auth
            # gate is what answered (not an upstream/app 401).
            challenge = response.headers.get('WWW-Authenticate', '')
            server = response.headers.get('Server', '').lower()
            if (response.status_code == 401 and challenge.startswith('Basic')
                    and f'realm="{auth_gate}"' in challenge and server == 'nginx'):
                self.log_test(f"Web Service: {name}", "PASS",
                              f"Auth-gated: 401 Basic realm=\"{auth_gate}\" from nginx "
                              f"(set OPS_BASIC_AUTH_USER/OPS_BASIC_AUTH_PASSWORD to test upstream)")
            else:
                self.log_test(f"Web Service: {name}", "FAIL",
                              f"Expected nginx basic-auth challenge, got HTTP {response.status_code} "
                              f"(WWW-Authenticate: {challenge or 'none'}, Server: {server or 'none'})")
            return
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

        # Check if port is published to host
        success, output, error = self.run_command("docker ps --filter name=minecraft --format '{{.Ports}}'")

        if not success or not output:
            self.log_test("Minecraft Server", "WARN", "Could not check Minecraft port configuration")
            return

        # Check if port 25565 is published to host (would show as 0.0.0.0:25565->25565/tcp)
        port_published = "0.0.0.0:25565" in output or ":::25565" in output

        if not port_published:
            # Port not published - container running but not externally accessible
            # This is actually OK for LAN-only access via reverse proxy or Docker network
            self.log_test("Minecraft Port", "PASS", "Container running (port not published to host - Docker network only)")
            return

        # Port is published, test external connectivity
        import socket
        minecraft_port = 25565

        # Try localhost first (we're on the server)
        try:
            sock = socket.create_connection(("localhost", minecraft_port), timeout=5)
            sock.close()
            self.log_test("Minecraft Port 25565", "PASS", f"TCP connection to localhost:{minecraft_port} successful")
        except socket.timeout:
            self.log_test("Minecraft Port 25565", "WARN", f"TCP connection to localhost:{minecraft_port} timed out")
        except socket.error as e:
            self.log_test("Minecraft Port 25565", "WARN", f"TCP connection to localhost:{minecraft_port} failed: {e}")
        except Exception as e:
            self.log_test("Minecraft Port 25565", "WARN", f"Unexpected error testing minecraft connectivity: {e}")

    def test_backup_integrity(self):
        """Test backup directory and recent backups"""
        print("\n💾 Testing Backup Integrity")
        print("=" * 50)

        # scripts/backup.sh (cron, daily 02:00) writes to the NAS at
        # /mnt/nas/83rr-backup and, only on full success, posts a
        # "backup-heartbeat" doc to OpenSearch. That heartbeat is the canonical
        # "backup OK" signal (OpenSearch monitor alerts after 26h without one).
        backup_root = Path("/mnt/nas/83rr-backup")
        success, _, _ = self.run_command("mountpoint -q /mnt/nas")
        if success and backup_root.is_dir():
            self.log_test("Backup NAS Mount", "PASS", f"NAS mounted, {backup_root} present")
        elif success:
            self.log_test("Backup NAS Mount", "WARN", f"NAS mounted but {backup_root} missing")
        else:
            self.log_test("Backup NAS Mount", "WARN", "NAS not mounted at /mnt/nas (backup.sh will try to mount it)")

        query = ("docker exec opensearch curl -s "
                 "'http://localhost:9200/logs-homelab-*/_search?size=1&sort=@timestamp:desc"
                 "&q=container_name:backup-heartbeat&_source=@timestamp'")
        success, output, error = self.run_command(query)
        if not success:
            self.log_test("Backup Heartbeat", "WARN", "Could not query OpenSearch for backup heartbeat", error)
        else:
            try:
                hits = json.loads(output).get('hits', {}).get('hits', [])
            except json.JSONDecodeError:
                hits = None
            if hits is None:
                self.log_test("Backup Heartbeat", "WARN", "Could not parse backup heartbeat query response")
            elif not hits:
                self.log_test("Backup Heartbeat", "FAIL", "No backup heartbeat found in OpenSearch")
            else:
                ts = hits[0]['_source']['@timestamp']
                last = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                if age_h <= 26:
                    self.log_test("Backup Heartbeat", "PASS", f"Last successful backup {age_h:.1f}h ago ({ts})")
                else:
                    self.log_test("Backup Heartbeat", "FAIL",
                                  f"Last successful backup {age_h:.1f}h ago ({ts}) - over 26h, see logs/backup.log")

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