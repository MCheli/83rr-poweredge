#!/usr/bin/env python3
"""
Cloudflare Cache Purge Utility

Purges Cloudflare cache for specified domains or URLs.
Requires CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_ID environment variables.

The API token needs "Cache Purge" permission (Zone > Cache Purge > Purge).

Usage:
    python scripts/cloudflare_cache_purge.py <service>
    python scripts/cloudflare_cache_purge.py --all
    python scripts/cloudflare_cache_purge.py --urls https://example.com/file.js

Examples:
    python scripts/cloudflare_cache_purge.py cookbook
    python scripts/cloudflare_cache_purge.py personal-website
    python scripts/cloudflare_cache_purge.py --all
"""

import os
import sys
import argparse
import requests
from dotenv import load_dotenv

# Service to domain mapping
SERVICE_DOMAINS = {
    "cookbook": "cookbook.markcheli.com",
    "personal-website": "www.markcheli.com",
    "flask-api": "flask.markcheli.com",
    "jupyterhub": "jupyter.markcheli.com",
}

def load_config():
    """Load Cloudflare credentials from environment."""
    load_dotenv()

    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")

    if not api_token:
        print("Error: CLOUDFLARE_API_TOKEN not set in environment or .env file")
        sys.exit(1)
    if not zone_id:
        print("Error: CLOUDFLARE_ZONE_ID not set in environment or .env file")
        sys.exit(1)

    return api_token, zone_id

def purge_urls(api_token: str, zone_id: str, urls: list[str]) -> bool:
    """Purge specific URLs from Cloudflare cache."""
    endpoint = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(endpoint, headers=headers, json={"files": urls})
    result = response.json()

    if result.get("success"):
        print(f"Successfully purged {len(urls)} URL(s)")
        return True
    else:
        errors = result.get("errors", [])
        for error in errors:
            print(f"Error {error.get('code')}: {error.get('message')}")
        return False

def purge_everything(api_token: str, zone_id: str) -> bool:
    """Purge entire Cloudflare cache for the zone."""
    endpoint = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(endpoint, headers=headers, json={"purge_everything": True})
    result = response.json()

    if result.get("success"):
        print("Successfully purged entire cache")
        return True
    else:
        errors = result.get("errors", [])
        for error in errors:
            print(f"Error {error.get('code')}: {error.get('message')}")
        return False

def purge_domain(api_token: str, zone_id: str, domain: str) -> bool:
    """Purge all cached content for a specific domain."""
    # Common static file extensions to purge
    extensions = ["", "/", "/index.html", "/app.js", "/styles.css", "/recipes.js"]
    urls = [f"https://{domain}{ext}" for ext in extensions]

    # Also purge with wildcard-like approach using prefix
    endpoint = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    # Try prefix purge first (Enterprise only, but worth trying)
    response = requests.post(endpoint, headers=headers, json={"prefixes": [f"https://{domain}/"]})
    result = response.json()

    if result.get("success"):
        print(f"Successfully purged cache for {domain} (prefix purge)")
        return True

    # Fall back to specific URLs
    print(f"Prefix purge not available, purging specific URLs for {domain}...")
    return purge_urls(api_token, zone_id, urls)

def main():
    parser = argparse.ArgumentParser(description="Purge Cloudflare cache")
    parser.add_argument("service", nargs="?", help="Service name to purge (cookbook, personal-website, flask-api, jupyterhub)")
    parser.add_argument("--all", action="store_true", help="Purge entire cache")
    parser.add_argument("--urls", nargs="+", help="Specific URLs to purge")
    parser.add_argument("--domain", help="Specific domain to purge")

    args = parser.parse_args()

    if not args.service and not args.all and not args.urls and not args.domain:
        parser.print_help()
        print("\nAvailable services:", ", ".join(SERVICE_DOMAINS.keys()))
        sys.exit(1)

    api_token, zone_id = load_config()

    if args.all:
        success = purge_everything(api_token, zone_id)
    elif args.urls:
        success = purge_urls(api_token, zone_id, args.urls)
    elif args.domain:
        success = purge_domain(api_token, zone_id, args.domain)
    elif args.service:
        if args.service not in SERVICE_DOMAINS:
            print(f"Unknown service: {args.service}")
            print("Available services:", ", ".join(SERVICE_DOMAINS.keys()))
            sys.exit(1)
        domain = SERVICE_DOMAINS[args.service]
        print(f"Purging cache for {args.service} ({domain})...")
        success = purge_domain(api_token, zone_id, domain)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
