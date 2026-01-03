#!/usr/bin/env python3
"""
OpenSearch Diagnostic Tool for 83RR PowerEdge Infrastructure

This script provides comprehensive container log analysis and infrastructure
diagnostics by accessing OpenSearch API directly (no SSH required).

Usage:
    python scripts/opensearch_diagnostic.py [command] [options]

Commands:
    recent          - Show recent logs from all containers
    container NAME  - Show logs for specific container
    errors          - Show error logs across all containers
    search QUERY    - Search logs with custom query
    health          - Check OpenSearch cluster health
    indices         - List all log indices
    test-log        - Add a test log entry

Options:
    --hours N       - Limit to last N hours (default: 1)
    --lines N       - Show N lines (default: 50)
    --json          - Output raw JSON
"""

import subprocess
import json
import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class OpenSearchDiagnostic:
    def __init__(self):
        pass

    def _run_command(self, command: str) -> str:
        """Execute command locally and return output"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e}")
            print(f"Command: {command}")
            print(f"Error output: {e.stderr}")
            return ""

    def _opensearch_request(self, method: str, path: str, data: Dict = None) -> Dict:
        """Make request to OpenSearch via docker exec"""
        if data:
            # Write JSON to temp file to avoid escaping issues
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f)
                temp_file = f.name

            # Copy temp file into container and use it
            copy_cmd = f"docker cp {temp_file} opensearch:/tmp/request.json"
            self._run_command(copy_cmd)

            curl_cmd = f"docker exec opensearch curl -s -X {method} 'http://localhost:9200{path}' -H 'Content-Type: application/json' -d @/tmp/request.json"

            result = self._run_command(curl_cmd)

            # Cleanup
            import os
            os.unlink(temp_file)
            self._run_command("docker exec opensearch rm /tmp/request.json")
        else:
            curl_cmd = f"docker exec opensearch curl -s -X {method} 'http://localhost:9200{path}'"
            result = self._run_command(curl_cmd)

        if not result:
            return {}

        try:
            return json.loads(result)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw response: {result}")
            return {}

    def health_check(self) -> Dict:
        """Check OpenSearch cluster health"""
        return self._opensearch_request("GET", "/_cluster/health")

    def list_indices(self) -> List[Dict]:
        """List all log indices in OpenSearch"""
        result = self._opensearch_request("GET", "/_cat/indices/logs*?format=json")
        return result if isinstance(result, list) else []

    def search_logs(self, query: Dict, index_pattern: str = "logs-homelab*") -> Dict:
        """Search logs with given query"""
        return self._opensearch_request("POST", f"/{index_pattern}/_search", query)

    def add_test_log(self):
        """Add a test log entry to verify ingestion"""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        today = now.strftime("%Y.%m.%d")

        test_log = {
            "@timestamp": timestamp,
            "message": f"Test log entry from diagnostic tool at {timestamp}",
            "container": {
                "name": "diagnostic-tool",
                "id": "test-diagnostic",
                "image": {
                    "name": "python:diagnostic"
                }
            },
            "labels": {
                "environment": "homelab",
                "infrastructure": "83rr-poweredge"
            },
            "host": {
                "hostname": "83rr-poweredge"
            },
            "level": "info",
            "service": "diagnostic",
            "test": True
        }

        index_name = f"logs-homelab-{today}"
        result = self._opensearch_request("POST", f"/{index_name}/_doc", test_log)

        if result.get("result") == "created":
            print(f"✅ Test log entry added to index: {index_name}")
            print(f"   Document ID: {result.get('_id')}")
            return True
        else:
            print(f"❌ Failed to add test log entry")
            print(f"   Response: {result}")
            return False

    def get_recent_logs(self, hours: int = 1, lines: int = 50, container: str = None):
        """Get recent logs from all containers or specific container"""
        # Calculate time range
        now = datetime.utcnow()
        start_time = now - timedelta(hours=hours)

        query = {
            "size": lines,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": start_time.isoformat() + "Z",
                                    "lte": now.isoformat() + "Z"
                                }
                            }
                        }
                    ]
                }
            }
        }

        # Add container filter if specified
        if container:
            query["query"]["bool"]["must"].append({
                "match": {"container.name": container}
            })

        result = self.search_logs(query)

        if not result or "hits" not in result:
            print(f"No logs found in the last {hours} hour(s)")
            return

        hits = result["hits"]["hits"]
        total = result["hits"]["total"]["value"]

        print(f"📝 Found {total} logs in the last {hours} hour(s), showing {len(hits)}:")
        print("=" * 80)

        for hit in hits:
            source = hit["_source"]
            timestamp = source.get("@timestamp", "Unknown time")
            container_name = source.get("container", {}).get("name", "Unknown")
            message = source.get("message", "No message")
            level = source.get("level", "INFO")

            # Color code by level
            level_icon = "📘" if level == "info" else "⚠️" if level == "warn" else "❌" if level == "error" else "📄"

            print(f"{level_icon} [{timestamp}] [{container_name}] {message[:200]}")

    def get_error_logs(self, hours: int = 1, lines: int = 50):
        """Get error and warning logs"""
        now = datetime.utcnow()
        start_time = now - timedelta(hours=hours)

        query = {
            "size": lines,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": start_time.isoformat() + "Z",
                                    "lte": now.isoformat() + "Z"
                                }
                            }
                        }
                    ],
                    "should": [
                        {"match": {"level": "error"}},
                        {"match": {"level": "ERROR"}},
                        {"match": {"level": "warn"}},
                        {"match": {"level": "WARNING"}},
                        {"wildcard": {"message": "*error*"}},
                        {"wildcard": {"message": "*ERROR*"}},
                        {"wildcard": {"message": "*failed*"}},
                        {"wildcard": {"message": "*FAILED*"}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }

        result = self.search_logs(query)

        if not result or "hits" not in result:
            print(f"✅ No errors found in the last {hours} hour(s)")
            return

        hits = result["hits"]["hits"]
        total = result["hits"]["total"]["value"]

        print(f"🔴 Found {total} errors/warnings in the last {hours} hour(s), showing {len(hits)}:")
        print("=" * 80)

        for hit in hits:
            source = hit["_source"]
            timestamp = source.get("@timestamp", "Unknown time")
            container_name = source.get("container", {}).get("name", "Unknown")
            message = source.get("message", "No message")
            level = source.get("level", "UNKNOWN")

            level_icon = "⚠️" if level.lower() in ["warn", "warning"] else "❌"

            print(f"{level_icon} [{timestamp}] [{container_name}]")
            print(f"   {message[:300]}")
            print()

def main():
    parser = argparse.ArgumentParser(description="OpenSearch Diagnostic Tool")
    parser.add_argument("command", nargs="?", default="health",
                      help="Command to run (health, indices, recent, container, errors, search, test-log)")
    parser.add_argument("arg", nargs="?", help="Additional argument (container name or search query)")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back (default: 1)")
    parser.add_argument("--lines", type=int, default=50, help="Number of lines to show (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    diag = OpenSearchDiagnostic()

    if args.command == "health":
        print("🏥 OpenSearch Cluster Health")
        print("=" * 50)
        health = diag.health_check()
        if health:
            if args.json:
                print(json.dumps(health, indent=2))
            else:
                print(f"Cluster: {health.get('cluster_name')}")
                print(f"Status: {health.get('status')}")
                print(f"Nodes: {health.get('number_of_nodes')}")
                print(f"Active Shards: {health.get('active_shards')}")
                print(f"Relocating Shards: {health.get('relocating_shards')}")
                print(f"Initializing Shards: {health.get('initializing_shards')}")
                print(f"Unassigned Shards: {health.get('unassigned_shards')}")
        else:
            print("Failed to get cluster health")

    elif args.command == "indices":
        print("📊 OpenSearch Indices")
        print("=" * 50)
        indices = diag.list_indices()
        if indices:
            if args.json:
                print(json.dumps(indices, indent=2))
            else:
                for idx in indices:
                    print(f"Index: {idx.get('index')}")
                    print(f"  Status: {idx.get('health')} | Docs: {idx.get('docs.count')} | Size: {idx.get('store.size')}")
        else:
            print("No log indices found")

    elif args.command == "recent":
        diag.get_recent_logs(hours=args.hours, lines=args.lines)

    elif args.command == "container":
        if not args.arg:
            print("❌ Error: Please specify container name")
            sys.exit(1)
        diag.get_recent_logs(hours=args.hours, lines=args.lines, container=args.arg)

    elif args.command == "errors":
        diag.get_error_logs(hours=args.hours, lines=args.lines)

    elif args.command == "search":
        if not args.arg:
            print("❌ Error: Please specify search query")
            sys.exit(1)
        # Simple text search
        query = {
            "size": args.lines,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "query_string": {
                    "query": args.arg
                }
            }
        }
        result = diag.search_logs(query)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            hits = result.get("hits", {}).get("hits", [])
            print(f"Found {result.get('hits', {}).get('total', {}).get('value', 0)} results:")
            for hit in hits:
                source = hit["_source"]
                print(f"[{source.get('@timestamp')}] {source.get('message')}")

    elif args.command == "test-log":
        diag.add_test_log()

    else:
        print(f"❌ Unknown command: {args.command}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
