#!/usr/bin/env python3
"""
Deploy All Services with SSH Session Management

This script deploys all infrastructure services while respecting the 2 concurrent SSH session limit.
Services are deployed sequentially with proper session cleanup between deployments.

IMPORTANT SSH LIMITATIONS:
- Maximum 2 concurrent SSH sessions allowed
- Each deployment uses 1 SSH session that is properly closed
- Do not run multiple instances of this script simultaneously
- Wait for completion before running other SSH operations
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv

class ManagedSSHDeployer:
    def __init__(self):
        load_dotenv()
        self.base_dir = Path(__file__).parent.parent
        self.deploy_script = self.base_dir / "scripts" / "deploy_via_ssh.py"

        # Services in deployment order (Traefik first, then dependent services)
        self.services = [
            {
                'name': 'traefik',
                'path': 'infrastructure/traefik/docker-compose.yml',
                'description': 'Traefik reverse proxy with SSL certificates',
                'wait_time': 15  # Extra time for Traefik to initialize
            },
            {
                'name': 'personal-website',
                'path': 'infrastructure/personal-website/docker-compose.yml',
                'description': 'Personal website and Flask API',
                'wait_time': 10
            },
            {
                'name': 'jupyter',
                'path': 'infrastructure/jupyter/docker-compose.yml',
                'description': 'JupyterHub data science environment',
                'wait_time': 10
            },
            {
                'name': 'opensearch',
                'path': 'infrastructure/opensearch/docker-compose.yml',
                'description': 'OpenSearch logging and monitoring',
                'wait_time': 10
            }
        ]

    def check_ssh_connectivity(self):
        """Verify SSH connectivity before starting deployment"""
        print("🔍 Checking SSH connectivity...")

        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        if not all([ssh_host, ssh_user]):
            print("❌ SSH configuration missing (SSH_HOST, SSH_USER)")
            return False

        # Test SSH connection
        test_cmd = f"ssh -o ConnectTimeout=10 {ssh_user}@{ssh_host} 'echo SSH_OK'"
        result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0 and 'SSH_OK' in result.stdout:
            print(f"✅ SSH connectivity confirmed to {ssh_user}@{ssh_host}")
            return True
        else:
            print(f"❌ SSH connection failed: {result.stderr}")
            return False

    def deploy_service(self, service):
        """Deploy a single service with proper session management"""
        print(f"\n🚀 Deploying {service['name']}: {service['description']}")
        print("=" * 60)

        # Run deployment script
        cmd = ['python3', str(self.deploy_script), service['name'], service['path']]

        result = subprocess.run(cmd, cwd=self.base_dir)

        if result.returncode == 0:
            print(f"✅ {service['name']} deployed successfully")

            # Wait for service to stabilize before next deployment
            if service['wait_time'] > 0:
                print(f"⏳ Waiting {service['wait_time']}s for {service['name']} to stabilize...")
                time.sleep(service['wait_time'])

            return True
        else:
            print(f"❌ {service['name']} deployment failed")
            return False

    def verify_services(self):
        """Verify that all services are running"""
        print("\n🔍 Verifying service health...")

        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        # Check container status
        check_cmd = f'''ssh -o ConnectTimeout=30 {ssh_user}@{ssh_host} "
            echo 'Container Status:' &&
            docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' &&
            echo '' &&
            echo 'Network Status:' &&
            docker network ls | grep traefik
        "'''

        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            print(result.stdout)
            return True
        else:
            print(f"❌ Service verification failed: {result.stderr}")
            return False

    def test_ssl_endpoints(self):
        """Test SSL certificate functionality"""
        print("\n🔐 Testing SSL certificates...")

        endpoints = [
            ('https://www.markcheli.com', 'Personal website'),
            ('https://flask.markcheli.com', 'Flask API'),
            ('https://traefik-local.ops.markcheli.com', 'Traefik dashboard (LAN)'),
            ('https://jupyter.ops.markcheli.com', 'JupyterHub (LAN)')
        ]

        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        for url, description in endpoints:
            test_cmd = f'''ssh -o ConnectTimeout=30 {ssh_user}@{ssh_host} "
                curl -I -k --connect-timeout 10 {url} 2>/dev/null | head -1 || echo 'FAILED'
            "'''

            result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0 and 'HTTP' in result.stdout:
                status = result.stdout.strip()
                print(f"  ✅ {description}: {status}")
            else:
                print(f"  ❌ {description}: Connection failed")

    def deploy_all(self):
        """Deploy all services with SSH session management"""
        print("🌟 Starting Managed SSH Deployment")
        print("=" * 50)
        print("⚠️  SSH Session Limits: Max 2 concurrent connections")
        print("⚠️  Services deployed sequentially to avoid conflicts")
        print()

        # Check prerequisites
        if not self.check_ssh_connectivity():
            return False

        # Deploy each service
        failed_services = []
        for service in self.services:
            if not self.deploy_service(service):
                failed_services.append(service['name'])

                # Ask whether to continue on failure
                response = input(f"\n⚠️  Continue with remaining services? [y/N]: ").lower()
                if response != 'y':
                    break

        # Final verification
        print("\n" + "=" * 50)
        if failed_services:
            print(f"⚠️  Deployment completed with failures: {', '.join(failed_services)}")
        else:
            print("🎉 All services deployed successfully!")

        # Verify deployment
        self.verify_services()

        # Test SSL
        self.test_ssl_endpoints()

        return len(failed_services) == 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--verify-only':
        deployer = ManagedSSHDeployer()
        deployer.verify_services()
        deployer.test_ssl_endpoints()
        return

    deployer = ManagedSSHDeployer()
    success = deployer.deploy_all()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()