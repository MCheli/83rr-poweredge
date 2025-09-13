#!/usr/bin/env python3
"""
Create a new stack in Portainer using the API
"""
import os
import json
import requests
import urllib3
from dotenv import load_dotenv
from pathlib import Path

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_stack(stack_name, compose_file_path):
    load_dotenv()

    portainer_url = os.getenv('PORTAINER_URL')
    api_key = os.getenv('PORTAINER_API_KEY')
    endpoint_id = os.getenv('PORTAINER_ENDPOINT_ID', '3')

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

    print(f"🚀 Creating new stack: {stack_name}")
    print("=" * 50)

    try:
        # Check if stack already exists
        response = requests.get(
            f"{portainer_url}/api/stacks",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            stacks = response.json()
            for stack in stacks:
                if stack['Name'] == stack_name:
                    print(f"❌ Stack '{stack_name}' already exists")
                    return False

        # Create new stack
        create_payload = {
            "Name": stack_name,
            "StackFileContent": compose_content,
            "Env": []
        }

        print(f"📝 Creating stack with {len(compose_content)} characters of compose content...")

        response = requests.post(
            f"{portainer_url}/api/stacks?type=2&method=string&endpointId={endpoint_id}",
            headers=headers,
            json=create_payload,
            verify=False,
            timeout=120
        )

        if response.status_code == 200:
            print("✅ Stack created successfully!")
            result = response.json()
            print(f"   Stack ID: {result.get('Id')}")
            print(f"   Stack Name: {result.get('Name')}")
            print(f"   Endpoint: {result.get('EndpointId')}")
            return True
        else:
            print(f"❌ Failed to create stack: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python create_stack.py <stack_name> <compose_file_path>")
        print("Example: python create_stack.py minecraft infrastructure/minecraft/docker-compose.yml")
        sys.exit(1)

    stack_name = sys.argv[1]
    compose_file = sys.argv[2]

    success = create_stack(stack_name, compose_file)
    sys.exit(0 if success else 1)