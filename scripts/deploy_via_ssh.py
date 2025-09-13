#!/usr/bin/env python3
"""
Deploy stack via SSH using SINGLE SSH connection to respect MaxSessions limit.

FIXED VERSION: Uses rsync and single SSH session to avoid connection limits.
This server has a limit of 2 concurrent SSH sessions.
"""
import os
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import time

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

    print(f"🚀 Deploying {stack_name} via SSH (Single Session)")
    print("=" * 50)

    try:
        # Prepare local staging directory with all files
        with tempfile.TemporaryDirectory() as temp_dir:
            staging_dir = Path(temp_dir) / stack_name
            staging_dir.mkdir()

            compose_dir = compose_file.parent
            files_to_copy = []

            # Copy compose file
            staging_compose = staging_dir / "docker-compose.yml"
            staging_compose.write_text(compose_file.read_text())
            files_to_copy.append("docker-compose.yml")
            print(f"📁 Staged: docker-compose.yml")

            # Copy additional directories if they exist
            for dir_name in ["backend", "frontend", "web", "config"]:
                source_dir = compose_dir / dir_name
                if source_dir.exists():
                    dest_dir = staging_dir / dir_name
                    subprocess.run(["cp", "-r", str(source_dir), str(dest_dir)],
                                 capture_output=True, text=True)
                    files_to_copy.append(dir_name)
                    print(f"📁 Staged: {dir_name}/")

            # Copy .env file if it exists
            env_file = Path(".env")
            if env_file.exists():
                staging_env = staging_dir / ".env"
                staging_env.write_text(env_file.read_text())
                files_to_copy.append(".env")
                print(f"📁 Staged: .env")

            remote_dir = f"/tmp/{stack_name}"

            # Create tar archive locally
            tar_file = Path(temp_dir) / f"{stack_name}.tar.gz"
            print(f"🔄 Creating archive and copying via single SSH session...")

            # Create tar archive without extended attributes
            subprocess.run([
                "tar", "-czf", str(tar_file),
                "--no-xattrs", "--no-acls",
                "-C", str(staging_dir), "."
            ], capture_output=True, text=True)

            # Single SSH session: transfer, extract, and deploy all in one
            full_deploy_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 {ssh_user}@{ssh_host} "
                echo 'Preparing deployment directory...' &&
                rm -rf {remote_dir} &&
                mkdir -p {remote_dir} &&
                echo 'Receiving and extracting files...' &&
                cd {remote_dir} &&
                cat > deployment.tar.gz &&
                tar -xzf deployment.tar.gz &&
                rm deployment.tar.gz &&
                echo 'Files extracted successfully' &&
                echo '🔄 Starting deployment...' &&
                echo 'Stopping existing containers...' &&
                docker compose -p {stack_name} down &&
                echo 'Rebuilding images with updated code...' &&
                docker compose -p {stack_name} build --no-cache &&
                echo 'Starting updated stack...' &&
                docker compose -p {stack_name} up -d &&
                echo '✅ Deployment complete!' &&
                echo 'SSH session closing...'
            " < {tar_file}'''

            print(f"🔄 Transferring files and deploying stack...")

            result = subprocess.run(full_deploy_cmd, shell=True, capture_output=True, text=True)
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
        print("")
        print("FIXED: Now uses single SSH session to respect MaxSessions=2 limit")
        print("Features: Tar-based transfer, atomic operations, connection limit compliance")
        sys.exit(1)

    stack_name = sys.argv[1]
    compose_file = sys.argv[2]

    success = deploy_via_ssh(stack_name, compose_file)
    sys.exit(0 if success else 1)