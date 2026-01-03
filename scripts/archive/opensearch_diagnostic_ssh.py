#!/usr/bin/env python3
"""
OpenSearch Diagnostic Tool for 83RR PowerEdge Infrastructure (SSH Version)

This script provides comprehensive container log analysis and infrastructure
diagnostics using SSH to access OpenSearch API directly on the server.

Usage:
    python scripts/opensearch_diagnostic_ssh.py [command] [options]

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

class OpenSearchDiagnosticSSH:
    def __init__(self, ssh_host: str = "192.168.1.179", ssh_user: str = "mcheli"):
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user

    def _ssh_command(self, command: str) -> str:
        """Execute command via SSH and return output"""
        ssh_cmd = f'ssh {self.ssh_user}@{self.ssh_host} "{command}"'
        try:
            result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"SSH command failed: {e}")
            print(f"Command: {command}")
            print(f"Error output: {e.stderr}")
            return ""

    def _opensearch_request(self, method: str, path: str, data: str = None) -> Dict:
        """Make request to OpenSearch via SSH"""
        curl_cmd = f"docker exec opensearch curl -s -X {method} 'http://localhost:9200{path}'"
        if data:
            curl_cmd += f" -H 'Content-Type: application/json' -d '{data}'"

        result = self._ssh_command(curl_cmd)
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

    def search_logs(self, query: Dict, index_pattern: str = "logs-homelab") -> Dict:
        """Search logs with given query"""
        query_json = json.dumps(query).replace('"', '\\"')
        return self._opensearch_request("POST", f"/{index_pattern}/_search", query_json)

    def add_test_log(self):
        """Add a test log entry to verify ingestion"""
        timestamp = datetime.utcnow().isoformat() + "Z"
        today = datetime.utcnow().strftime("%Y.%m.%d")

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
                "name": "poweredge-server"
            },
            "level": "info",
            "service": "diagnostic"
        }

        log_json = json.dumps(test_log).replace('"', '\\"')
        result = self._opensearch_request("POST", f"/logs-homelab-{today}/_doc", log_json)
        return result

    def recent_logs(self, hours: int = 1, size: int = 50) -> Dict:
        """Get recent logs from all containers"""
        # Simple query to get most recent logs with 'log' field (container logs)
        query = {
            "query": {
                "exists": {
                    "field": "log"
                }
            },
            "sort": [{"_id": {"order": "desc"}}],  # Sort by document ID for consistency
            "size": size
        }
        return self.search_logs(query)

    def container_logs(self, container_name: str, hours: int = 1, size: int = 50) -> Dict:
        """Get logs for specific container"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": since.isoformat() + "Z"
                                }
                            }
                        },
                        {
                            "wildcard": {
                                "container.name": f"*{container_name}*"
                            }
                        }
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": size
        }
        return self.search_logs(query)

    def error_logs(self, hours: int = 1, size: int = 50) -> Dict:
        """Get error logs from all containers"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": since.isoformat() + "Z"
                                }
                            }
                        },
                        {
                            "bool": {
                                "should": [
                                    {"wildcard": {"message": "*error*"}},
                                    {"wildcard": {"message": "*ERROR*"}},
                                    {"wildcard": {"message": "*failed*"}},
                                    {"wildcard": {"message": "*FAILED*"}},
                                    {"wildcard": {"message": "*exception*"}},
                                    {"wildcard": {"message": "*Exception*"}},
                                    {"term": {"level": "error"}},
                                    {"term": {"level": "ERROR"}}
                                ]
                            }
                        }
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": size
        }
        return self.search_logs(query)

    def custom_search(self, search_term: str, hours: int = 1, size: int = 50) -> Dict:
        """Search logs with custom term"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "exists": {
                                "field": "log"
                            }
                        }
                    ],
                    "should": [
                        {
                            "wildcard": {
                                "log": f"*{search_term}*"
                            }
                        },
                        {
                            "wildcard": {
                                "message": f"*{search_term}*"
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [{"_id": {"order": "desc"}}],
            "size": size
        }
        return self.search_logs(query)

    def format_log_entry(self, hit: Dict) -> str:
        """Format a single log entry for display"""
        source = hit.get("_source", {})
        timestamp = source.get("@timestamp", "Unknown")

        # Handle different log formats
        if "container" in source and "message" in source:
            # Properly structured logs (from test data)
            container = source.get("container", {}).get("name", "unknown")
            message = source.get("message", "")
            level = source.get("level", "info")
            stream = "stdout"
        else:
            # Nested JSON from Fluent Bit container logs
            log_data = source.get("log", "")
            if log_data and log_data.startswith("{"):
                try:
                    import json
                    parsed_log = json.loads(log_data)
                    message = parsed_log.get("log", "").strip()
                    stream = parsed_log.get("stream", "stdout")

                    # Extract container name from file path or use placeholder
                    container = "container"
                    if "container_name" in parsed_log:
                        container = parsed_log.get("container_name", "unknown")
                    else:
                        # For now, use generic container until we can extract from path
                        container = "docker-container"

                    # Determine log level from message content
                    message_lower = message.lower()
                    if any(word in message_lower for word in ["error", "err", "failed", "exception"]):
                        level = "error"
                    elif any(word in message_lower for word in ["warn", "warning"]):
                        level = "warn"
                    elif any(word in message_lower for word in ["debug"]):
                        level = "debug"
                    else:
                        level = "info"

                except json.JSONDecodeError:
                    message = log_data[:200] + "..." if len(log_data) > 200 else log_data
                    container = "unknown"
                    level = "info"
                    stream = "stdout"
            else:
                # Direct message
                container = source.get("container", {}).get("name", "unknown") if isinstance(source.get("container"), dict) else "unknown"
                message = source.get("message", log_data or "")
                level = source.get("level", "info")
                stream = "stdout"

        # Clean up timestamp
        if timestamp != "Unknown":
            try:
                # Handle various timestamp formats
                timestamp_clean = timestamp.replace(".%L.", ".000.").replace("%L", "000")
                if timestamp_clean.endswith("Z"):
                    dt = datetime.fromisoformat(timestamp_clean.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromisoformat(timestamp_clean)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                # Keep original timestamp if parsing fails
                timestamp = timestamp[:19] if len(timestamp) > 19 else timestamp

        # Format stream indicator
        stream_indicator = "⬆" if stream == "stdout" else "⬇" if stream == "stderr" else "•"

        return f"[{timestamp}] {container:15} {level:5} {stream_indicator} | {message[:150]}"

    def print_search_results(self, results: Dict, json_output: bool = False):
        """Print search results in formatted way"""
        if json_output:
            print(json.dumps(results, indent=2))
            return

        hits = results.get("hits", {}).get("hits", [])
        total = results.get("hits", {}).get("total", {}).get("value", 0)

        if total == 0:
            print("No log entries found")
            return

        print(f"Found {total} log entries (showing {len(hits)}):")
        print("-" * 80)

        for hit in hits:
            print(self.format_log_entry(hit))

    def print_health(self):
        """Print cluster health information"""
        health = self.health_check()
        if not health:
            print("Failed to get cluster health")
            return

        status = health.get("status", "unknown")
        nodes = health.get("number_of_nodes", 0)
        data_nodes = health.get("number_of_data_nodes", 0)

        status_colors = {
            "green": "🟢",
            "yellow": "🟡",
            "red": "🔴"
        }

        print(f"OpenSearch Cluster Health:")
        print(f"  Status: {status_colors.get(status, '⚫')} {status.upper()}")
        print(f"  Nodes: {nodes} total, {data_nodes} data nodes")
        print(f"  Cluster: {health.get('cluster_name', 'unknown')}")

    def print_indices(self):
        """Print available log indices"""
        indices = self.list_indices()
        if not indices:
            print("No log indices found")
            return

        print("Available log indices:")
        print("-" * 60)
        for idx in indices:
            health = idx.get("health", "unknown")
            name = idx.get("index", "unknown")
            docs = idx.get("docs.count", "0")
            size = idx.get("store.size", "0")

            health_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(health, "⚫")
            print(f"{health_icon} {name:30} {docs:>8} docs {size:>10}")

def main():
    parser = argparse.ArgumentParser(
        description="OpenSearch Diagnostic Tool for Container Logs (SSH Version)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("command", nargs="?", default="recent",
                       help="Command to execute")
    parser.add_argument("target", nargs="?",
                       help="Target container name or search query")
    parser.add_argument("--hours", type=int, default=1,
                       help="Hours to look back (default: 1)")
    parser.add_argument("--lines", type=int, default=50,
                       help="Number of lines to show (default: 50)")
    parser.add_argument("--json", action="store_true",
                       help="Output raw JSON")

    args = parser.parse_args()

    diagnostic = OpenSearchDiagnosticSSH()

    try:
        if args.command == "health":
            diagnostic.print_health()

        elif args.command == "indices":
            diagnostic.print_indices()

        elif args.command == "test-log":
            result = diagnostic.add_test_log()
            if result.get("result") == "created":
                print(f"✅ Test log added successfully: {result.get('_id')}")
            else:
                print(f"❌ Failed to add test log: {result}")

        elif args.command == "recent":
            results = diagnostic.recent_logs(args.hours, args.lines)
            diagnostic.print_search_results(results, args.json)

        elif args.command == "container":
            if not args.target:
                print("Error: container name required")
                sys.exit(1)
            results = diagnostic.container_logs(args.target, args.hours, args.lines)
            diagnostic.print_search_results(results, args.json)

        elif args.command == "errors":
            results = diagnostic.error_logs(args.hours, args.lines)
            diagnostic.print_search_results(results, args.json)

        elif args.command == "search":
            if not args.target:
                print("Error: search query required")
                sys.exit(1)
            results = diagnostic.custom_search(args.target, args.hours, args.lines)
            diagnostic.print_search_results(results, args.json)

        else:
            print(f"Unknown command: {args.command}")
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(0)

if __name__ == "__main__":
    main()