#!/usr/bin/env python3
"""
Test hello-world container deployment and DNS resolution
Enhanced with infrastructure DNS integration
"""
import subprocess
import requests
import urllib3
from datetime import datetime
import sys
import os

# Add scripts directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from infrastructure_dns import InfrastructureDNS

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_hello_world():
    print("🧪 Testing Hello World Deployment")
    print("=" * 50)

    # Use infrastructure DNS manager
    infra = InfrastructureDNS()

    # Comprehensive test using infrastructure DNS
    print("Using infrastructure DNS verification...")
    success = infra.verify_deployment('hello')

    if not success:
        print("\n📋 DNS Setup Instructions:")
        infra.setup_service_dns('hello')

        print("\n📝 Complete Deployment Checklist:")
        infra.generate_deployment_checklist('hello')

    return success

if __name__ == "__main__":
    success = test_hello_world()
    if success:
        print("\n🎉 Hello World deployment test PASSED!")
    else:
        print("\n❌ Hello World deployment test FAILED")
        print("\nNext steps:")
        print("1. Add DNS A record: hello.ops.markcheli.com → 173.48.98.211")
        print("2. Wait 5-15 minutes for DNS propagation")
        print("3. Run this test again: python scripts/test_hello_world.py")

    exit(0 if success else 1)