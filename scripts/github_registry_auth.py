#!/usr/bin/env python3
"""
GitHub Registry Authentication Manager

This module manages GitHub Container Registry authentication for both local Docker
and Portainer registry configuration, ensuring credentials stay synchronized.
"""

import os
import sys
import subprocess
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GitHubRegistryAuth:
    def __init__(self):
        load_dotenv()
        self.registry_url = "ghcr.io"
        self.github_username = "mcheli"
        self.portainer_url = os.getenv('PORTAINER_URL')
        self.portainer_api_key = os.getenv('PORTAINER_API_KEY')
        self.portainer_endpoint_id = os.getenv('PORTAINER_ENDPOINT_ID', '3')

        if not all([self.portainer_url, self.portainer_api_key]):
            raise ValueError("Missing Portainer configuration")

    def get_github_token(self):
        """Get GitHub token with packages scope"""
        try:
            result = subprocess.run(['gh', 'auth', 'token'],
                                  capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except:
            return None

    def _verify_token_scopes(self, token):
        """Verify token has required scopes for packages"""
        try:
            headers = {'Authorization': f'token {token}'}
            response = requests.get('https://api.github.com/user/packages?package_type=container',
                                   headers=headers)
            return response.status_code == 200
        except:
            return False

    def update_portainer_registry(self, github_token):
        """Update Portainer registry configuration with new token"""
        print("🔄 Updating Portainer registry configuration...")

        headers = {
            'X-API-Key': self.portainer_api_key,
            'Content-Type': 'application/json'
        }

        # Get existing registry configuration
        registry_id = None
        response = requests.get(f'{self.portainer_url}/api/registries',
                              headers=headers, verify=False)

        if response.status_code == 200:
            registries = response.json()
            for registry in registries:
                if registry.get('URL') == self.registry_url:
                    registry_id = registry['Id']
                    break

        if not registry_id:
            print("❌ GitHub Container Registry not found in Portainer")
            return False

        # Update registry credentials
        update_payload = {
            "Name": "ghcr",
            "URL": self.registry_url,
            "Type": 3,
            "Authentication": True,
            "Username": self.github_username,
            "Password": github_token
        }

        response = requests.put(f'{self.portainer_url}/api/registries/{registry_id}',
                              headers=headers, json=update_payload, verify=False)

        if response.status_code == 200:
            print("✅ Portainer registry credentials updated successfully")
            return True
        else:
            print(f"❌ Failed to update Portainer registry: {response.status_code}")
            return False

    def is_authenticated(self):
        """Check if GitHub Container Registry is properly authenticated"""
        token = self.get_github_token()
        if not token or not self._verify_token_scopes(token):
            return False
        return True

    def authenticate(self):
        """Perform complete authentication setup"""
        print("🔐 Setting up GitHub Container Registry authentication...")

        # Get GitHub token
        token = self.get_github_token()
        if not token:
            print("❌ No GitHub token available")
            return False

        # Check token scopes
        if not self._verify_token_scopes(token):
            print("❌ GitHub token lacks packages scope")
            print("Run: gh auth refresh --scopes 'repo,workflow,read:packages,write:packages'")
            return False

        # Update Portainer registry
        if not self.update_portainer_registry(token):
            return False

        print("🎉 GitHub Container Registry authentication setup complete!")
        return True

    def setup_server_authentication(self):
        """Setup server authentication using Portainer"""
        return self.authenticate()

def main():
    if len(sys.argv) < 2:
        print("Usage: python github_registry_auth.py <command>")
        print("Commands: test, authenticate, verify-token")
        sys.exit(1)

    try:
        auth_manager = GitHubRegistryAuth()
        command = sys.argv[1].lower()

        if command == 'test':
            if auth_manager.is_authenticated():
                print("✅ Authentication checks passed")
                sys.exit(0)
            else:
                print("❌ Authentication issues detected")
                sys.exit(1)

        elif command == 'authenticate':
            if auth_manager.authenticate():
                print("✅ Authentication setup successful")
                sys.exit(0)
            else:
                print("❌ Authentication setup failed")
                sys.exit(1)

        elif command == 'verify-token':
            token = auth_manager.get_github_token()
            if token and auth_manager._verify_token_scopes(token):
                print("✅ GitHub token is valid")
                sys.exit(0)
            else:
                print("❌ GitHub token issues")
                sys.exit(1)

        else:
            print(f"❌ Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()