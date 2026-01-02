#!/usr/bin/env python3
"""
Test SSL Certificate Creation
Debug the exact API requirements for Origin Certificates
"""

import os
import requests
from dotenv import load_dotenv

def test_ssl_creation():
    """Test Origin Certificate creation with minimal data"""
    load_dotenv()

    api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    base_url = 'https://api.cloudflare.com/client/v4'

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }

    print("🔐 Testing Origin Certificate Creation")
    print("=" * 50)

    # Get zone ID first
    print("\n🔍 Getting zone ID...")
    zone_response = requests.get(f"{base_url}/zones?name=markcheli.com", headers=headers)
    if zone_response.status_code != 200:
        print("❌ Failed to get zone")
        return

    zone_result = zone_response.json()
    if not zone_result['success'] or not zone_result['result']:
        print("❌ No zone found")
        return

    zone_id = zone_result['result'][0]['id']
    print(f"✅ Zone ID: {zone_id}")

    # Test different certificate creation approaches
    test_configs = [
        {
            'name': 'Minimal RSA',
            'data': {
                'hostnames': ['markcheli.com'],
                'request_type': 'origin-rsa',
                'requested_validity': 5475
            }
        },
        {
            'name': 'No request_type',
            'data': {
                'hostnames': ['markcheli.com'],
                'requested_validity': 5475
            }
        },
        {
            'name': 'Default values',
            'data': {
                'hostnames': ['markcheli.com']
            }
        }
    ]

    for config in test_configs:
        print(f"\n🧪 Testing: {config['name']}")
        print(f"   Data: {config['data']}")

        try:
            response = requests.post(f"{base_url}/certificates", headers=headers, json=config['data'])
            print(f"   Status: {response.status_code}")

            result = response.json()
            if response.status_code == 200 and result.get('success'):
                print(f"   ✅ Success! Certificate ID: {result['result']['id']}")
                # Clean up - delete the test certificate
                cert_id = result['result']['id']
                delete_response = requests.delete(f"{base_url}/certificates/{cert_id}", headers=headers)
                print(f"   🗑️ Cleanup: {delete_response.status_code}")
                break
            else:
                print(f"   ❌ Failed: {result.get('errors', 'Unknown error')}")
                if 'messages' in result:
                    print(f"   📝 Messages: {result['messages']}")

        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")

if __name__ == '__main__':
    test_ssl_creation()