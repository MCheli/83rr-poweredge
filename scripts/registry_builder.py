#!/usr/bin/env python3
"""
Container Registry Builder and Publisher

This script builds Docker images locally and pushes them to GitHub Container Registry (ghcr.io),
enabling pure Portainer API deployments without SSH dependencies.

Features:
- Builds all stack images locally
- Tags with semantic versioning
- Pushes to ghcr.io/MCheli/<stack-name>
- Updates compose files to use registry images
- Integrates with unified Portainer stack manager

Usage:
    python scripts/registry_builder.py build <stack_name>     # Build single stack
    python scripts/registry_builder.py build-all             # Build all stacks
    python scripts/registry_builder.py push <stack_name>     # Push single stack
    python scripts/registry_builder.py deploy <stack_name>   # Build, push, and deploy
    python scripts/registry_builder.py list-images          # List built images
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv
import yaml

class RegistryBuilder:
    def __init__(self):
        load_dotenv()

        self.registry = "ghcr.io"
        self.namespace = "mcheli"  # GitHub username

        # Define stacks that need building
        self.BUILD_STACKS = {
            'personal-website': {
                'compose_file': 'infrastructure/personal-website/docker-compose.yml',
                'services': {
                    'website': {
                        'context': './frontend',
                        'dockerfile': './frontend/Dockerfile',
                        'target': None,  # Production build
                        'image_name': 'personal-website'  # Clean name: personal-website
                    },
                    'website-dev': {
                        'context': './frontend',
                        'dockerfile': './frontend/Dockerfile',
                        'target': 'builder',  # Development build
                        'image_name': 'personal-website-dev'  # Clean name: personal-website-dev
                    }
                }
            },
            'flask-api': {
                'compose_file': 'infrastructure/flask-api/docker-compose.yml',
                'services': {
                    'flask-api': {
                        'context': './backend',
                        'dockerfile': './backend/Dockerfile',
                        'target': None,  # Production build
                        'image_name': 'flask'  # Clean name: flask
                    },
                    'flask-api-dev': {
                        'context': './backend',
                        'dockerfile': './backend/Dockerfile',
                        'target': None,  # Same as prod for now
                        'image_name': 'flask-dev'  # Clean name: flask-dev
                    }
                }
            },
            'jupyter': {
                'compose_file': 'infrastructure/jupyter/docker-compose.yml',
                'services': {
                    'jupyterhub': {
                        'context': '.',
                        'dockerfile': 'Dockerfile',
                        'target': None
                    }
                }
            }
        }

    def _run_command(self, cmd, cwd=None, capture_output=False):
        """Run shell command with proper error handling"""
        print(f"🔄 Running: {cmd}")
        try:
            if capture_output:
                result = subprocess.run(
                    cmd, shell=True, cwd=cwd, capture_output=True, text=True, check=True
                )
                return result.stdout.strip()
            else:
                subprocess.run(cmd, shell=True, cwd=cwd, check=True)
                return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Command failed: {e}")
            if capture_output and e.stderr:
                print(f"Error output: {e.stderr}")
            return False

    def _get_image_tag(self, stack_name, service_name, version="latest"):
        """Generate clean image tag using custom image names"""
        build_config = self.BUILD_STACKS[stack_name]['services'][service_name]
        image_name = build_config.get('image_name', f"{stack_name}-{service_name}")
        return f"{self.registry}/{self.namespace}/{image_name}:{version}"

    def _check_docker_login(self):
        """Check if authenticated with GitHub Container Registry using robust auth manager"""
        try:
            from github_registry_auth import GitHubRegistryAuth
            auth_manager = GitHubRegistryAuth()

            # Check if already authenticated
            if auth_manager.is_authenticated():
                print("✅ GitHub Container Registry authentication verified")
                return True
            else:
                print("🔐 Authenticating to GitHub Container Registry...")
                return auth_manager.authenticate()

        except ImportError:
            print("⚠️  Advanced authentication manager not available, falling back to basic check")
            return self._basic_auth_check()

    def _basic_auth_check(self):
        """Basic authentication check (fallback)"""
        print("🔐 Checking Docker registry authentication (basic)...")

        # Test by trying to inspect a manifest
        test_result = self._run_command(
            f"docker manifest inspect {self.registry}/{self.namespace}/personal-website-website:latest >/dev/null 2>&1; echo $?",
            capture_output=True
        )

        if test_result and test_result.strip() == "0":
            print("✅ Docker registry authentication verified")
            return True
        else:
            print("⚠️  Docker registry authentication may not be working")
            print("Run: python scripts/github_registry_auth.py test")
            return True  # Don't block - let push operations handle auth errors

    def build_stack(self, stack_name, version="latest", push=False, multiplatform=True):
        """Build all services for a specific stack"""
        if stack_name not in self.BUILD_STACKS:
            print(f"❌ Unknown stack: {stack_name}")
            print(f"Available stacks: {', '.join(self.BUILD_STACKS.keys())}")
            return False

        stack_config = self.BUILD_STACKS[stack_name]
        compose_file = Path(stack_config['compose_file'])

        if not compose_file.exists():
            print(f"❌ Compose file not found: {compose_file}")
            return False

        stack_dir = compose_file.parent
        print(f"🏗️  Building stack: {stack_name}")
        print(f"📁 Working directory: {stack_dir}")
        if multiplatform:
            print("🌍 Multi-platform build: linux/amd64,linux/arm64")
        print("=" * 60)

        success_count = 0
        total_services = len(stack_config['services'])

        for service_name, build_config in stack_config['services'].items():
            print(f"\n🔨 Building service: {service_name}")

            # Generate image tag
            image_tag = self._get_image_tag(stack_name, service_name, version)
            print(f"🏷️  Image tag: {image_tag}")

            # Build Docker command - use buildx for multi-platform if requested
            if multiplatform and push:
                # Multi-platform build with push (buildx required)
                build_cmd = f"docker buildx build --platform linux/amd64,linux/arm64"
                build_cmd += f" -f {build_config['dockerfile']}"
                build_cmd += f" -t {image_tag}"

                if build_config['target']:
                    build_cmd += f" --target {build_config['target']}"

                build_cmd += f" --push {build_config['context']}"

                # Execute multi-platform build with push
                if self._run_command(build_cmd, cwd=stack_dir):
                    print(f"✅ Built and pushed {service_name} (multi-platform)")
                    success_count += 1
                else:
                    print(f"❌ Failed to build {service_name}")
            else:
                # Regular single-platform build
                build_cmd = f"docker build"
                build_cmd += f" -f {build_config['dockerfile']}"
                build_cmd += f" -t {image_tag}"

                if build_config['target']:
                    build_cmd += f" --target {build_config['target']}"

                build_cmd += f" {build_config['context']}"

                # Execute build
                if self._run_command(build_cmd, cwd=stack_dir):
                    print(f"✅ Built {service_name}")
                    success_count += 1

                    # Push if requested (separate step for single-platform)
                    if push and not multiplatform:
                        if self.push_image(image_tag):
                            print(f"✅ Pushed {service_name}")
                        else:
                            print(f"❌ Failed to push {service_name}")
                else:
                    print(f"❌ Failed to build {service_name}")

        print(f"\n📊 Build Summary: {success_count}/{total_services} services built successfully")
        return success_count == total_services

    def push_image(self, image_tag):
        """Push single image to registry"""
        return self._run_command(f"docker push {image_tag}")

    def push_stack(self, stack_name, version="latest"):
        """Push all images for a stack"""
        if stack_name not in self.BUILD_STACKS:
            print(f"❌ Unknown stack: {stack_name}")
            return False

        if not self._check_docker_login():
            return False

        stack_config = self.BUILD_STACKS[stack_name]
        print(f"📤 Pushing stack: {stack_name}")

        success_count = 0
        total_services = len(stack_config['services'])

        for service_name in stack_config['services'].keys():
            image_tag = self._get_image_tag(stack_name, service_name, version)

            if self.push_image(image_tag):
                print(f"✅ Pushed {service_name}: {image_tag}")
                success_count += 1
            else:
                print(f"❌ Failed to push {service_name}")

        print(f"\n📊 Push Summary: {success_count}/{total_services} services pushed successfully")
        return success_count == total_services

    def generate_registry_compose(self, stack_name, version="latest"):
        """Generate compose file using registry images instead of build contexts"""
        if stack_name not in self.BUILD_STACKS:
            print(f"❌ Unknown stack: {stack_name}")
            return None

        stack_config = self.BUILD_STACKS[stack_name]
        compose_file = Path(stack_config['compose_file'])

        # Load original compose file
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)

        # Replace build contexts with registry images
        modified_services = []
        for service_name, build_config in stack_config['services'].items():
            if service_name in compose_data['services']:
                service_def = compose_data['services'][service_name]

                # Remove build section
                if 'build' in service_def:
                    del service_def['build']

                # Add image reference
                image_tag = self._get_image_tag(stack_name, service_name, version)
                service_def['image'] = image_tag
                modified_services.append(service_name)

        # Generate registry-based compose file
        registry_file = compose_file.parent / f"docker-compose.registry.yml"
        with open(registry_file, 'w') as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)

        print(f"✅ Generated registry compose: {registry_file}")
        print(f"📝 Modified services: {', '.join(modified_services)}")

        return registry_file

    def build_all(self, version="latest", push=False, multiplatform=True):
        """Build all stacks that need building"""
        print("🏗️  Building all stacks")
        if multiplatform:
            print("🌍 Multi-platform builds enabled (linux/amd64,linux/arm64)")
        print("=" * 60)

        success_stacks = []
        failed_stacks = []

        for stack_name in self.BUILD_STACKS.keys():
            print(f"\n{'='*20} {stack_name.upper()} {'='*20}")

            if self.build_stack(stack_name, version, push, multiplatform):
                success_stacks.append(stack_name)
            else:
                failed_stacks.append(stack_name)

        print(f"\n🎯 FINAL SUMMARY")
        print("=" * 60)
        print(f"✅ Successful: {len(success_stacks)} - {', '.join(success_stacks)}")

        if failed_stacks:
            print(f"❌ Failed: {len(failed_stacks)} - {', '.join(failed_stacks)}")
            return False
        else:
            print("🎉 All stacks built successfully!")
            return True

    def list_images(self, stack_name=None):
        """List built images"""
        print("🐳 Built Container Images")
        print("=" * 60)

        if stack_name:
            if stack_name not in self.BUILD_STACKS:
                print(f"❌ Unknown stack: {stack_name}")
                return
            stacks_to_check = [stack_name]
        else:
            stacks_to_check = self.BUILD_STACKS.keys()

        for stack in stacks_to_check:
            print(f"\n📦 {stack}:")
            stack_config = self.BUILD_STACKS[stack]

            for service_name in stack_config['services'].keys():
                image_tag = self._get_image_tag(stack, service_name, "latest")

                # Check if image exists locally
                result = self._run_command(f"docker images -q {image_tag}", capture_output=True)
                if result:
                    print(f"  ✅ {image_tag}")
                else:
                    print(f"  ❌ {image_tag} (not built)")

    def setup_server_auth(self, github_token=None, github_username=None):
        """Setup Docker registry authentication on the Portainer server"""
        print("🔐 Setting up server authentication for GitHub Container Registry")

        try:
            from github_registry_auth import GitHubRegistryAuth
            auth_manager = GitHubRegistryAuth()

            # Use the robust authentication manager
            return auth_manager.setup_server_authentication()

        except ImportError:
            print("⚠️  Advanced authentication manager not available, using basic setup")
            return self._basic_server_auth_setup(github_token, github_username)

    def _basic_server_auth_setup(self, github_token=None, github_username=None):
        """Basic server authentication setup (fallback)"""
        # Get credentials from environment or parameters
        if not github_token:
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                print("❌ GitHub token not provided and GITHUB_TOKEN not set")
                print("Please set GITHUB_TOKEN environment variable or run:")
                print("python scripts/github_registry_auth.py setup-server")
                return False

        if not github_username:
            github_username = self.namespace  # Use the namespace as default username

        # Get SSH configuration
        ssh_host = os.getenv('SSH_HOST')
        ssh_user = os.getenv('SSH_USER')

        if not ssh_host or not ssh_user:
            print("❌ SSH configuration missing (SSH_HOST, SSH_USER)")
            print("Cannot setup server authentication without SSH access")
            return False

        print(f"🔗 Configuring registry authentication on {ssh_host}")

        # Setup Docker login on the server using secure method
        try:
            ssh_cmd = f"ssh {ssh_user}@{ssh_host}"
            # Use --password-stdin for security instead of -p flag
            docker_login_cmd = f'echo "{github_token}" | docker login {self.registry} -u {github_username} --password-stdin'
            full_cmd = f'{ssh_cmd} "{docker_login_cmd}"'

            result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                print("✅ Server authentication configured successfully")
                print("⚠️  Note: Credentials are stored on the server in ~/.docker/config.json")
                return True
            else:
                print("❌ Failed to configure server authentication")
                print(f"Error: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Error setting up server authentication: {str(e)}")
            return False

    def deploy_with_registry(self, stack_name, version="latest", multiplatform=True):
        """Build, push, generate registry compose, and deploy via Portainer"""
        print(f"🚀 Complete Registry-based Deployment: {stack_name}")
        if multiplatform:
            print("🌍 Multi-platform deployment (linux/amd64,linux/arm64)")
        print("=" * 60)

        # Step 1: Build and Push (combined for multi-platform)
        if multiplatform:
            print("Step 1: Building and pushing multi-platform images...")
            if not self.build_stack(stack_name, version, push=True, multiplatform=True):
                print("❌ Multi-platform build and push failed")
                return False
        else:
            # Step 1: Build
            print("Step 1: Building images...")
            if not self.build_stack(stack_name, version):
                print("❌ Build failed")
                return False

            # Step 2: Push
            print("\nStep 2: Pushing to registry...")
            if not self.push_stack(stack_name, version):
                print("❌ Push failed")
                return False

        # Step 3: Generate registry compose
        step_num = 2 if multiplatform else 3
        print(f"\nStep {step_num}: Generating registry compose file...")
        registry_compose = self.generate_registry_compose(stack_name, version)
        if not registry_compose:
            print("❌ Registry compose generation failed")
            return False

        # Step 4: Deploy via Portainer
        step_num = 3 if multiplatform else 4
        print(f"\nStep {step_num}: Deploying via Portainer API...")
        sys.path.append(str(Path(__file__).parent))
        from portainer_stack_manager import PortainerStackManager

        manager = PortainerStackManager()
        success = manager.deploy_stack(stack_name, str(registry_compose))

        if success:
            print("🎉 Complete registry-based deployment successful!")
            print("✅ No SSH required - pure Portainer API deployment!")
            return True
        else:
            print("❌ Portainer deployment failed")
            return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python registry_builder.py <command> [args...]")
        print("\nCommands:")
        print("  build <stack_name> [version] [--single-platform]    - Build single stack")
        print("  build-all [version] [--single-platform]             - Build all stacks")
        print("  build-and-push <stack_name> [version]               - Build and push (multi-platform)")
        print("  build-and-push-all [version]                        - Build and push all (multi-platform)")
        print("  push <stack_name> [version]                         - Push single stack")
        print("  deploy <stack_name> [version]                       - Build, push, and deploy")
        print("  setup-server-auth [username] [token]               - Setup registry auth on server")
        print("  list-images [stack_name]                            - List built images")
        print("  generate-compose <stack> [version]                  - Generate registry compose file")
        print("\nOptions:")
        print("  --single-platform    - Build for current platform only (default: multi-platform)")
        print("\nExamples:")
        print("  python registry_builder.py build-and-push personal-website")
        print("  python registry_builder.py deploy flask-api")
        print("  python registry_builder.py build-and-push-all latest")
        sys.exit(1)

    try:
        builder = RegistryBuilder()
        command = sys.argv[1].lower()
        multiplatform = '--single-platform' not in sys.argv

        if command == 'build':
            if len(sys.argv) < 3:
                print("Usage: python registry_builder.py build <stack_name> [version] [--single-platform]")
                sys.exit(1)

            stack_name = sys.argv[2]
            version = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else "latest"
            success = builder.build_stack(stack_name, version, push=False, multiplatform=multiplatform)

        elif command == 'build-all':
            version = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else "latest"
            success = builder.build_all(version, push=False, multiplatform=multiplatform)

        elif command == 'build-and-push':
            if len(sys.argv) < 3:
                print("Usage: python registry_builder.py build-and-push <stack_name> [version]")
                sys.exit(1)

            stack_name = sys.argv[2]
            version = sys.argv[3] if len(sys.argv) > 3 else "latest"
            success = builder.build_stack(stack_name, version, push=True, multiplatform=True)

        elif command == 'build-and-push-all':
            version = sys.argv[2] if len(sys.argv) > 2 else "latest"
            success = builder.build_all(version, push=True, multiplatform=True)

        elif command == 'push':
            if len(sys.argv) < 3:
                print("Usage: python registry_builder.py push <stack_name> [version]")
                sys.exit(1)

            stack_name = sys.argv[2]
            version = sys.argv[3] if len(sys.argv) > 3 else "latest"
            success = builder.push_stack(stack_name, version)

        elif command == 'deploy':
            if len(sys.argv) < 3:
                print("Usage: python registry_builder.py deploy <stack_name> [version]")
                sys.exit(1)

            stack_name = sys.argv[2]
            version = sys.argv[3] if len(sys.argv) > 3 else "latest"
            success = builder.deploy_with_registry(stack_name, version, multiplatform=True)

        elif command == 'setup-server-auth':
            github_username = sys.argv[2] if len(sys.argv) > 2 else None
            github_token = sys.argv[3] if len(sys.argv) > 3 else None
            success = builder.setup_server_auth(github_token, github_username)

        elif command == 'list-images':
            stack_name = sys.argv[2] if len(sys.argv) > 2 else None
            builder.list_images(stack_name)
            success = True

        elif command == 'generate-compose':
            if len(sys.argv) < 3:
                print("Usage: python registry_builder.py generate-compose <stack_name> [version]")
                sys.exit(1)

            stack_name = sys.argv[2]
            version = sys.argv[3] if len(sys.argv) > 3 else "latest"
            registry_file = builder.generate_registry_compose(stack_name, version)
            success = registry_file is not None

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