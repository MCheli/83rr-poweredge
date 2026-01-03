#!/usr/bin/env python3
"""
Environment Validation Script
Validates that the environment is ready for local development or production deployment
"""

import os
import subprocess
import sys
import socket
from pathlib import Path

def check_docker():
    """Check if Docker is available and running"""
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker available: {result.stdout.strip()}")

            # Check if Docker daemon is running
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Docker daemon is running")
                return True
            else:
                print("❌ Docker daemon is not running")
                print("   Start Docker Desktop or run: sudo systemctl start docker")
                return False
        else:
            print("❌ Docker not found")
            return False
    except FileNotFoundError:
        print("❌ Docker not installed")
        return False

def check_docker_compose():
    """Check if Docker Compose is available"""
    try:
        result = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker Compose available: {result.stdout.strip()}")
            return True
        else:
            print("❌ Docker Compose not working")
            return False
    except FileNotFoundError:
        print("❌ Docker Compose not found")
        return False

def check_environment_variables():
    """Check required environment variables"""
    print("🔍 Checking environment variables...")

    required_vars = [
        ('GITHUB_USERNAME', 'GitHub username for container registry'),
        ('GITHUB_TOKEN', 'GitHub token for container registry (or GITHUB_PAT)')
    ]

    optional_vars = [
        ('INFRASTRUCTURE_ENV', 'Environment override (development/production)'),
        ('JUPYTERHUB_CRYPT_KEY', 'JupyterHub encryption key'),
        ('GRAFANA_ADMIN_PASSWORD', 'Grafana admin password')
    ]

    missing_required = []

    for var, description in required_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        elif var == 'GITHUB_TOKEN' and os.getenv('GITHUB_PAT'):
            print(f"✅ GITHUB_PAT is set (alternative to GITHUB_TOKEN)")
        else:
            print(f"❌ {var} not set - {description}")
            missing_required.append(var)

    for var, description in optional_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        else:
            print(f"ℹ️  {var} not set - {description} (optional)")

    return len(missing_required) == 0

def check_ports():
    """Check if required ports are available"""
    print("🔍 Checking port availability...")

    ports_to_check = [
        (80, "HTTP"),
        (443, "HTTPS"),
        (3000, "Personal Website"),
        (5000, "Flask API"),
        (8000, "JupyterHub"),
        (9090, "Prometheus"),
        (3001, "Grafana"),
        (5601, "OpenSearch Dashboards"),
        (8080, "NGINX HTTP"),
        (8443, "NGINX HTTPS")
    ]

    available_ports = []
    occupied_ports = []

    for port, service in ports_to_check:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()

        if result == 0:
            print(f"⚠️  Port {port} ({service}) is occupied")
            occupied_ports.append((port, service))
        else:
            print(f"✅ Port {port} ({service}) is available")
            available_ports.append((port, service))

    if occupied_ports:
        print("\nℹ️  Note: Occupied ports may be from currently running containers.")
        print("   Stop existing containers if you plan to redeploy.")

    return True  # Don't fail on occupied ports

def check_infrastructure_files():
    """Check that key infrastructure files exist"""
    print("🔍 Checking infrastructure files...")

    required_files = [
        "docker-compose.yml",
        "docker-compose.override.yml",
        "docker-compose.prod.yml",
        "infrastructure/nginx/Dockerfile",
        "infrastructure/nginx/conf.d/default.conf",
        "infrastructure/nginx/dev-certs/localhost.crt",
        "infrastructure/nginx/dev-certs/localhost.key"
    ]

    project_root = Path(__file__).parent.parent
    missing_files = []

    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} missing")
            missing_files.append(file_path)

    return len(missing_files) == 0

def get_environment_info():
    """Display environment information"""
    print("🌍 Environment Information:")
    print(f"   Hostname: {socket.gethostname()}")
    print(f"   Working Directory: {os.getcwd()}")
    print(f"   Python: {sys.executable}")

    # Try to detect environment using our infrastructure manager logic
    try:
        sys.path.append(str(Path(__file__).parent))
        import infrastructure_manager_new
        manager = infrastructure_manager_new.InfrastructureManager()
        print(f"   Detected Environment: {manager.environment}")
        print(f"   Compose Files: {', '.join(manager.compose_files)}")
    except Exception as e:
        print(f"   Environment Detection: Failed ({e})")

def main():
    """Run all validation checks"""
    print("🔍 Infrastructure Environment Validation")
    print("=" * 60)

    get_environment_info()
    print()

    checks = [
        ("Docker Installation", check_docker),
        ("Docker Compose", check_docker_compose),
        ("Environment Variables", check_environment_variables),
        ("Port Availability", check_ports),
        ("Infrastructure Files", check_infrastructure_files)
    ]

    passed = 0
    total = len(checks)

    for check_name, check_func in checks:
        print(f"🔬 {check_name}")
        print("-" * 40)

        if check_func():
            passed += 1
            print(f"✅ {check_name}: PASSED\n")
        else:
            print(f"❌ {check_name}: FAILED\n")

    print("=" * 60)
    print(f"📊 Validation Results: {passed}/{total} passed ({(passed/total)*100:.1f}%)")

    if passed == total:
        print("🎉 Environment is ready for deployment!")
        print("\n🚀 You can now run:")
        print("   docker compose up          # Start local development")
        print("   # OR")
        print("   python scripts/infrastructure_manager_new.py deploy")
    else:
        print("⚠️  Please fix the failed checks before deploying.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)