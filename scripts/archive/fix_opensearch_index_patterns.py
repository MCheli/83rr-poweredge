#!/usr/bin/env python3
"""
Fix OpenSearch Dashboards Index Patterns

This script fixes the common issue where index patterns don't appear
in OpenSearch Dashboards by using the proper saved objects API.
"""

import requests
import json
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_index_pattern():
    """Create the logs-homelab-* index pattern via the saved objects API"""

    url = "https://logs-local.ops.markcheli.com/api/saved_objects/index-pattern"
    headers = {
        'Content-Type': 'application/json',
        'osd-xsrf': 'true'
    }

    data = {
        "attributes": {
            "title": "logs-homelab-*",
            "timeFieldName": "@timestamp"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data, verify=False)

        if response.status_code == 200:
            result = response.json()
            index_pattern_id = result.get('id')
            print(f"✅ Index pattern created successfully: {index_pattern_id}")
            return index_pattern_id
        elif response.status_code == 409:
            print("ℹ️  Index pattern already exists")
            # Try to get existing pattern
            list_url = "https://logs-local.ops.markcheli.com/api/saved_objects/_find?type=index-pattern"
            list_response = requests.get(list_url, headers=headers, verify=False)
            if list_response.status_code == 200:
                patterns = list_response.json().get('saved_objects', [])
                for pattern in patterns:
                    if pattern.get('attributes', {}).get('title') == 'logs-homelab-*':
                        return pattern.get('id')
            return None
        else:
            print(f"❌ Failed to create index pattern: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error creating index pattern: {e}")
        return None

def set_default_index_pattern(pattern_id):
    """Set the index pattern as default"""

    if not pattern_id:
        print("❌ No pattern ID provided")
        return False

    url = "https://logs-local.ops.markcheli.com/api/saved_objects/config/3.2.0"
    headers = {
        'Content-Type': 'application/json',
        'osd-xsrf': 'true'
    }

    data = {
        "attributes": {
            "defaultIndex": pattern_id
        }
    }

    try:
        # Try PUT first (update existing)
        response = requests.put(url, headers=headers, json=data, verify=False)

        if response.status_code == 200:
            print("✅ Default index pattern set successfully")
            return True
        else:
            # Try POST (create new)
            response = requests.post(url, headers=headers, json=data, verify=False)
            if response.status_code == 200:
                print("✅ Default index pattern created successfully")
                return True
            else:
                print(f"❌ Failed to set default index pattern: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        print(f"❌ Error setting default index pattern: {e}")
        return False

def add_test_data():
    """Add test log data to ensure there's something to see"""
    try:
        import subprocess
        result = subprocess.run([
            'python', 'scripts/opensearch_diagnostic_ssh.py', 'test-log'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Test log data added")
        else:
            print(f"⚠️  Could not add test data: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Could not add test data: {e}")

def main():
    print("🔧 Fixing OpenSearch Dashboards Index Patterns")
    print("=" * 50)

    # Create index pattern
    pattern_id = create_index_pattern()

    if pattern_id:
        # Set as default
        set_default_index_pattern(pattern_id)

        # Add test data
        add_test_data()

        print("\n🎉 Setup complete!")
        print("📊 Go to: https://logs-local.ops.markcheli.com")
        print("🔍 Navigate to 'Discover' to view your logs")
        print("📈 The 'logs-homelab-*' index pattern should now be visible")

    else:
        print("\n❌ Failed to create index pattern")
        print("Check OpenSearch Dashboards connectivity and try again")

if __name__ == "__main__":
    main()