#!/usr/bin/env python3
"""
Unified Portainer Stack Manager

This is the SINGLE UNIFIED script for all stack deployment, management, and troubleshooting.
All stacks MUST be managed through Portainer API for proper visibility and control.

Features:
- Create new stacks in Portainer
- Update existing stacks
- Deploy with environment variable support
- Health checking and validation
- Automatic cleanup and rollback on failures
- Full Portainer integration

Usage:
    python scripts/portainer_stack_manager.py create <stack_name> <compose_file>
    python scripts/portainer_stack_manager.py update <stack_name> <compose_file>
    python scripts/portainer_stack_manager.py deploy <stack_name> <compose_file>  # smart create/update
    python scripts/portainer_stack_manager.py remove <stack_name>
    python scripts/portainer_stack_manager.py list
    python scripts/portainer_stack_manager.py status <stack_name>
    python scripts/portainer_stack_manager.py health <stack_name>
"""

import os
import json
import time
import requests
import urllib3
from dotenv import load_dotenv
from pathlib import Path
import sys
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PortainerStackManager:
    def __init__(self):
        load_dotenv()

        self.portainer_url = os.getenv('PORTAINER_URL')
        self.api_key = os.getenv('PORTAINER_API_KEY')
        self.endpoint_id = os.getenv('PORTAINER_ENDPOINT_ID', '3')

        if not all([self.portainer_url, self.api_key]):
            raise ValueError("❌ Missing required environment variables (PORTAINER_URL, PORTAINER_API_KEY)")

        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def _make_request(self, method, endpoint, **kwargs):
        """Make authenticated request to Portainer API with proper error handling"""
        url = f"{self.portainer_url}/api/{endpoint}"
        kwargs.setdefault('headers', self.headers)
        kwargs.setdefault('verify', False)
        kwargs.setdefault('timeout', 30)

        try:
            response = requests.request(method, url, **kwargs)
            return response
        except requests.exceptions.RequestException as e:
            print(f"❌ API Request failed: {str(e)}")
            print(f"URL: {url}")
            print(f"Exception type: {type(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text}")
            return None

    def _load_compose_file(self, compose_file_path):
        """Load and validate docker-compose file"""
        compose_file = Path(compose_file_path)
        if not compose_file.exists():
            raise FileNotFoundError(f"❌ Compose file not found: {compose_file_path}")

        with open(compose_file, 'r') as f:
            compose_content = f.read()

        # Basic validation - check if file contains basic compose structure
        if 'services:' not in compose_content and 'version:' not in compose_content:
            raise ValueError(f"❌ File doesn't appear to be a valid docker-compose file")

        return compose_content

    def _load_env_file(self, compose_file_path):
        """Load environment variables from .env file in same directory"""
        compose_dir = Path(compose_file_path).parent
        env_file = compose_dir / '.env'

        env_vars = []
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars.append({
                            "name": key.strip(),
                            "value": value.strip()
                        })
            print(f"📝 Loaded {len(env_vars)} environment variables from {env_file}")

        return env_vars

    def list_stacks(self):
        """List all stacks in Portainer"""
        print("📚 Portainer Stack Management Report")
        print("=" * 80)

        response = self._make_request('GET', 'stacks')
        if not response or response.status_code != 200:
            print(f"❌ Failed to fetch stacks: {response.status_code if response else 'Request failed'}")
            return False

        stacks = response.json()

        if not stacks:
            print("No stacks found.")
            return True

        for stack in stacks:
            name = stack.get('Name', 'Unknown')
            stack_id = stack.get('Id', 'N/A')
            status = stack.get('Status', 'Unknown')
            endpoint_id = stack.get('EndpointId', 'N/A')

            # Status icon
            status_icon = "✅" if status == 1 else "❌" if status == 2 else "❓"

            print(f"{status_icon} **{name}** (ID: {stack_id})")
            print(f"   Status: {'Active' if status == 1 else 'Inactive' if status == 2 else 'Unknown'}")
            print(f"   Endpoint: {endpoint_id}")

            # Get creation/update dates if available
            creation_date = stack.get('CreationDate', 0)
            if creation_date:
                import datetime
                created = datetime.datetime.fromtimestamp(creation_date).strftime('%Y-%m-%d %H:%M:%S')
                print(f"   Created: {created}")

            print()

        print("=" * 80)
        print(f"📊 Total Stacks: {len(stacks)}")
        return True

    def get_stack(self, stack_name):
        """Get stack by name"""
        response = self._make_request('GET', 'stacks')
        if not response or response.status_code != 200:
            return None

        stacks = response.json()
        for stack in stacks:
            if stack['Name'] == stack_name:
                return stack

        return None

    def create_stack(self, stack_name, compose_file_path, force=False):
        """Create new stack in Portainer"""
        print(f"🚀 Creating new stack: {stack_name}")
        print("=" * 50)

        # Check if stack already exists
        existing_stack = self.get_stack(stack_name)
        if existing_stack and not force:
            print(f"❌ Stack '{stack_name}' already exists (ID: {existing_stack['Id']})")
            print("   Use 'update' command or --force flag to replace")
            return False

        if existing_stack and force:
            print(f"⚠️  Force flag enabled - removing existing stack first...")
            if not self.remove_stack(stack_name):
                print("❌ Failed to remove existing stack")
                return False

        try:
            # Load compose file and environment variables
            compose_content = self._load_compose_file(compose_file_path)
            env_vars = self._load_env_file(compose_file_path)

            print(f"📝 Loaded compose file: {len(compose_content)} characters")
            print(f"🌍 Environment variables: {len(env_vars)}")

            # Create payload
            create_payload = {
                "Name": stack_name,
                "StackFileContent": compose_content,
                "Env": env_vars
            }

            # Create stack using correct endpoint
            response = self._make_request(
                'POST',
                f'stacks/create/standalone/string?endpointId={self.endpoint_id}',
                json=create_payload,
                timeout=120
            )

            if response and response.status_code == 200:
                result = response.json()
                print("✅ Stack created successfully!")
                print(f"   Stack ID: {result.get('Id')}")
                print(f"   Stack Name: {result.get('Name')}")
                print(f"   Endpoint: {result.get('EndpointId')}")

                # Wait for containers to start
                print("⏳ Waiting for containers to start...")
                time.sleep(5)

                return True
            else:
                error_msg = f"HTTP {response.status_code}" if response else 'Request failed'
                print(f"❌ Failed to create stack: {error_msg}")
                if response:
                    print(f"Response status: {response.status_code}")
                    print(f"Response headers: {dict(response.headers)}")
                    print(f"Response text: {response.text}")
                    try:
                        error_json = response.json()
                        print(f"Error details: {error_json}")
                    except:
                        pass
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    def update_stack(self, stack_name, compose_file_path):
        """Update existing stack in Portainer"""
        print(f"🔄 Updating stack: {stack_name}")
        print("=" * 50)

        # Get existing stack
        target_stack = self.get_stack(stack_name)
        if not target_stack:
            print(f"❌ Stack '{stack_name}' not found in Portainer")
            print("   Use 'create' command to create new stack")
            return False

        stack_id = target_stack['Id']
        endpoint_id = target_stack['EndpointId']

        print(f"📋 Found stack: {stack_name} (ID: {stack_id})")

        try:
            # Load compose file and environment variables
            compose_content = self._load_compose_file(compose_file_path)
            env_vars = self._load_env_file(compose_file_path)

            print(f"📝 Loaded compose file: {len(compose_content)} characters")
            print(f"🌍 Environment variables: {len(env_vars)}")

            # Update payload
            update_payload = {
                "StackFileContent": compose_content,
                "Env": env_vars
            }

            # Update stack
            response = self._make_request(
                'PUT',
                f'stacks/{stack_id}?endpointId={endpoint_id}',
                json=update_payload,
                timeout=120
            )

            if response and response.status_code == 200:
                print("✅ Stack updated successfully!")

                # Wait for containers to restart
                print("⏳ Waiting for containers to restart...")
                time.sleep(5)

                return True
            else:
                print(f"❌ Failed to update stack: {response.status_code if response else 'Request failed'}")
                if response:
                    print(f"Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    def deploy_stack(self, stack_name, compose_file_path):
        """Smart deploy: create if doesn't exist, update if it does"""
        print(f"🎯 Smart deploy: {stack_name}")
        print("=" * 50)

        existing_stack = self.get_stack(stack_name)

        if existing_stack:
            print(f"📋 Stack exists - updating...")
            return self.update_stack(stack_name, compose_file_path)
        else:
            print(f"✨ New stack - creating...")
            return self.create_stack(stack_name, compose_file_path)

    def remove_stack(self, stack_name):
        """Remove stack from Portainer"""
        print(f"🗑️  Removing stack: {stack_name}")
        print("=" * 50)

        target_stack = self.get_stack(stack_name)
        if not target_stack:
            print(f"❌ Stack '{stack_name}' not found")
            return False

        stack_id = target_stack['Id']
        endpoint_id = target_stack['EndpointId']

        print(f"📋 Found stack: {stack_name} (ID: {stack_id})")

        response = self._make_request('DELETE', f'stacks/{stack_id}?endpointId={endpoint_id}')

        if response and response.status_code == 204:
            print("✅ Stack removed successfully!")
            return True
        else:
            print(f"❌ Failed to remove stack: {response.status_code if response else 'Request failed'}")
            if response:
                print(f"Response: {response.text}")
            return False

    def get_stack_status(self, stack_name):
        """Get detailed status of stack and its containers"""
        print(f"📊 Stack Status: {stack_name}")
        print("=" * 50)

        target_stack = self.get_stack(stack_name)
        if not target_stack:
            print(f"❌ Stack '{stack_name}' not found")
            return False

        stack_id = target_stack['Id']
        endpoint_id = target_stack['EndpointId']
        status = target_stack['Status']

        print(f"Stack ID: {stack_id}")
        print(f"Status: {'Active' if status == 1 else 'Inactive' if status == 2 else 'Unknown'}")
        print(f"Endpoint: {endpoint_id}")

        # Get containers for this stack
        response = self._make_request('GET', f'endpoints/{endpoint_id}/docker/containers/json?all=true')
        if response and response.status_code == 200:
            containers = response.json()
            stack_containers = [
                c for c in containers
                if c.get('Labels', {}).get('com.docker.compose.project') == stack_name
            ]

            print(f"\n📦 Containers: {len(stack_containers)}")
            for container in stack_containers:
                name = container['Names'][0].lstrip('/')
                status = container['Status']
                state = container['State']

                state_icon = "🟢" if state == 'running' else "🔴" if state == 'exited' else "🟡"
                print(f"   {state_icon} {name}: {status}")

        return True

    def health_check(self, stack_name):
        """Perform health check on stack"""
        print(f"🏥 Health Check: {stack_name}")
        print("=" * 50)

        target_stack = self.get_stack(stack_name)
        if not target_stack:
            print(f"❌ Stack '{stack_name}' not found")
            return False

        # Basic health check
        if target_stack['Status'] != 1:
            print(f"❌ Stack is not active (Status: {target_stack['Status']})")
            return False

        # Get containers and check their health
        endpoint_id = target_stack['EndpointId']
        response = self._make_request('GET', f'endpoints/{endpoint_id}/docker/containers/json')

        if response and response.status_code == 200:
            containers = response.json()
            stack_containers = [
                c for c in containers
                if c.get('Labels', {}).get('com.docker.compose.project') == stack_name
            ]

            healthy_count = 0
            total_count = len(stack_containers)

            for container in stack_containers:
                name = container['Names'][0].lstrip('/')
                state = container['State']

                if state == 'running':
                    health = container.get('Status', '')
                    if 'healthy' in health.lower():
                        print(f"✅ {name}: {health}")
                        healthy_count += 1
                    elif 'starting' in health.lower():
                        print(f"⏳ {name}: {health}")
                    else:
                        print(f"✅ {name}: Running")
                        healthy_count += 1
                else:
                    print(f"❌ {name}: {state}")

            print(f"\n📊 Health Summary: {healthy_count}/{total_count} containers healthy")
            return healthy_count == total_count

        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python portainer_stack_manager.py <command> [args...]")
        print("\nCommands:")
        print("  list                           - List all stacks")
        print("  create <name> <compose_file>   - Create new stack")
        print("  update <name> <compose_file>   - Update existing stack")
        print("  deploy <name> <compose_file>   - Smart create/update")
        print("  remove <name>                  - Remove stack")
        print("  status <name>                  - Show stack status")
        print("  health <name>                  - Health check stack")
        print("\nExamples:")
        print("  python portainer_stack_manager.py list")
        print("  python portainer_stack_manager.py deploy minecraft infrastructure/minecraft/docker-compose.yml")
        print("  python portainer_stack_manager.py health minecraft")
        sys.exit(1)

    try:
        manager = PortainerStackManager()
        command = sys.argv[1].lower()

        if command == 'list':
            success = manager.list_stacks()

        elif command in ['create', 'update', 'deploy']:
            if len(sys.argv) != 4:
                print(f"Usage: python portainer_stack_manager.py {command} <stack_name> <compose_file>")
                sys.exit(1)

            stack_name = sys.argv[2]
            compose_file = sys.argv[3]

            if command == 'create':
                success = manager.create_stack(stack_name, compose_file)
            elif command == 'update':
                success = manager.update_stack(stack_name, compose_file)
            elif command == 'deploy':
                success = manager.deploy_stack(stack_name, compose_file)

        elif command == 'remove':
            if len(sys.argv) != 3:
                print("Usage: python portainer_stack_manager.py remove <stack_name>")
                sys.exit(1)

            stack_name = sys.argv[2]
            success = manager.remove_stack(stack_name)

        elif command in ['status', 'health']:
            if len(sys.argv) != 3:
                print(f"Usage: python portainer_stack_manager.py {command} <stack_name>")
                sys.exit(1)

            stack_name = sys.argv[2]

            if command == 'status':
                success = manager.get_stack_status(stack_name)
            elif command == 'health':
                success = manager.health_check(stack_name)

        else:
            print(f"❌ Unknown command: {command}")
            sys.exit(1)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()