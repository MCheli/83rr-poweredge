#!/usr/bin/env python3
"""
OpenSearch Diagnostic Tool for 83RR PowerEdge Infrastructure

This script provides comprehensive container log analysis and infrastructure
diagnostics using the OpenSearch API.

Usage:
    python scripts/opensearch_diagnostic.py [command] [options]

Commands:
    recent          - Show recent logs from all containers
    container NAME  - Show logs for specific container
    errors          - Show error logs across all containers
    services        - Show logs by service type
    search QUERY    - Search logs with custom query
    health          - Check OpenSearch cluster health
    indices         - List all log indices

Options:
    --hours N       - Limit to last N hours (default: 1)
    --lines N       - Show N lines (default: 50)
    --level LEVEL   - Filter by log level (info, warn, error)
    --json          - Output raw JSON
"""

import requests
import json
import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class OpenSearchDiagnostic:
    def __init__(self, opensearch_url: str = "https://opensearch-local.ops.markcheli.com"):
        self.opensearch_url = opensearch_url
        self.session = requests.Session()
        self.session.verify = False  # Accept self-signed certificates

    def _make_request(self, method: str, path: str, **kwargs) -> Dict:
        """Make request to OpenSearch API with error handling"""
        url = f"{self.opensearch_url}{path}"
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to OpenSearch: {e}")
            print(f"URL: {url}")
            print("Make sure OpenSearch is running and accessible")
            sys.exit(1)

    def health_check(self) -> Dict:
        """Check OpenSearch cluster health"""
        return self._make_request("GET", "/_cluster/health")

    def list_indices(self) -> List[Dict]:
        """List all indices in OpenSearch"""
        result = self._make_request("GET", "/_cat/indices/logs*?format=json")
        return result if isinstance(result, list) else []

    def search_logs(self, query: Dict, index_pattern: str = "logs-*") -> Dict:
        """Search logs with given query"""
        return self._make_request("POST", f"/{index_pattern}/_search", json=query)

    def recent_logs(self, hours: int = 1, size: int = 50) -> Dict:
        """Get recent logs from all containers"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = {
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": since.isoformat() + "Z"
                    }
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
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

    def service_logs(self, service_name: str, hours: int = 1, size: int = 50) -> Dict:
        """Get logs for specific service"""
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
                                "service": f"*{service_name}*"
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
                            "query_string": {
                                "query": search_term,
                                "default_field": "message"
                            }
                        }
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": size
        }
        return self.search_logs(query)

    def format_log_entry(self, hit: Dict) -> str:
        """Format a single log entry for display"""
        source = hit.get("_source", {})
        timestamp = source.get("@timestamp", "Unknown")
        container = source.get("container", {}).get("name", "unknown")
        message = source.get("message", "")
        level = source.get("level", "info")

        # Clean up timestamp
        if timestamp != "Unknown":
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        return f"[{timestamp}] {container:15} {level:5} | {message}"

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
        description="OpenSearch Diagnostic Tool for Container Logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("command", nargs="?", default="recent",
                       help="Command to execute (recent, container, errors, services, search, health, indices)")
    parser.add_argument("target", nargs="?",
                       help="Target container/service name or search query")
    parser.add_argument("--hours", type=int, default=1,
                       help="Hours to look back (default: 1)")
    parser.add_argument("--lines", type=int, default=50,
                       help="Number of lines to show (default: 50)")
    parser.add_argument("--level", choices=["debug", "info", "warn", "error"],
                       help="Filter by log level")
    parser.add_argument("--json", action="store_true",
                       help="Output raw JSON")
    parser.add_argument("--url", default="https://opensearch-local.ops.markcheli.com",
                       help="OpenSearch URL (default: https://opensearch-local.ops.markcheli.com)")

    args = parser.parse_args()

    diagnostic = OpenSearchDiagnostic(args.url)

    try:
        if args.command == "health":
            diagnostic.print_health()

        elif args.command == "indices":
            diagnostic.print_indices()

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

        elif args.command == "services":
            if not args.target:
                print("Error: service name required")
                sys.exit(1)
            results = diagnostic.service_logs(args.target, args.hours, args.lines)
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