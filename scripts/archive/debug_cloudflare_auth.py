#!/usr/bin/env python3
"""
Debug Cloudflare Authentication
Test different API endpoints to diagnose permission issues
"""

import os
import requests
from dotenv import load_dotenv

def test_auth():
    """Test various Cloudflare API endpoints"""
    load_dotenv()

    api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    base_url = 'https://api.cloudflare.com/client/v4'

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }

    print("🔍 Cloudflare API Authentication Debug")
    print("=" * 60)

    tests = [
        ('Token Verification', '/user/tokens/verify'),
        ('User Info', '/user'),
        ('Zones List', '/zones'),
        ('Zone Details (markcheli.com)', '/zones?name=markcheli.com')
    ]

    for test_name, endpoint in tests:
        print(f"\n🔬 {test_name}")
        print(f"   Endpoint: {endpoint}")

        try:
            response = requests.get(f"{base_url}{endpoint}", headers=headers)
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    if 'result' in result:
                        if isinstance(result['result'], list):
                            print(f"   ✅ Success - {len(result['result'])} items")
                            if result['result']:
                                print(f"   📊 Sample: {list(result['result'][0].keys())[:3]}...")
                        else:
                            print(f"   ✅ Success - {type(result['result'])}")
                    else:
                        print(f"   ✅ Success")
                else:
                    print(f"   ❌ API Error: {result.get('errors', 'Unknown')}")
            else:
                try:
                    error_data = response.json()
                    print(f"   ❌ HTTP Error: {error_data}")
                except:
                    print(f"   ❌ HTTP Error: {response.text[:100]}...")

        except Exception as e:
            print(f"   ❌ Request Error: {str(e)}")

    # Test specific zone access
    print(f"\n🔬 Zone-Specific Access Test")
    try:
        response = requests.get(f"{base_url}/zones", headers=headers)
        if response.status_code == 200:
            result = response.json()
            if result.get('success') and result.get('result'):
                for zone in result['result']:
                    zone_name = zone['name']
                    zone_id = zone['id']
                    print(f"\n   🌍 Testing zone: {zone_name} (ID: {zone_id})")

                    # Test DNS records access
                    dns_response = requests.get(f"{base_url}/zones/{zone_id}/dns_records", headers=headers)
                    print(f"      DNS Records: {dns_response.status_code}")

                    if dns_response.status_code == 200:
                        dns_result = dns_response.json()
                        if dns_result.get('success'):
                            records = dns_result.get('result', [])
                            print(f"      ✅ Found {len(records)} DNS records")
                        else:
                            print(f"      ❌ DNS Error: {dns_result.get('errors', 'Unknown')}")
                    else:
                        try:
                            error_data = dns_response.json()
                            print(f"      ❌ DNS HTTP Error: {error_data}")
                        except:
                            print(f"      ❌ DNS HTTP Error: {dns_response.text[:50]}...")
            else:
                print(f"   ❌ Could not list zones")
    except Exception as e:
        print(f"   ❌ Zone test failed: {str(e)}")

if __name__ == '__main__':
    test_auth()