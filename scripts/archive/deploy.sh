#!/usr/bin/env python3
"""
Homelab Deployment Script with Portainer API and SSH
Provides automatic backup, deployment, health checking, and rollback
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path
import requests
import yaml
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def colored(text: str, color: str) -> str:
    """Return colored text for terminal output"""
    return f"{color}{text}{Colors.ENDC}"

class HomelabDeployer:
    def __init__(self):
        """Initialize the deployer with environment configuration"""
        # Load environment variables
        load_dotenv()
        
        self.portainer_url = os.getenv('PORTAINER_URL')
        self.api_key = os.getenv('PORTAINER_API_KEY')
        self.ssh_host = os.getenv('SSH_HOST')
        self.ssh_user = os.getenv('SSH_USER')
        self.endpoint_id = os.getenv('PORTAINER_ENDPOINT_ID', '1')
        
        # Validate required environment variables
        if not all([self.portainer_url, self.api_key, self.ssh_host, self.ssh_user]):
            print(colored("❌ Missing required environment variables!", Colors.FAIL))
            print("Please ensure your .env file contains:")
            print("  - PORTAINER_URL")
            print("  - PORTAINER_API_KEY")
            print("  - SSH_HOST")
            print("  - SSH_USER")
            sys.exit(1)
        
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Create necessary directories
        Path("backups").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
        # Setup logging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f"logs/deployment_{timestamp}.log"
        
        # Service health check configurations
        self.health_configs = {
            'traefik': {
                'containers': ['traefik', 'whoami'],
                'url': os.getenv('TRAEFIK_URL'),
                'wait_time': 15
            },
            'jupyter': {
                'containers': ['jupyterhub', 'jupyterhub-proxy', 'jupyterhub-db'],
                'url': os.getenv('JUPYTER_URL'),
                'wait_time': 30
            },
            'logs': {
                'containers': ['logs-loki-1', 'logs-promtail-1', 'logs-grafana-1'],
                'url': os.getenv('GRAFANA_URL'),
                'wait_time': 20
            }
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message to file and console with appropriate formatting"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\n")
        
        # Console output with color
        if level == "ERROR":
            print(colored(log_entry, Colors.FAIL))
        elif level == "SUCCESS":
            print(colored(log_entry, Colors.GREEN))
        elif level == "WARNING":
            print(colored(log_entry, Colors.WARNING))
        elif level == "HEADER":
            print(colored(message, Colors.HEADER + Colors.BOLD))
        else:
            print(log_entry)
    
    def run_ssh_command(self, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """Execute command on remote server via SSH"""
        ssh_cmd = f"ssh -o ConnectTimeout=5 {self.ssh_user}@{self.ssh_host} '{command}'"
        
        try:
            result = subprocess.run(
                ssh_cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, str(e)
    
    def test_connectivity(self) -> bool:
        """Test connectivity to both Portainer API and SSH"""
        self.log("Testing connectivity...", "HEADER")
        
        # Test SSH
        success, output = self.run_ssh_command("echo 'SSH OK'")
        if success:
            self.log("✅ SSH connection successful", "SUCCESS")
        else:
            self.log(f"❌ SSH connection failed: {output}", "ERROR")
            return False
        
        # Test Portainer API
        try:
            response = requests.get(
                f"{self.portainer_url}/api/stacks",
                headers=self.headers,
                verify=False,
                timeout=5
            )
            if response.status_code == 200:
                self.log("✅ Portainer API connection successful", "SUCCESS")
                stacks = response.json()
                self.log(f"Found {len(stacks)} existing stacks", "INFO")
                return True
            else:
                self.log(f"❌ Portainer API error: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"❌ Portainer API connection failed: {str(e)}", "ERROR")
            return False
    
    def get_stacks(self) -> List[Dict]:
        """Fetch all stacks from Portainer"""
        try:
            response = requests.get(
                f"{self.portainer_url}/api/stacks",
                headers=self.headers,
                verify=False
            )
            if response.status_code == 200:
                return response.json()
            else:
                self.log(f"Failed to fetch stacks: {response.text}", "ERROR")
                return []
        except Exception as e:
            self.log(f"Error fetching stacks: {str(e)}", "ERROR")
            return []
    
    def get_stack_by_name(self, name: str) -> Optional[Dict]:
        """Get a specific stack by name"""
        stacks = self.get_stacks()
        for stack in stacks:
            if stack['Name'] == name:
                return stack
        return None
    
    def backup_stack(self, stack_name: str) -> Optional[str]:
        """Create backup of current stack configuration"""
        stack = self.get_stack_by_name(stack_name)
        if stack:
            backup_dir = Path(f"backups/{stack_name}")
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"{stack_name}_{timestamp}.json"
            
            # Fetch the full stack details including file content
            try:
                response = requests.get(
                    f"{self.portainer_url}/api/stacks/{stack['Id']}/file",
                    headers=self.headers,
                    verify=False
                )
                if response.status_code == 200:
                    stack['StackFileContent'] = response.json().get('StackFileContent', '')
            except:
                pass
            
            with open(backup_path, 'w') as f:
                json.dump(stack, f, indent=2)
            
            self.log(f"📦 Backed up {stack_name} to {backup_path}", "SUCCESS")
            return str(backup_path)
        else:
            self.log(f"⚠️ No existing stack '{stack_name}' to backup", "WARNING")
            return None
    
    def validate_compose_file(self, compose_file_path: str) -> bool:
        """Validate docker-compose file syntax"""
        self.log(f"Validating {compose_file_path}...")
        
        try:
            with open(compose_file_path, 'r') as f:
                yaml.safe_load(f)
            
            # Additional validation with docker-compose
            result = subprocess.run(
                f"docker-compose -f {compose_file_path} config",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.log("✅ Compose file validation passed", "SUCCESS")