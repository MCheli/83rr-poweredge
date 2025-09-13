#!/usr/bin/env python3
"""
Standalone connectivity test script for homelab infrastructure
Usage: source venv/bin/activate && python scripts/test_connectivity.py
"""
import os
import sys
import subprocess
import requests
import urllib3
from dotenv import load_dotenv

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_connectivity():
    """Test connectivity to both Portainer API and SSH"""
    # Load environment variables
    load_dotenv()

    portainer_url = os.getenv('PORTAINER_URL')
    api_key = os.getenv('PORTAINER_API_KEY')
    ssh_host = os.getenv('SSH_HOST')
    ssh_user = os.getenv('SSH_USER')

    # Validate required environment variables
    if not all([portainer_url, api_key, ssh_host, ssh_user]):
        print("❌ Missing required environment variables!")
        print("Please ensure your .env file contains:")
        print("  - PORTAINER_URL")
        print("  - PORTAINER_API_KEY")
        print("  - SSH_HOST")
        print("  - SSH_USER")
        return False

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    print("🔍 Testing connectivity...")
    print(f"SSH Host: {ssh_user}@{ssh_host}")
    print(f"Portainer: {portainer_url}")
    print("-" * 50)

    # Test SSH
    ssh_cmd = f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no {ssh_user}@{ssh_host} 'echo SSH_OK'"
    try:
        result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "SSH_OK" in result.stdout:
            print("✅ SSH connection successful")
            ssh_success = True
        else:
            print(f"❌ SSH connection failed")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            ssh_success = False
    except subprocess.TimeoutExpired:
        print("❌ SSH connection timed out after 10 seconds")
        ssh_success = False
    except Exception as e:
        print(f"❌ SSH connection failed: {str(e)}")
        ssh_success = False

    # Test Portainer API
    try:
        print("Testing Portainer API...")
        response = requests.get(
            f"{portainer_url}/api/stacks",
            headers=headers,
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            stacks = response.json()
            print("✅ Portainer API connection successful")
            print(f"   Found {len(stacks)} existing stacks")

            # List stack names
            if stacks:
                stack_names = [stack.get('Name', 'Unknown') for stack in stacks]
                print(f"   Stacks: {', '.join(stack_names)}")

            portainer_success = True
        else:
            print(f"❌ Portainer API error: HTTP {response.status_code}")
            if response.text:
                print(f"   Response: {response.text[:200]}")
            portainer_success = False
    except requests.exceptions.Timeout:
        print("❌ Portainer API connection timed out")
        portainer_success = False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Portainer API connection failed: Unable to connect")
        print(f"   Check if {portainer_url} is accessible")
        portainer_success = False
    except Exception as e:
        print(f"❌ Portainer API connection failed: {str(e)}")
        portainer_success = False

    print("-" * 50)
    if ssh_success and portainer_success:
        print("🎉 All connectivity tests passed!")
        return True
    else:
        print("❌ Some connectivity tests failed")
        return False

if __name__ == "__main__":
    success = test_connectivity()
    sys.exit(0 if success else 1)