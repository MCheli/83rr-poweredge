#!/usr/bin/env python3
"""
Deploy stack via SSH by copying compose file and using docker stack deploy
"""
import os
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv

def deploy_via_ssh(stack_name, compose_file_path):
    load_dotenv()

    ssh_host = os.getenv('SSH_HOST')
    ssh_user = os.getenv('SSH_USER')

    if not all([ssh_host, ssh_user]):
        print("❌ Missing SSH configuration (SSH_HOST, SSH_USER)")
        return False

    compose_file = Path(compose_file_path)
    if not compose_file.exists():
        print(f"❌ Compose file not found: {compose_file_path}")
        return False

    print(f"🚀 Deploying {stack_name} via SSH")
    print("=" * 40)

    try:
        # Copy compose file to server
        remote_path = f"/tmp/{stack_name}-compose.yml"

        scp_cmd = f"scp {compose_file} {ssh_user}@{ssh_host}:{remote_path}"
        print(f"📁 Copying compose file to server...")

        result = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Failed to copy file: {result.stderr}")
            return False

        print("✅ File copied successfully")

        # Deploy stack using docker compose on remote server
        deploy_cmd = f'''ssh {ssh_user}@{ssh_host} "
            cd /tmp &&
            echo 'Stopping existing containers...' &&
            docker compose -p {stack_name} -f {remote_path} down &&
            echo 'Starting updated stack...' &&
            docker compose -p {stack_name} -f {remote_path} up -d &&
            echo 'Deployment complete!' &&
            rm {remote_path}
        "'''

        print(f"🔄 Deploying stack on remote server...")

        result = subprocess.run(deploy_cmd, shell=True, capture_output=True, text=True)
        print(result.stdout)

        if result.returncode == 0:
            print("✅ Stack deployed successfully via SSH!")
            return True
        else:
            print(f"❌ Deployment failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python deploy_via_ssh.py <stack_name> <compose_file_path>")
        print("Example: python deploy_via_ssh.py traefik infrastructure/traefik/docker-compose.yml")
        sys.exit(1)

    stack_name = sys.argv[1]
    compose_file = sys.argv[2]

    success = deploy_via_ssh(stack_name, compose_file)
    sys.exit(0 if success else 1)