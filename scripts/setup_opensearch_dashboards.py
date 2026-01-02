#!/usr/bin/env python3
"""
OpenSearch Dashboards Setup Script

This script configures OpenSearch Dashboards with proper index patterns
and default settings for the homelab logging infrastructure.
"""

import subprocess
import json
import sys
from datetime import datetime

def ssh_command(command: str) -> str:
    """Execute command via SSH and return output"""
    ssh_cmd = f'ssh mcheli@192.168.1.179 "{command}"'
    try:
        result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"SSH command failed: {e}")
        print(f"Command: {command}")
        return ""

def opensearch_request(method: str, path: str, data: str = None) -> dict:
    """Make request to OpenSearch via SSH"""
    curl_cmd = f"docker exec opensearch curl -s -X {method} 'http://localhost:9200{path}'"
    if data:
        curl_cmd += f" -H 'Content-Type: application/json' -d '{data}'"

    result = ssh_command(curl_cmd)
    if not result:
        return {}

    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}")
        print(f"Raw response: {result}")
        return {}

def create_index_pattern():
    """Create the logs-homelab-* index pattern"""
    print("🔧 Creating index pattern: logs-homelab-*")

    timestamp = datetime.utcnow().isoformat() + "Z"

    index_pattern_data = {
        "type": "index-pattern",
        "migrationVersion": {
            "index-pattern": "7.6.0"
        },
        "updated_at": timestamp,
        "index-pattern": {
            "title": "logs-homelab-*",
            "timeFieldName": "@timestamp"
        }
    }

    data_json = json.dumps(index_pattern_data).replace('"', '\\"')
    result = opensearch_request("PUT", "/.opensearch-dashboards/_doc/index-pattern:logs-homelab-*", data_json)

    if result.get("result") in ["created", "updated"]:
        print("✅ Index pattern created successfully")
        return True
    else:
        print(f"❌ Failed to create index pattern: {result}")
        return False

def set_default_index():
    """Set logs-homelab-* as the default index pattern"""
    print("🎯 Setting default index pattern")

    config_data = {
        "type": "config",
        "config": {
            "defaultIndex": "logs-homelab-*",
            "buildNum": 99999
        }
    }

    data_json = json.dumps(config_data).replace('"', '\\"')
    result = opensearch_request("PUT", "/.opensearch-dashboards/_doc/config:2.11.1", data_json)

    if result.get("result") in ["created", "updated"]:
        print("✅ Default index pattern set successfully")
        return True
    else:
        print(f"❌ Failed to set default index: {result}")
        return False

def create_sample_data():
    """Create sample log data for testing"""
    print("📝 Adding sample log data")

    today = datetime.utcnow().strftime("%Y.%m.%d")
    timestamp = datetime.utcnow().isoformat() + "Z"

    sample_logs = [
        {
            "@timestamp": timestamp,
            "message": "OpenSearch Dashboards setup completed successfully",
            "container": {"name": "setup-script", "image": {"name": "python:setup"}},
            "level": "info",
            "service": "setup",
            "labels": {"environment": "homelab", "infrastructure": "83rr-poweredge"},
            "host": {"name": "poweredge-server"}
        },
        {
            "@timestamp": timestamp,
            "message": "Index pattern logs-homelab-* configured and ready for use",
            "container": {"name": "setup-script", "image": {"name": "python:setup"}},
            "level": "info",
            "service": "setup",
            "labels": {"environment": "homelab", "infrastructure": "83rr-poweredge"},
            "host": {"name": "poweredge-server"}
        }
    ]

    for i, log_entry in enumerate(sample_logs):
        data_json = json.dumps(log_entry).replace('"', '\\"')
        result = opensearch_request("POST", f"/logs-homelab-{today}/_doc", data_json)

        if result.get("result") == "created":
            print(f"✅ Sample log {i+1} added")
        else:
            print(f"❌ Failed to add sample log {i+1}: {result}")

def verify_setup():
    """Verify the setup was successful"""
    print("🔍 Verifying setup")

    # Check index pattern exists
    result = opensearch_request("GET", "/.opensearch-dashboards/_doc/index-pattern:logs-homelab-*")
    if result.get("found"):
        print("✅ Index pattern verified")
    else:
        print("❌ Index pattern not found")
        return False

    # Check log data exists
    result = opensearch_request("GET", "/logs-homelab-*/_count")
    count = result.get("count", 0)
    print(f"📊 Found {count} log entries")

    if count > 0:
        print("✅ Log data verified")
        return True
    else:
        print("❌ No log data found")
        return False

def main():
    print("🚀 Setting up OpenSearch Dashboards for Homelab Logs")
    print("=" * 60)

    try:
        # Create index pattern
        if not create_index_pattern():
            sys.exit(1)

        # Set as default
        if not set_default_index():
            sys.exit(1)

        # Add sample data
        create_sample_data()

        # Verify setup
        if verify_setup():
            print("\n🎉 OpenSearch Dashboards setup completed successfully!")
            print("📊 Dashboard URL: https://logs-local.ops.markcheli.com")
            print("🔍 Index pattern 'logs-homelab-*' is ready for log analysis")
        else:
            print("\n⚠️  Setup completed with warnings")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()