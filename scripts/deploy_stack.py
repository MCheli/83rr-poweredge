#!/usr/bin/env python3
"""
Deploy stack configuration to Portainer
Updates an existing stack with new docker-compose content
"""
import os
import json
import requests
import urllib3
from dotenv import load_dotenv
from pathlib import Path

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def deploy_stack(stack_name, compose_file_path):
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

    # Read the compose file
    compose_file = Path(compose_file_path)
    if not compose_file.exists():
        print(f"❌ Compose file not found: {compose_file_path}")
        return False

    with open(compose_file, 'r') as f:
        compose_content = f.read()

    print(f"🚀 Deploying stack: {stack_name}")
    print("=" * 50)

    try:
        # Get existing stack
        response = requests.get(
            f"{portainer_url}/api/stacks",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code != 200:
            print(f"❌ Failed to fetch stacks: {response.status_code}")
            return False

        stacks = response.json()
        target_stack = None

        for stack in stacks:
            if stack['Name'] == stack_name:
                target_stack = stack
                break

        if not target_stack:
            print(f"❌ Stack '{stack_name}' not found in Portainer")
            return False

        stack_id = target_stack['Id']
        endpoint_id = target_stack['EndpointId']

        print(f"📋 Found stack: {stack_name} (ID: {stack_id})")

        # Update stack
        update_payload = {
            "StackFileContent": compose_content,
            "Env": []  # Keep existing environment variables
        }

        print(f"🔄 Updating stack with {len(compose_content)} characters of compose content...")

        response = requests.put(
            f"{portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}",
            headers=headers,
            json=update_payload,
            verify=False,
            timeout=60
        )

        if response.status_code == 200:
            print("✅ Stack updated successfully!")
            result = response.json()
            print(f"   Stack ID: {result.get('Id', stack_id)}")
            print(f"   Endpoint: {result.get('EndpointId', endpoint_id)}")
            return True
        else:
            print(f"❌ Failed to update stack: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python deploy_stack.py <stack_name> <compose_file_path>")
        print("Example: python deploy_stack.py traefik infrastructure/traefik/docker-compose.yml")
        sys.exit(1)

    stack_name = sys.argv[1]
    compose_file = sys.argv[2]

    success = deploy_stack(stack_name, compose_file)
    sys.exit(0 if success else 1)