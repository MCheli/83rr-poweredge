#!/usr/bin/env python3
"""
Quick Service Availability Test

Test basic service endpoints to see what's running
"""

import requests
import urllib3
from dotenv import load_dotenv

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_endpoints():
    """Test basic service endpoints"""
    load_dotenv()

    endpoints = {
        # Public services
        "Personal Website": "https://www.markcheli.com",
        "Flask API": "https://flask.markcheli.com/health",
        "JupyterHub": "https://jupyter.markcheli.com",

        # LAN services
        "Portainer": "https://portainer-local.ops.markcheli.com",
        "Traefik": "https://traefik-local.ops.markcheli.com",
        "OpenSearch": "https://logs-local.ops.markcheli.com",
        "Dev Website": "https://www-dev.ops.markcheli.com",
        "Dev Flask API": "https://flask-dev.ops.markcheli.com/health",
    }

    print("🔍 Quick Service Availability Test")
    print("=" * 60)

    for name, url in endpoints.items():
        try:
            response = requests.get(url, verify=False, timeout=10)
            status = "✅ ONLINE" if response.status_code < 400 else f"⚠️  HTTP {response.status_code}"
            print(f"{name:20} - {status}")
        except requests.exceptions.RequestException as e:
            print(f"{name:20} - ❌ OFFLINE ({type(e).__name__})")

    print("\n🐳 Checking Minecraft Server")
    print("=" * 60)
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('minecraft.markcheli.com', 25565))
        if result == 0:
            print("Minecraft Server      - ✅ ONLINE")
        else:
            print("Minecraft Server      - ❌ OFFLINE")
        sock.close()
    except Exception as e:
        print(f"Minecraft Server      - ❌ ERROR ({str(e)})")

if __name__ == "__main__":
    test_endpoints()