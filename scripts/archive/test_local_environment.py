#!/usr/bin/env python3
"""
Test Local Development Environment
Validates Docker Compose configuration and service definitions
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a command and return success status and output"""
    try:
        if cwd is None:
            cwd = Path(__file__).parent.parent

        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def test_docker_compose_config():
    """Test Docker Compose configuration validity"""
    print("🔍 Testing Docker Compose configuration...")

    # Test base configuration
    success, stdout, stderr = run_command("docker compose config")
    if not success:
        print(f"❌ Base configuration invalid: {stderr}")
        return False

    print("✅ Base docker-compose.yml is valid")

    # Test production configuration
    success, stdout, stderr = run_command("docker compose -f docker-compose.yml -f docker-compose.prod.yml config")
    if not success:
        print(f"❌ Production configuration invalid: {stderr}")
        return False

    print("✅ Production configuration is valid")
    return True

def test_build_contexts():
    """Test that all build contexts exist"""
    print("🔍 Testing build contexts...")

    build_contexts = [
        "infrastructure/nginx",
        "infrastructure/personal-website/frontend",
        "infrastructure/flask-api",
        "infrastructure/jupyter"
    ]

    for context in build_contexts:
        context_path = Path(__file__).parent.parent / context
        dockerfile_path = context_path / "Dockerfile"

        if not context_path.exists():
            print(f"❌ Build context missing: {context}")
            return False

        if not dockerfile_path.exists():
            print(f"⚠️  Dockerfile missing: {context}/Dockerfile")
            # Don't fail for missing Dockerfiles yet - they'll be created in later phases
        else:
            print(f"✅ Build context exists: {context}")

    return True

def test_certificates():
    """Test that development certificates exist"""
    print("🔍 Testing development certificates...")

    cert_files = [
        "infrastructure/nginx/dev-certs/localhost.crt",
        "infrastructure/nginx/dev-certs/localhost.key",
        "infrastructure/nginx/dev-certs/fullchain.pem",
        "infrastructure/nginx/dev-certs/privkey.pem"
    ]

    for cert_file in cert_files:
        cert_path = Path(__file__).parent.parent / cert_file
        if not cert_path.exists():
            print(f"❌ Certificate missing: {cert_file}")
            return False

    print("✅ All development certificates present")
    return True

def test_nginx_config():
    """Test NGINX configuration syntax"""
    print("🔍 Testing NGINX configuration...")

    config_file = Path(__file__).parent.parent / "infrastructure/nginx/conf.d/default.conf"
    if not config_file.exists():
        print(f"❌ NGINX config missing: {config_file}")
        return False

    # Basic syntax check (look for obvious issues)
    with open(config_file, 'r') as f:
        content = f.read()

    if 'server {' not in content:
        print("❌ NGINX config appears malformed (no server blocks)")
        return False

    if 'upstream' not in content:
        print("❌ NGINX config missing upstream definitions")
        return False

    print("✅ NGINX configuration appears valid")
    return True

def test_environment_detection():
    """Test environment detection logic"""
    print("🔍 Testing environment detection...")

    # Import and test the infrastructure manager
    sys.path.append(str(Path(__file__).parent))
    try:
        import infrastructure_manager_new
        manager = infrastructure_manager_new.InfrastructureManager()

        print(f"✅ Environment detected: {manager.environment}")
        print(f"✅ Compose files: {', '.join(manager.compose_files)}")
        return True
    except ImportError as e:
        print(f"❌ Cannot import infrastructure manager: {e}")
        return False
    except Exception as e:
        print(f"❌ Environment detection failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Local Development Environment Tests")
    print("=" * 60)

    tests = [
        ("Docker Compose Configuration", test_docker_compose_config),
        ("Build Contexts", test_build_contexts),
        ("Development Certificates", test_certificates),
        ("NGINX Configuration", test_nginx_config),
        ("Environment Detection", test_environment_detection)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔬 {test_name}")
        print("-" * 40)

        if test_func():
            passed += 1
            print(f"✅ {test_name}: PASSED")
        else:
            print(f"❌ {test_name}: FAILED")

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} passed ({(passed/total)*100:.1f}%)")

    if passed == total:
        print("🎉 All tests passed! Local environment is ready.")
        return True
    else:
        print("⚠️  Some tests failed. Please fix issues before proceeding.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)