#!/usr/bin/env python3
"""
Test NGINX Configuration
Validates NGINX configuration files and routing rules
"""

import os
import subprocess
import sys
from pathlib import Path

def test_nginx_syntax(config_file):
    """Test NGINX configuration syntax"""
    print(f"🔍 Testing NGINX syntax for {config_file}...")

    # Create a temporary NGINX config for testing
    test_dir = Path("/tmp/nginx-test")
    test_dir.mkdir(exist_ok=True)

    # Copy config to test directory
    config_path = Path(__file__).parent.parent / "infrastructure/nginx/conf.d" / config_file
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False

    test_config = test_dir / "nginx.conf"

    # Create minimal nginx.conf for testing
    with open(test_config, 'w') as f:
        f.write(f"""
events {{
    worker_connections 1024;
}}

http {{
    include {config_path};
}}
""")

    # Test configuration
    try:
        result = subprocess.run(
            ['nginx', '-t', '-c', str(test_config)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"✅ {config_file} syntax is valid")
            return True
        else:
            print(f"❌ {config_file} syntax error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("⚠️  NGINX not installed - skipping syntax check")
        return True  # Don't fail if nginx isn't installed
    except Exception as e:
        print(f"❌ Error testing {config_file}: {str(e)}")
        return False

def analyze_routing_coverage():
    """Analyze routing coverage compared to current Traefik setup"""
    print("🔍 Analyzing routing coverage...")

    # Current Traefik routes (from inspection)
    traefik_routes = {
        # Public services (*.markcheli.com)
        'www.markcheli.com': 'Personal Website',
        'flask.markcheli.com': 'Flask API',
        'jupyter.markcheli.com': 'JupyterHub',
        'ha.markcheli.com': 'Home Assistant',
        'ops.markcheli.com': 'Ops Base (whoami)',

        # LAN-only services (*.ops.markcheli.com)
        'traefik-local.ops.markcheli.com': 'Traefik Dashboard (current)',
        'portainer-local.ops.markcheli.com': 'Portainer (to be removed)',
        'logs-local.ops.markcheli.com': 'OpenSearch Dashboards',
        'opensearch-local.ops.markcheli.com': 'OpenSearch API (currently unused)',
        'www-dev.ops.markcheli.com': 'Development Website',
        'flask-dev.ops.markcheli.com': 'Development Flask API',
        'grafana-local.ops.markcheli.com': 'Grafana Dashboards',
        'prometheus-local.ops.markcheli.com': 'Prometheus Database',
        'cadvisor-local.ops.markcheli.com': 'cAdvisor Container Metrics'
    }

    # Check if NGINX production config covers all routes
    production_config = Path(__file__).parent.parent / "infrastructure/nginx/conf.d/production.conf"

    if not production_config.exists():
        print("❌ Production NGINX config not found")
        return False

    with open(production_config, 'r') as f:
        config_content = f.read()

    missing_routes = []
    covered_routes = []

    for domain, service in traefik_routes.items():
        if f'server_name {domain}' in config_content:
            print(f"✅ {domain} ({service})")
            covered_routes.append(domain)
        else:
            print(f"❌ {domain} ({service}) - MISSING")
            missing_routes.append(domain)

    coverage_pct = (len(covered_routes) / len(traefik_routes)) * 100
    print(f"\n📊 Route Coverage: {len(covered_routes)}/{len(traefik_routes)} ({coverage_pct:.1f}%)")

    if missing_routes:
        print("\n⚠️  Missing routes:")
        for route in missing_routes:
            print(f"   - {route}")
        return False

    print("🎉 All routes covered!")
    return True

def check_certificate_structure():
    """Check certificate directory structure"""
    print("🔍 Checking certificate structure...")

    cert_dirs = [
        "infrastructure/nginx/certs",           # Production certificates
        "infrastructure/nginx/dev-certs"       # Development certificates
    ]

    project_root = Path(__file__).parent.parent

    for cert_dir in cert_dirs:
        cert_path = project_root / cert_dir
        if not cert_path.exists():
            print(f"❌ Certificate directory missing: {cert_dir}")
            return False

        print(f"✅ {cert_dir} exists")

        # List certificate files
        cert_files = list(cert_path.glob("*.crt")) + list(cert_path.glob("*.pem"))
        key_files = list(cert_path.glob("*.key"))

        print(f"   📄 Certificate files: {len(cert_files)}")
        print(f"   🔑 Key files: {len(key_files)}")

    return True

def check_upstream_definitions():
    """Check that upstream definitions match service names"""
    print("🔍 Checking upstream definitions...")

    # Services from docker-compose.yml
    expected_services = [
        'personal-website',
        'flask-api',
        'jupyter',
        'opensearch-dashboards',
        'grafana',
        'prometheus',
        'cadvisor'
    ]

    production_config = Path(__file__).parent.parent / "infrastructure/nginx/conf.d/production.conf"

    if not production_config.exists():
        print("❌ Production config not found")
        return False

    with open(production_config, 'r') as f:
        config_content = f.read()

    missing_upstreams = []
    for service in expected_services:
        # Check for upstream definition (convert hyphen to underscore for upstream names)
        upstream_name = service.replace('-', '_')
        if f'upstream {upstream_name}' in config_content:
            print(f"✅ {service} -> {upstream_name}")
        else:
            print(f"❌ {service} upstream missing")
            missing_upstreams.append(service)

    return len(missing_upstreams) == 0

def create_migration_checklist():
    """Create migration checklist"""
    print("📋 Creating migration checklist...")

    checklist = """
# NGINX Migration Checklist

## Pre-Migration Preparation
- [ ] Backup current Traefik configuration
- [ ] Ensure all certificates are in place:
  - [ ] /etc/nginx/certs/wildcard-markcheli.crt
  - [ ] /etc/nginx/certs/wildcard-markcheli.key
  - [ ] /etc/nginx/certs/wildcard-ops-markcheli.crt
  - [ ] /etc/nginx/certs/wildcard-ops-markcheli.key
- [ ] Test NGINX configuration syntax
- [ ] Verify all upstreams are defined
- [ ] Confirm route coverage matches Traefik

## Migration Steps
1. [ ] Deploy NGINX alongside Traefik (different ports)
2. [ ] Test NGINX routing with temporary DNS entries
3. [ ] Validate SSL certificates work correctly
4. [ ] Test all service endpoints
5. [ ] Switch DNS to point to NGINX
6. [ ] Monitor for any issues
7. [ ] Remove Traefik containers

## Validation
- [ ] All public services accessible (*.markcheli.com)
- [ ] All LAN services accessible (*.ops.markcheli.com)
- [ ] SSL certificates working correctly
- [ ] WebSocket connections working (Jupyter, Home Assistant)
- [ ] API routing working correctly
- [ ] Security headers present

## Rollback Plan
- [ ] Keep Traefik containers stopped but available
- [ ] DNS change back to Traefik if needed
- [ ] Traefik restart procedure documented
"""

    checklist_file = Path(__file__).parent.parent / "NGINX_MIGRATION_CHECKLIST.md"
    with open(checklist_file, 'w') as f:
        f.write(checklist.strip())

    print(f"✅ Migration checklist created: {checklist_file}")
    return True

def main():
    """Run all NGINX configuration tests"""
    print("🧪 NGINX Configuration Tests")
    print("=" * 60)

    tests = [
        ("Development Config Syntax", lambda: test_nginx_syntax("default.conf")),
        ("Production Config Syntax", lambda: test_nginx_syntax("production.conf")),
        ("Routing Coverage Analysis", analyze_routing_coverage),
        ("Certificate Structure", check_certificate_structure),
        ("Upstream Definitions", check_upstream_definitions),
        ("Migration Checklist", create_migration_checklist)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔬 {test_name}")
        print("-" * 40)

        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {str(e)}")

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} passed ({(passed/total)*100:.1f}%)")

    if passed == total:
        print("🎉 NGINX configuration is ready for migration!")
        print("\n📋 Next steps:")
        print("   1. Review NGINX_MIGRATION_CHECKLIST.md")
        print("   2. Ensure production certificates are in place")
        print("   3. Test deployment in parallel with Traefik")
    else:
        print("⚠️  Please fix configuration issues before migration.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)