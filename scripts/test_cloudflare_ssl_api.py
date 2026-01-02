#!/usr/bin/env python3
"""
Test Cloudflare SSL API directly with minimal data
"""

import os
import json
import requests
from dotenv import load_dotenv
from test_csr_generation import test_csr_generation

def test_ssl_api():
    """Test SSL API with minimal, validated CSR"""
    load_dotenv()

    api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    base_url = 'https://api.cloudflare.com/client/v4'

    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }

    print("🧪 Testing Cloudflare SSL API")
    print("=" * 40)

    # Generate a valid CSR
    print("🔑 Generating test CSR...")
    csr_pem = test_csr_generation()
    if not csr_pem:
        print("❌ CSR generation failed")
        return

    print("\n📤 Testing SSL API with minimal data...")

    # Test with absolute minimal data
    test_data = {
        "hostnames": ["markcheli.com"],
        "request_type": "origin-rsa",
        "csr": csr_pem
    }

    print(f"📊 Request size: {len(json.dumps(test_data))} bytes")
    print(f"📊 CSR size: {len(csr_pem)} characters")

    try:
        response = requests.post(
            f"{base_url}/certificates",
            headers=headers,
            json=test_data,
            timeout=30
        )

        print(f"\n📥 Response:")
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")

        try:
            result = response.json()
            print(f"   Success: {result.get('success', 'N/A')}")

            if result.get('success'):
                print("✅ Certificate created successfully!")
                cert_data = result.get('result', {})
                cert_id = cert_data.get('id')
                print(f"   Certificate ID: {cert_id}")

                # Clean up test certificate
                if cert_id:
                    print(f"\n🗑️ Cleaning up test certificate...")
                    delete_response = requests.delete(
                        f"{base_url}/certificates/{cert_id}",
                        headers=headers
                    )
                    print(f"   Delete status: {delete_response.status_code}")

            else:
                print("❌ API Error:")
                errors = result.get('errors', [])
                for error in errors:
                    error_code = error.get('code', 'N/A')
                    error_msg = error.get('message', 'N/A')
                    print(f"      Code {error_code}: {error_msg}")

                # Additional debug info
                if 'messages' in result:
                    print(f"   Messages: {result['messages']}")

        except json.JSONDecodeError:
            print(f"   ❌ Invalid JSON response")
            print(f"   Raw response: {response.text[:500]}")

    except requests.RequestException as e:
        print(f"❌ Request error: {str(e)}")

    print(f"\n" + "=" * 40)
    print("🔍 Additional API Tests")
    print("=" * 40)

    # Test listing certificates with zone ID
    print("\n📋 Testing certificate listing...")
    try:
        # Get zone ID
        zone_response = requests.get(f"{base_url}/zones?name=markcheli.com", headers=headers)
        if zone_response.status_code == 200:
            zone_result = zone_response.json()
            if zone_result['success'] and zone_result['result']:
                zone_id = zone_result['result'][0]['id']
                print(f"✅ Zone ID: {zone_id}")

                # Test listing with zone ID
                list_response = requests.get(f"{base_url}/certificates?zone_id={zone_id}", headers=headers)
                print(f"📋 List certificates status: {list_response.status_code}")

                if list_response.status_code == 200:
                    list_result = list_response.json()
                    if list_result.get('success'):
                        certs = list_result.get('result', [])
                        print(f"✅ Found {len(certs)} existing certificates")
                    else:
                        print(f"❌ List error: {list_result.get('errors', 'Unknown')}")
                else:
                    print(f"❌ List failed: {list_response.text[:200]}")

    except Exception as e:
        print(f"❌ Zone/list error: {str(e)}")

if __name__ == '__main__':
    test_ssl_api()