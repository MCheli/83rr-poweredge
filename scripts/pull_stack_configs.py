#!/usr/bin/env python3
"""
Pull docker-compose configurations from Portainer stacks and save locally
Downloads all stack configurations to infrastructure/ directory with metadata
"""
import os
import json
import yaml
import requests
import urllib3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def pull_stack_configs():
    load_dotenv()

    portainer_url = os.getenv('PORTAINER_URL')
    api_key = os.getenv('PORTAINER_API_KEY')

    if not all([portainer_url, api_key]):
        print("❌ Missing required environment variables (PORTAINER_URL, PORTAINER_API_KEY)")
        return False

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    # Create infrastructure directory
    infra_dir = Path("infrastructure")
    infra_dir.mkdir(exist_ok=True)

    print("📥 Pulling Stack Configurations from Portainer")
    print("=" * 60)

    try:
        # Get all stacks
        response = requests.get(
            f"{portainer_url}/api/stacks",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code != 200:
            print(f"❌ Failed to fetch stacks: {response.status_code}")
            print(response.text)
            return False

        stacks = response.json()
        if not stacks:
            print("No stacks found in Portainer")
            return True

        success_count = 0
        total_stacks = len(stacks)

        for stack in stacks:
            stack_name = stack.get('Name', 'unknown')
            stack_id = stack.get('Id')

            print(f"📋 Processing stack: {stack_name} (ID: {stack_id})")

            try:
                # Get stack file content
                file_response = requests.get(
                    f"{portainer_url}/api/stacks/{stack_id}/file",
                    headers=headers,
                    verify=False,
                    timeout=10
                )

                if file_response.status_code == 200:
                    file_data = file_response.json()
                    compose_content = file_data.get('StackFileContent', '')

                    if compose_content:
                        # Create stack directory
                        stack_dir = infra_dir / stack_name
                        stack_dir.mkdir(exist_ok=True)

                        # Save docker-compose.yml
                        compose_file = stack_dir / "docker-compose.yml"
                        with open(compose_file, 'w') as f:
                            f.write(compose_content)

                        # Save stack metadata
                        metadata = {
                            'stack_name': stack_name,
                            'stack_id': stack_id,
                            'status': 'Active' if stack.get('Status') == 1 else 'Inactive',
                            'endpoint_id': stack.get('EndpointId'),
                            'creation_date': datetime.fromtimestamp(stack.get('CreationDate', 0)).isoformat() if stack.get('CreationDate') else None,
                            'update_date': datetime.fromtimestamp(stack.get('UpdateDate', 0)).isoformat() if stack.get('UpdateDate') else None,
                            'pulled_at': datetime.now().isoformat(),
                            'portainer_url': portainer_url
                        }

                        metadata_file = stack_dir / "stack-metadata.json"
                        with open(metadata_file, 'w') as f:
                            json.dump(metadata, f, indent=2)

                        # Try to parse and validate YAML
                        try:
                            parsed_yaml = yaml.safe_load(compose_content)
                            services = list(parsed_yaml.get('services', {}).keys()) if parsed_yaml else []

                            print(f"   ✅ Saved to infrastructure/{stack_name}/")
                            print(f"   📄 docker-compose.yml ({len(compose_content.splitlines())} lines)")
                            print(f"   📋 stack-metadata.json")
                            if services:
                                print(f"   🐳 Services: {', '.join(services)}")

                        except yaml.YAMLError as e:
                            print(f"   ⚠️  YAML parsing warning: {e}")
                            print(f"   ✅ Files saved anyway")

                        success_count += 1

                    else:
                        print(f"   ❌ No compose content found for {stack_name}")

                else:
                    print(f"   ❌ Failed to fetch file content: {file_response.status_code}")
                    print(f"   Response: {file_response.text[:100]}")

            except Exception as e:
                print(f"   ❌ Error processing {stack_name}: {str(e)}")

            print()

        print("=" * 60)
        print(f"📊 Summary: {success_count}/{total_stacks} stacks pulled successfully")

        if success_count > 0:
            print(f"📁 Configurations saved to: {infra_dir.absolute()}")
            print("\nDirectory structure:")
            for item in sorted(infra_dir.iterdir()):
                if item.is_dir():
                    print(f"  infrastructure/{item.name}/")
                    for subitem in sorted(item.iterdir()):
                        print(f"    ├── {subitem.name}")

        return success_count == total_stacks

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = pull_stack_configs()
    exit(0 if success else 1)