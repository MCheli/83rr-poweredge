#!/usr/bin/env python3
"""
Get detailed container status from Portainer API
Shows all containers with their status, images, ports, and resource usage
"""
import os
import json
import requests
import urllib3
from dotenv import load_dotenv

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_containers():
    load_dotenv()

    portainer_url = os.getenv('PORTAINER_URL')
    api_key = os.getenv('PORTAINER_API_KEY')
    endpoint_id = os.getenv('PORTAINER_ENDPOINT_ID', '3')

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        # Get all containers
        response = requests.get(
            f"{portainer_url}/api/endpoints/{endpoint_id}/docker/containers/json?all=true",
            headers=headers,
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            containers = response.json()

            print("🐳 Container Status Report")
            print("=" * 80)

            running_count = 0
            stopped_count = 0

            for container in containers:
                name = container['Names'][0].lstrip('/')
                image = container['Image']
                status = container['Status']
                state = container['State']

                if state == 'running':
                    status_icon = "✅"
                    running_count += 1
                elif state == 'restarting':
                    status_icon = "🔄"
                    running_count += 1
                elif state == 'exited':
                    status_icon = "❌"
                    stopped_count += 1
                else:
                    status_icon = "❓"

                print(f"{status_icon} {name}")
                print(f"   Image: {image}")
                print(f"   Status: {status}")

                # Get ports if available
                if container.get('Ports'):
                    ports = []
                    for port in container['Ports']:
                        if 'PublicPort' in port:
                            ports.append(f"{port.get('IP', '0.0.0.0')}:{port['PublicPort']}->{port['PrivatePort']}/{port['Type']}")
                        else:
                            ports.append(f"{port['PrivatePort']}/{port['Type']}")
                    if ports:
                        print(f"   Ports: {', '.join(ports)}")

                print()

            print("=" * 80)
            print(f"📊 Summary: {running_count} running, {stopped_count} stopped")

        else:
            print(f"❌ API Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    get_containers()