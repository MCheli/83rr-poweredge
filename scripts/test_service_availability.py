#!/usr/bin/env python3
"""
Critical Service Availability Test

MANDATORY: This test must pass 100% before any git commits.
All public services must return expected HTTP status codes.
Any failures indicate broken infrastructure that must be fixed.
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test timeout settings
TIMEOUT = 10
MAX_RETRIES = 2

def test_service(name, url, expected_status=200, expected_content=None, description=""):
    """Test a single service endpoint"""
    print(f"\n🔍 Testing {name}")
    print(f"   URL: {url}")
    print(f"   Expected: HTTP {expected_status}")
    if description:
        print(f"   Description: {description}")

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=TIMEOUT, verify=True, allow_redirects=False)

            # Check status code
            if response.status_code == expected_status:
                status_result = "✅ PASS"
            else:
                status_result = f"❌ FAIL - Got HTTP {response.status_code}"

            # Check content if specified
            content_result = ""
            if expected_content and response.status_code in [200, 302]:
                if expected_content.lower() in response.text.lower():
                    content_result = " | Content: ✅"
                else:
                    content_result = f" | Content: ❌ (missing '{expected_content}')"

            # Show timing
            timing = f" | Response: {response.elapsed.total_seconds():.2f}s"

            print(f"   Result: {status_result}{content_result}{timing}")

            # Return success/failure
            if response.status_code == expected_status:
                if expected_content:
                    return expected_content.lower() in response.text.lower()
                return True

            # If this was not the last attempt, wait and retry
            if attempt < MAX_RETRIES:
                print(f"   Retrying in 5 seconds... (attempt {attempt + 2}/{MAX_RETRIES + 1})")
                time.sleep(5)
                continue

            return False

        except requests.exceptions.Timeout:
            print(f"   Result: ❌ FAIL - Timeout ({TIMEOUT}s)")
            if attempt < MAX_RETRIES:
                print(f"   Retrying in 5 seconds... (attempt {attempt + 2}/{MAX_RETRIES + 1})")
                time.sleep(5)
                continue
            return False

        except requests.exceptions.ConnectionError as e:
            print(f"   Result: ❌ FAIL - Connection error: {str(e)}")
            if attempt < MAX_RETRIES:
                print(f"   Retrying in 5 seconds... (attempt {attempt + 2}/{MAX_RETRIES + 1})")
                time.sleep(5)
                continue
            return False

        except Exception as e:
            print(f"   Result: ❌ FAIL - Error: {str(e)}")
            if attempt < MAX_RETRIES:
                print(f"   Retrying in 5 seconds... (attempt {attempt + 2}/{MAX_RETRIES + 1})")
                time.sleep(5)
                continue
            return False

    return False

def main():
    print("🏥 CRITICAL SERVICE AVAILABILITY TEST")
    print("=" * 50)
    print("MANDATORY: All services must pass before git commits")
    print("=" * 50)

    # Define all critical services
    services = [
        {
            "name": "JupyterHub",
            "url": "https://jupyter.markcheli.com",
            "expected_status": 302,  # JupyterHub redirects to login
            "description": "Data science environment - should redirect to login"
        },
        {
            "name": "Personal Website",
            "url": "https://www.markcheli.com",
            "expected_status": 200,
            "expected_content": "terminal",  # Website has terminal interface
            "description": "Main personal website - terminal interface"
        },
        {
            "name": "Flask API Health",
            "url": "https://flask.markcheli.com/health",
            "expected_status": 200,
            "expected_content": "status",  # Health endpoint returns status
            "description": "API health endpoint - should return status"
        },
        {
            "name": "Base Domain",
            "url": "https://ops.markcheli.com",
            "expected_status": 200,
            "expected_content": "hostname",  # Whoami service
            "description": "Base domain whoami service"
        }
    ]

    # Test all services
    results = []
    for service in services:
        success = test_service(
            service["name"],
            service["url"],
            service["expected_status"],
            service.get("expected_content"),
            service.get("description", "")
        )
        results.append({
            "name": service["name"],
            "success": success,
            "url": service["url"]
        })

    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)

    passed = sum(1 for r in results if r["success"])
    failed = len(results) - passed

    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status} - {result['name']}")

    print("-" * 50)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")

    if failed > 0:
        print("\n🚨 CRITICAL FAILURE: Some services are not available!")
        print("❌ DO NOT COMMIT until all services pass")
        print("\nFailed services:")
        for result in results:
            if not result["success"]:
                print(f"   • {result['name']}: {result['url']}")

        print("\nTroubleshooting steps:")
        print("1. Check container status: docker ps")
        print("2. Check service logs: docker logs <container_name>")
        print("3. Verify DNS resolution: dig <domain>")
        print("4. Test SSL certificates: curl -I <url>")
        print("5. Check Traefik routing: curl localhost:8080/api/http/routers")

        sys.exit(1)
    else:
        print("\n✅ ALL SERVICES AVAILABLE")
        print("✅ Ready for git commit")
        sys.exit(0)

if __name__ == "__main__":
    main()