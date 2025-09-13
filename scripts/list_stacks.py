#!/usr/bin/env python3
"""
List all stacks managed by Portainer with detailed information
Shows stack status, creation/update dates, and service counts
"""
import os
import json
import requests
import urllib3
from dotenv import load_dotenv
from datetime import datetime

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def list_stacks():
    load_dotenv()

    portainer_url = os.getenv('PORTAINER_URL')
    api_key = os.getenv('PORTAINER_API_KEY')

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        # Get all stacks
        response = requests.get(
            f"{portainer_url}/api/stacks",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            stacks = response.json()

            print("📚 Portainer Stack Management Report")
            print("=" * 80)

            if not stacks:
                print("No stacks found.")
                return

            for stack in stacks:
                name = stack.get('Name', 'Unknown')
                stack_id = stack.get('Id', 'N/A')
                status = stack.get('Status', 'Unknown')
                endpoint_id = stack.get('EndpointId', 'N/A')

                # Convert timestamp to readable format
                creation_date = stack.get('CreationDate', 0)
                if creation_date:
                    created = datetime.fromtimestamp(creation_date).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    created = 'Unknown'

                update_date = stack.get('UpdateDate', 0)
                if update_date:
                    updated = datetime.fromtimestamp(update_date).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    updated = 'Never'

                # Status icon
                status_icon = "✅" if status == 1 else "❌" if status == 2 else "❓"

                print(f"{status_icon} **{name}** (ID: {stack_id})")
                print(f"   Status: {'Active' if status == 1 else 'Inactive' if status == 2 else 'Unknown'}")
                print(f"   Endpoint: {endpoint_id}")
                print(f"   Created: {created}")
                print(f"   Updated: {updated}")

                # Get stack file content if available
                try:
                    file_response = requests.get(
                        f"{portainer_url}/api/stacks/{stack_id}/file",
                        headers=headers,
                        verify=False,
                        timeout=5
                    )
                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        if 'StackFileContent' in file_data:
                            # Count services in compose file
                            content = file_data['StackFileContent']
                            service_count = content.count('image:') if content else 0
                            print(f"   Services: ~{service_count} containers")
                except:
                    pass

                print()

            print("=" * 80)
            print(f"📊 Total Stacks: {len(stacks)}")

        else:
            print(f"❌ API Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    list_stacks()