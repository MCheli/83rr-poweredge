#!/usr/bin/env python3
"""
Cloudflare SSL Permissions Guide
Helps user understand and configure proper API token permissions for Origin Certificates
"""

import os
import requests
from dotenv import load_dotenv

def check_ssl_permissions():
    """Check current token permissions and provide guidance"""
    load_dotenv()

    api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    base_url = 'https://api.cloudflare.com/client/v4'

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }

    print("🔐 Cloudflare SSL Certificate Permissions Check")
    print("=" * 60)

    # Test token verification to see what permissions we have
    print("\n🔍 Checking current token permissions...")

    try:
        response = requests.get(f"{base_url}/user/tokens/verify", headers=headers)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                token_info = result['result']
                print(f"✅ Token Status: {token_info.get('status', 'Unknown')}")

                # Show token policies if available
                if 'policies' in token_info:
                    print("\n📋 Current Token Permissions:")
                    for i, policy in enumerate(token_info['policies'], 1):
                        print(f"   {i}. Permission Group: {policy.get('effect', 'Unknown')}")
                        if 'resources' in policy:
                            for resource_type, resources in policy['resources'].items():
                                print(f"      {resource_type}: {len(resources) if isinstance(resources, list) else 'All'}")
                        if 'permission_groups' in policy:
                            for perm in policy['permission_groups']:
                                perm_name = perm.get('name', 'Unknown')
                                perm_id = perm.get('id', 'Unknown')
                                print(f"      - {perm_name} (ID: {perm_id})")
            else:
                print(f"❌ Token verification failed: {result.get('errors', 'Unknown')}")
    except Exception as e:
        print(f"❌ Error checking token: {str(e)}")

    # Test specific SSL-related endpoints
    print("\n🧪 Testing SSL-related API endpoints...")

    ssl_tests = [
        ("Origin Certificates (Create)", "POST", "/certificates", "❌ Requires Zone:SSL:Edit permission"),
        ("Origin Certificates (List)", "GET", "/certificates", "❌ Requires Zone:SSL:Edit permission"),
        ("Zone SSL Settings", "GET", "/zones/test/settings/ssl", "❌ Requires Zone:SSL:Read permission")
    ]

    for test_name, method, endpoint, expected_error in ssl_tests:
        print(f"\n   🔬 {test_name}")
        try:
            if method == "GET":
                # For GET requests, we can test without making actual changes
                if "zones/test" in endpoint:
                    # Get actual zone ID for testing
                    zone_response = requests.get(f"{base_url}/zones?name=markcheli.com", headers=headers)
                    if zone_response.status_code == 200:
                        zone_result = zone_response.json()
                        if zone_result['success'] and zone_result['result']:
                            zone_id = zone_result['result'][0]['id']
                            test_endpoint = endpoint.replace("zones/test", f"zones/{zone_id}")
                            response = requests.get(f"{base_url}{test_endpoint}", headers=headers)
                        else:
                            print(f"      ❌ Could not get zone ID")
                            continue
                    else:
                        print(f"      ❌ Could not get zone ID")
                        continue
                else:
                    response = requests.get(f"{base_url}{endpoint}", headers=headers)
            else:
                # For POST requests, test with minimal data
                test_data = {
                    "hostnames": ["test.markcheli.com"],
                    "request_type": "origin-rsa",
                    "requested_validity": 90
                }
                response = requests.post(f"{base_url}{endpoint}", headers=headers, json=test_data)

            print(f"      Status: {response.status_code}")

            if response.status_code == 200:
                print(f"      ✅ Permission granted - API accessible")
            elif response.status_code == 403:
                result = response.json()
                errors = result.get('errors', [])
                if any('unauthorized' in str(error).lower() for error in errors):
                    print(f"      ❌ Permission denied: {expected_error}")
                else:
                    print(f"      ❌ Other error: {errors}")
            else:
                try:
                    result = response.json()
                    errors = result.get('errors', [])
                    print(f"      ❌ HTTP {response.status_code}: {errors}")
                except:
                    print(f"      ❌ HTTP {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"      ❌ Error: {str(e)}")

    # Provide guidance for fixing permissions
    print(f"\n" + "=" * 60)
    print("🛠️  REQUIRED ACTION: Update API Token Permissions")
    print("=" * 60)
    print()
    print("Your current API token needs additional permissions for Origin Certificates.")
    print("Please follow these steps:")
    print()
    print("1. Go to: https://dash.cloudflare.com/profile/api-tokens")
    print("2. Find your current token and click 'Edit'")
    print("3. Add these permissions:")
    print("   • Zone:SSL:Edit (for creating/managing Origin Certificates)")
    print("   • Zone:SSL:Read (for reading SSL settings)")
    print()
    print("4. Current working permissions (keep these):")
    print("   • Zone:Zone:Read (for zone access)")
    print("   • Zone:DNS:Edit (for DNS management)")
    print()
    print("5. Save the token and test again:")
    print("   python scripts/cloudflare_ssl_manager.py create-wildcards")
    print()
    print("🔗 More info: https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/")

if __name__ == '__main__':
    check_ssl_permissions()