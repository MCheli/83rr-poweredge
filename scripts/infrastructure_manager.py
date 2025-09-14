#!/usr/bin/env python3
"""
Complete Infrastructure Management System

This script provides comprehensive infrastructure management capabilities:
- Deploy all stacks with proper orchestration
- Health monitoring and validation
- Service availability testing
- Rollback capabilities
- Migration from SSH-deployed to Portainer-managed stacks

This is the MASTER CONTROLLER for all infrastructure operations.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Import our unified stack manager
sys.path.append(str(Path(__file__).parent))
from portainer_stack_manager import PortainerStackManager

class InfrastructureManager:
    def __init__(self):
        load_dotenv()
        self.stack_manager = PortainerStackManager()

        # Define infrastructure stack order and dependencies
        self.STACK_ORDER = [
            'traefik',      # Must be first - provides routing
            'jupyter',      # Independent service
            'opensearch',   # Logging infrastructure (renamed from 'logs')
            'personal-website',  # Web services
            'flask-api',    # API services
            'minecraft',    # Game services
        ]

        # Map stack names to their compose files
        self.STACK_CONFIGS = {
            'traefik': 'infrastructure/traefik/docker-compose.yml',
            'jupyter': 'infrastructure/jupyter/docker-compose.yml',
            'opensearch': 'infrastructure/opensearch/docker-compose.yml',  # Renamed from logs
            'personal-website': 'infrastructure/personal-website/docker-compose.yml',
            'flask-api': 'infrastructure/flask-api/docker-compose.yml',
            'minecraft': 'infrastructure/minecraft/docker-compose.yml',
        }

        # Registry-based compose files (for pure Portainer deployment)
        self.REGISTRY_CONFIGS = {
            'traefik': 'infrastructure/traefik/docker-compose.yml',
            'jupyter': 'infrastructure/jupyter/docker-compose.registry.yml',
            'opensearch': 'infrastructure/opensearch/docker-compose.yml',
            'personal-website': 'infrastructure/personal-website/docker-compose.registry.yml',
            'flask-api': 'infrastructure/flask-api/docker-compose.registry.yml',
            'minecraft': 'infrastructure/minecraft/docker-compose.yml',
        }

        # Define which stacks need building (for registry-based deployment)
        self.BUILD_STACKS = ['personal-website', 'flask-api', 'jupyter']

        # Registry-based deployment mode
        self.use_registry = os.getenv('USE_REGISTRY', 'false').lower() == 'true'

    def cleanup_ssh_deployed_stacks(self):
        """Remove SSH-deployed containers that conflict with Portainer management"""
        print("🧹 Cleaning up SSH-deployed stacks for Portainer migration")
        print("=" * 80)

        # Get list of unmanaged stacks
        unmanaged_stacks = ['opensearch', 'personal-website', 'flask-api', 'minecraft']

        for stack_name in unmanaged_stacks:
            print(f"🗑️  Removing SSH-deployed stack: {stack_name}")
            try:
                # Use SSH to stop and remove the stack
                ssh_host = os.getenv('SSH_HOST', '192.168.1.179')
                ssh_user = os.getenv('SSH_USER', 'mcheli')

                cleanup_cmd = f'''ssh -o ConnectTimeout=10 {ssh_user}@{ssh_host} "
                    echo 'Stopping {stack_name} containers...' &&
                    docker compose -p {stack_name} down --remove-orphans 2>/dev/null || true &&
                    docker system prune -f &&
                    echo 'Cleanup complete for {stack_name}'
                "'''

                result = subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✅ Cleaned up {stack_name}")
                else:
                    print(f"⚠️  Warning cleaning {stack_name}: {result.stderr}")

                # Small delay between cleanups
                time.sleep(2)

            except Exception as e:
                print(f"❌ Error cleaning {stack_name}: {str(e)}")

        print("\n✅ SSH-deployed stack cleanup completed")

    def deploy_all_stacks(self, clean_first=False, use_registry=None):
        """Deploy all infrastructure stacks in proper dependency order"""
        print("🚀 Deploying Complete Infrastructure")

        # Override registry mode if specified
        if use_registry is not None:
            self.use_registry = use_registry

        if self.use_registry:
            print("🐳 Using REGISTRY-BASED deployment (no SSH required!)")
        else:
            print("📡 Using HYBRID deployment (SSH + Portainer API)")

        print("=" * 80)

        if clean_first:
            self.cleanup_ssh_deployed_stacks()
            print("\n⏳ Waiting for cleanup to complete...")
            time.sleep(10)

        success_count = 0
        failed_stacks = []

        for stack_name in self.STACK_ORDER:
            # Choose the appropriate compose file based on deployment mode
            if self.use_registry:
                compose_file = self.REGISTRY_CONFIGS[stack_name]
            else:
                compose_file = self.STACK_CONFIGS[stack_name]

            print(f"\n🎯 Deploying {stack_name}...")
            print("-" * 50)

            if not Path(compose_file).exists():
                print(f"❌ Compose file not found: {compose_file}")
                failed_stacks.append(stack_name)
                continue

            # Choose deployment method
            if self.use_registry:
                # Pure Portainer API deployment using registry images
                success = self.stack_manager.deploy_stack(stack_name, compose_file)
            elif stack_name in self.BUILD_STACKS:
                # Hybrid: SSH for build-based stacks
                success = self._deploy_with_ssh(stack_name, compose_file)
            else:
                # Portainer API for simple stacks
                success = self.stack_manager.deploy_stack(stack_name, compose_file)

            if success:
                print(f"✅ {stack_name} deployed successfully")
                success_count += 1

                # Wait for stack to stabilize before deploying next
                print("⏳ Waiting for stack to stabilize...")
                time.sleep(15)

                # Quick health check
                if self.stack_manager.health_check(stack_name):
                    print(f"✅ {stack_name} health check passed")
                else:
                    print(f"⚠️  {stack_name} health check warning (may still be starting)")

            else:
                print(f"❌ {stack_name} deployment failed")
                failed_stacks.append(stack_name)

        # Final summary
        print("\n" + "=" * 80)
        print("📊 DEPLOYMENT SUMMARY")
        print("=" * 80)
        print(f"✅ Successful: {success_count}/{len(self.STACK_ORDER)}")

        if failed_stacks:
            print(f"❌ Failed: {', '.join(failed_stacks)}")
            return False
        else:
            print("🎉 All stacks deployed successfully!")
            return True

    def _deploy_with_registry(self, stack_name):
        """Deploy stack using registry-based images (pure Portainer)"""
        print(f"🐳 Registry-based deployment: {stack_name}")

        try:
            from registry_builder import RegistryBuilder
            builder = RegistryBuilder()

            # Use the registry deployment method
            return builder.deploy_with_registry(stack_name, "latest")
        except Exception as e:
            print(f"❌ Registry deployment failed: {str(e)}")
            return False

    def _deploy_with_ssh(self, stack_name, compose_file):
        """DEPRECATED: SSH deployment fallback for troubleshooting only"""
        print(f"⚠️  SSH-based deployment fallback: {stack_name}")
        print("⚠️  WARNING: SSH deployment is deprecated. Use --registry flag instead!")
        print("⚠️  This method should only be used for emergency troubleshooting.")

        try:
            from ssh_manager import SSHManager
            ssh = SSHManager()

            # Simple SSH deployment using docker compose
            deploy_cmd = f"cd /opt/infrastructure && docker compose -f {compose_file.split('/')[-1]} up -d"
            result = ssh.run_ssh_command(deploy_cmd, timeout=300)

            return result.returncode == 0 if result else False
        except Exception as e:
            print(f"❌ SSH deployment failed: {str(e)}")
            print("💡 Consider using: python infrastructure_manager.py deploy-all --registry")
            return False

    def health_check_all(self):
        """Perform comprehensive health check on all infrastructure"""
        print("🏥 Comprehensive Infrastructure Health Check")
        print("=" * 80)

        healthy_count = 0
        total_count = 0

        for stack_name in self.STACK_ORDER:
            if self.stack_manager.get_stack(stack_name):
                total_count += 1
                print(f"\n🔍 Checking {stack_name}...")

                if self.stack_manager.health_check(stack_name):
                    healthy_count += 1
                    print(f"✅ {stack_name}: HEALTHY")
                else:
                    print(f"❌ {stack_name}: UNHEALTHY")
            else:
                print(f"⚠️  {stack_name}: Not deployed")

        print("\n" + "=" * 80)
        print(f"📊 Overall Health: {healthy_count}/{total_count} stacks healthy")

        if healthy_count == total_count:
            print("🎉 All infrastructure is healthy!")
            return True
        else:
            print("🚨 Some infrastructure components are unhealthy!")
            return False

    def run_full_tests(self):
        """Run comprehensive infrastructure tests"""
        print("🧪 Running Full Infrastructure Test Suite")
        print("=" * 80)

        try:
            # Run the existing test infrastructure script
            result = subprocess.run([
                'python', 'scripts/test_infrastructure.py'
            ], cwd=Path(__file__).parent.parent, capture_output=True, text=True)

            print(result.stdout)
            if result.stderr:
                print("Errors:", result.stderr)

            return result.returncode == 0

        except Exception as e:
            print(f"❌ Test execution failed: {str(e)}")
            return False

    def migrate_to_portainer(self):
        """Complete migration from SSH-deployed to Portainer-managed stacks"""
        print("🔄 Migrating Infrastructure to Portainer Management")
        print("=" * 80)

        print("Step 1: Cleanup SSH-deployed stacks")
        self.cleanup_ssh_deployed_stacks()

        print("\nStep 2: Deploy all stacks via Portainer API")
        if not self.deploy_all_stacks():
            print("❌ Migration failed during deployment")
            return False

        print("\nStep 3: Comprehensive health check")
        if not self.health_check_all():
            print("⚠️  Migration completed but some services are unhealthy")

        print("\nStep 4: Full test suite")
        test_success = self.run_full_tests()

        if test_success:
            print("\n🎉 Migration completed successfully!")
            print("All stacks are now managed by Portainer API")
            return True
        else:
            print("\n⚠️  Migration completed but tests have warnings")
            return False

    def build_images(self, stack_name=None, push=False):
        """Build container images for registry deployment (with multi-platform support)"""
        try:
            from registry_builder import RegistryBuilder
            builder = RegistryBuilder()

            if stack_name:
                if stack_name not in self.BUILD_STACKS:
                    print(f"❌ {stack_name} doesn't require building")
                    return False
                return builder.build_stack(stack_name, "latest", push=push, multiplatform=True)
            else:
                return builder.build_all("latest", push=push, multiplatform=True)
        except Exception as e:
            print(f"❌ Build failed: {str(e)}")
            return False

    def push_images(self, stack_name=None):
        """Push container images to registry"""
        try:
            from registry_builder import RegistryBuilder
            builder = RegistryBuilder()

            if stack_name:
                if stack_name not in self.BUILD_STACKS:
                    print(f"❌ {stack_name} doesn't require building")
                    return False
                return builder.push_stack(stack_name, "latest")
            else:
                # Push all build stacks
                success_count = 0
                for stack in self.BUILD_STACKS:
                    if builder.push_stack(stack, "latest"):
                        success_count += 1
                return success_count == len(self.BUILD_STACKS)
        except Exception as e:
            print(f"❌ Push failed: {str(e)}")
            return False

    def build_and_push_images(self, stack_name=None):
        """Build and push container images to registry in one operation"""
        try:
            from registry_builder import RegistryBuilder
            builder = RegistryBuilder()

            if stack_name:
                if stack_name not in self.BUILD_STACKS:
                    print(f"❌ {stack_name} doesn't require building")
                    return False
                # Build and push in sequence
                if builder.build_stack(stack_name, "latest", push=False, multiplatform=True):
                    return builder.push_stack(stack_name, "latest")
                return False
            else:
                # Build and push all build stacks
                success_count = 0
                for stack in self.BUILD_STACKS:
                    if builder.build_stack(stack, "latest", push=False, multiplatform=True):
                        if builder.push_stack(stack, "latest"):
                            success_count += 1
                return success_count == len(self.BUILD_STACKS)
        except Exception as e:
            print(f"❌ Build and push failed: {str(e)}")
            return False

    def setup_registry_auth(self):
        """Setup Docker registry authentication on the server"""
        try:
            from github_registry_auth import GitHubRegistryAuth
            auth_manager = GitHubRegistryAuth()
            return auth_manager.setup_server_authentication()
        except ImportError:
            print("⚠️  Using fallback authentication setup")
            try:
                from registry_builder import RegistryBuilder
                builder = RegistryBuilder()
                return builder.setup_server_auth()
            except Exception as e:
                print(f"❌ Registry authentication setup failed: {str(e)}")
                return False
        except Exception as e:
            print(f"❌ Registry authentication setup failed: {str(e)}")
            return False

    def test_registry_auth(self):
        """Test Docker registry authentication"""
        try:
            from github_registry_auth import GitHubRegistryAuth
            auth_manager = GitHubRegistryAuth()
            return auth_manager.test_authentication()
        except ImportError:
            print("⚠️  Advanced authentication testing not available")
            print("Run: python scripts/github_registry_auth.py test")
            return False
        except Exception as e:
            print(f"❌ Registry authentication test failed: {str(e)}")
            return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python infrastructure_manager.py <command> [options]")
        print("\nCommands:")
        print("  deploy-all [--clean] [--registry]  - Deploy all infrastructure stacks")
        print("  build-images [stack_name]          - Build container images for registry")
        print("  push-images [stack_name]           - Push container images to registry")
        print("  build-and-push [stack_name]        - Build and push images in one operation")
        print("  setup-registry-auth                - Setup Docker registry authentication on server")
        print("  test-registry-auth                 - Test Docker registry authentication")
        print("  health-check-all                   - Health check all stacks")
        print("  run-tests                          - Run comprehensive test suite")
        print("  migrate-to-portainer               - Complete migration to Portainer management")
        print("  cleanup-ssh                        - Clean up SSH-deployed stacks")
        print("\nOptions:")
        print("  --clean      Clean up SSH-deployed stacks before deployment")
        print("  --registry   Use registry-based deployment (no SSH required)")
        print("\nExamples:")
        print("  python infrastructure_manager.py deploy-all --registry --clean")
        print("  python infrastructure_manager.py build-and-push personal-website")
        print("  python infrastructure_manager.py setup-registry-auth")
        print("  python infrastructure_manager.py health-check-all")
        print("  python infrastructure_manager.py migrate-to-portainer")
        sys.exit(1)

    try:
        manager = InfrastructureManager()
        command = sys.argv[1].lower()

        if command == 'deploy-all':
            clean_first = '--clean' in sys.argv
            use_registry = '--registry' in sys.argv
            success = manager.deploy_all_stacks(clean_first=clean_first, use_registry=use_registry)

        elif command == 'health-check-all':
            success = manager.health_check_all()

        elif command == 'run-tests':
            success = manager.run_full_tests()

        elif command == 'migrate-to-portainer':
            success = manager.migrate_to_portainer()

        elif command == 'build-images':
            stack_name = sys.argv[2] if len(sys.argv) > 2 else None
            success = manager.build_images(stack_name)

        elif command == 'push-images':
            stack_name = sys.argv[2] if len(sys.argv) > 2 else None
            success = manager.push_images(stack_name)

        elif command == 'build-and-push':
            stack_name = sys.argv[2] if len(sys.argv) > 2 else None
            success = manager.build_and_push_images(stack_name)

        elif command == 'setup-registry-auth':
            success = manager.setup_registry_auth()

        elif command == 'test-registry-auth':
            success = manager.test_registry_auth()

        elif command == 'cleanup-ssh':
            manager.cleanup_ssh_deployed_stacks()
            success = True

        else:
            print(f"❌ Unknown command: {command}")
            sys.exit(1)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()