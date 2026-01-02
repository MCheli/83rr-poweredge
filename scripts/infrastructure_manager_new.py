#!/usr/bin/env python3
"""
Native Docker Compose Infrastructure Management System

This script provides comprehensive infrastructure management using native Docker Compose:
- Environment-aware deployment (development vs production)
- Auto-build and push for production deployments
- Health monitoring and validation
- Service availability testing
- Native Docker Compose orchestration (NO Portainer dependency)

This is the MASTER CONTROLLER for all infrastructure operations.
"""

import os
import sys
import time
import subprocess
import socket
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple

class InfrastructureManager:
    def __init__(self):
        """Initialize the infrastructure manager with environment detection"""
        load_dotenv()
        self.project_root = Path(__file__).parent.parent
        self.environment = self._detect_environment()
        self.compose_files = self._get_compose_files()

        # GitHub Container Registry settings
        self.github_registry = "ghcr.io/mcheli"

        # Services that need to be built and pushed for production
        self.buildable_services = [
            'nginx',
            'personal-website',
            'flask-api',
            'jupyter'
        ]

        print(f"🌍 Environment detected: {self.environment}")
        print(f"📄 Using compose files: {', '.join(self.compose_files)}")

    def _detect_environment(self) -> str:
        """Detect if we're running in development or production environment"""
        # Method 1: Check environment variable
        env = os.getenv('INFRASTRUCTURE_ENV')
        if env:
            return env.lower()

        # Method 2: Check hostname patterns
        hostname = socket.gethostname().lower()
        if any(prod_indicator in hostname for prod_indicator in ['server', 'prod', 'poweredge']):
            return 'production'

        # Method 3: Check if we're running in expected production path
        if '/home/mcheli' in str(self.project_root):
            return 'production'

        # Default to development
        return 'development'

    def _get_compose_files(self) -> List[str]:
        """Get appropriate compose files for current environment"""
        files = ['docker-compose.yml']

        if self.environment == 'production':
            files.append('docker-compose.prod.yml')
        # docker-compose.override.yml is auto-loaded for development

        return files

    def _run_command(self, command: List[str], cwd: Optional[Path] = None, capture_output: bool = True) -> Tuple[bool, str, str]:
        """Run a command and return success status, stdout, stderr"""
        try:
            if cwd is None:
                cwd = self.project_root

            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=capture_output,
                text=True,
                timeout=300  # 5 minute timeout
            )

            success = result.returncode == 0
            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "Command timed out after 5 minutes"
        except Exception as e:
            return False, "", f"Command failed: {str(e)}"

    def _docker_compose_cmd(self, action: str, services: List[str] = None, extra_args: List[str] = None) -> List[str]:
        """Build docker compose command with appropriate files"""
        cmd = ['docker', 'compose']

        # Add compose files
        for file in self.compose_files:
            cmd.extend(['-f', file])

        # Add action
        cmd.append(action)

        # Add services if specified
        if services:
            cmd.extend(services)

        # Add extra arguments
        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def build_images(self) -> bool:
        """Build all buildable images locally"""
        print("🔨 Building container images...")

        if self.environment == 'production':
            print("⚠️  Production environment detected - building for registry push")

        for service in self.buildable_services:
            print(f"  📦 Building {service}...")

            cmd = self._docker_compose_cmd('build', [service])
            success, stdout, stderr = self._run_command(cmd)

            if not success:
                print(f"❌ Failed to build {service}: {stderr}")
                return False

            print(f"  ✅ {service} built successfully")

        print("🎉 All images built successfully!")
        return True

    def push_images(self) -> bool:
        """Push all buildable images to GitHub Container Registry"""
        print("📤 Pushing images to GitHub Container Registry...")

        # First, ensure we're authenticated
        if not self._ensure_registry_auth():
            return False

        for service in self.buildable_services:
            print(f"  🚀 Pushing {service}...")

            # Tag for registry
            local_tag = f"{self.project_root.name}_{service}"
            registry_tag = f"{self.github_registry}/{service}:latest"

            # Tag image
            tag_cmd = ['docker', 'tag', local_tag, registry_tag]
            success, stdout, stderr = self._run_command(tag_cmd)

            if not success:
                print(f"❌ Failed to tag {service}: {stderr}")
                return False

            # Push image
            push_cmd = ['docker', 'push', registry_tag]
            success, stdout, stderr = self._run_command(push_cmd)

            if not success:
                print(f"❌ Failed to push {service}: {stderr}")
                return False

            print(f"  ✅ {service} pushed successfully")

        print("🎉 All images pushed successfully!")
        return True

    def build_and_push(self) -> bool:
        """Build and push images in one operation"""
        return self.build_images() and self.push_images()

    def _ensure_registry_auth(self) -> bool:
        """Ensure we're authenticated with GitHub Container Registry"""
        print("🔐 Checking GitHub Container Registry authentication...")

        # Check if we have a GitHub token
        github_token = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_PAT')
        if not github_token:
            print("❌ No GitHub token found. Set GITHUB_TOKEN or GITHUB_PAT environment variable.")
            return False

        # Try to login to registry
        login_cmd = ['echo', github_token]
        docker_login_cmd = ['docker', 'login', 'ghcr.io', '-u', os.getenv('GITHUB_USERNAME', 'mcheli'), '--password-stdin']

        try:
            # Pipe echo output to docker login
            echo_process = subprocess.Popen(login_cmd, stdout=subprocess.PIPE, text=True)
            login_process = subprocess.Popen(docker_login_cmd, stdin=echo_process.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            echo_process.stdout.close()

            stdout, stderr = login_process.communicate()

            if login_process.returncode == 0:
                print("✅ GitHub Container Registry authentication successful")
                return True
            else:
                print(f"❌ GitHub Container Registry authentication failed: {stderr}")
                return False

        except Exception as e:
            print(f"❌ Registry authentication error: {str(e)}")
            return False

    def deploy(self, services: List[str] = None, build_first: bool = None) -> bool:
        """Deploy infrastructure services"""
        print(f"🚀 Deploying infrastructure in {self.environment} mode...")

        # Auto-determine if we should build first
        if build_first is None:
            if self.environment == 'production':
                build_first = True  # Auto-build and push for production
                print("🔨 Production deployment - building and pushing images first...")
                if not self.build_and_push():
                    return False
            else:
                build_first = False  # Use local builds for development
        elif build_first and self.environment == 'production':
            if not self.build_and_push():
                return False
        elif build_first:
            if not self.build_images():
                return False

        # Deploy services
        print("📋 Starting Docker Compose deployment...")

        cmd = self._docker_compose_cmd('up', services, ['-d', '--remove-orphans'])
        success, stdout, stderr = self._run_command(cmd, capture_output=False)

        if not success:
            print(f"❌ Deployment failed: {stderr}")
            return False

        print("✅ Deployment completed!")

        # Wait a moment for services to initialize
        print("⏳ Waiting for services to initialize...")
        time.sleep(10)

        # Run health check
        return self.health_check()

    def stop(self, services: List[str] = None) -> bool:
        """Stop infrastructure services"""
        print("🛑 Stopping infrastructure services...")

        cmd = self._docker_compose_cmd('down', services)
        success, stdout, stderr = self._run_command(cmd, capture_output=False)

        if success:
            print("✅ Services stopped successfully")
        else:
            print(f"❌ Failed to stop services: {stderr}")

        return success

    def restart(self, services: List[str] = None) -> bool:
        """Restart infrastructure services"""
        print("🔄 Restarting infrastructure services...")

        cmd = self._docker_compose_cmd('restart', services)
        success, stdout, stderr = self._run_command(cmd, capture_output=False)

        if success:
            print("✅ Services restarted successfully")
        else:
            print(f"❌ Failed to restart services: {stderr}")

        return success

    def status(self) -> bool:
        """Show status of all services"""
        print("📊 Infrastructure Status:")

        cmd = self._docker_compose_cmd('ps', extra_args=['--format', 'table'])
        success, stdout, stderr = self._run_command(cmd, capture_output=False)

        return success

    def logs(self, services: List[str] = None, follow: bool = False) -> bool:
        """Show logs for services"""
        print("📋 Service Logs:")

        extra_args = []
        if follow:
            extra_args.append('-f')

        cmd = self._docker_compose_cmd('logs', services, extra_args)
        success, stdout, stderr = self._run_command(cmd, capture_output=False)

        return success

    def health_check(self) -> bool:
        """Perform basic health check on services"""
        print("🏥 Performing health check...")

        # Check if containers are running
        cmd = self._docker_compose_cmd('ps', extra_args=['--format', 'json'])
        success, stdout, stderr = self._run_command(cmd)

        if not success:
            print(f"❌ Failed to get container status: {stderr}")
            return False

        # Parse container status
        try:
            containers = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    container = json.loads(line)
                    containers.append(container)

            print(f"📊 Found {len(containers)} containers:")

            healthy_count = 0
            for container in containers:
                name = container.get('Service', 'Unknown')
                state = container.get('State', 'Unknown')
                status = container.get('Status', 'Unknown')

                if state == 'running':
                    print(f"  ✅ {name}: {status}")
                    healthy_count += 1
                else:
                    print(f"  ❌ {name}: {status}")

            success_rate = (healthy_count / len(containers)) * 100 if containers else 0
            print(f"🎯 Health check: {healthy_count}/{len(containers)} services healthy ({success_rate:.1f}%)")

            return success_rate >= 80  # Consider healthy if 80% or more services are running

        except Exception as e:
            print(f"❌ Failed to parse container status: {str(e)}")
            return False

def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='83RR PowerEdge Infrastructure Manager')
    parser.add_argument('action', choices=[
        'deploy', 'stop', 'restart', 'status', 'logs', 'health',
        'build', 'push', 'build-and-push'
    ], help='Action to perform')

    parser.add_argument('--services', nargs='+', help='Specific services to target')
    parser.add_argument('--build', action='store_true', help='Build images before deploying')
    parser.add_argument('--follow', action='store_true', help='Follow logs output')
    parser.add_argument('--env', choices=['development', 'production'], help='Override environment detection')

    args = parser.parse_args()

    # Override environment if specified
    if args.env:
        os.environ['INFRASTRUCTURE_ENV'] = args.env

    manager = InfrastructureManager()

    try:
        if args.action == 'deploy':
            success = manager.deploy(args.services, args.build)
        elif args.action == 'stop':
            success = manager.stop(args.services)
        elif args.action == 'restart':
            success = manager.restart(args.services)
        elif args.action == 'status':
            success = manager.status()
        elif args.action == 'logs':
            success = manager.logs(args.services, args.follow)
        elif args.action == 'health':
            success = manager.health_check()
        elif args.action == 'build':
            success = manager.build_images()
        elif args.action == 'push':
            success = manager.push_images()
        elif args.action == 'build-and-push':
            success = manager.build_and_push()
        else:
            print(f"❌ Unknown action: {args.action}")
            success = False

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()