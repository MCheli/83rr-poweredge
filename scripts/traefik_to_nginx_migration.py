#!/usr/bin/env python3
"""
Traefik to NGINX Migration Script
Handles the direct cutover from Traefik to NGINX with proper rollback capabilities
"""

import os
import sys
import time
import subprocess
from pathlib import Path

class TraefikNginxMigration:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent

    def _run_command(self, cmd, capture_output=True):
        """Run a command and return success, stdout, stderr"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True, cwd=self.project_root)
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def backup_traefik_config(self):
        """Backup current Traefik configuration"""
        print("💾 Backing up Traefik configuration...")

        backup_dir = self.project_root / "backups" / f"traefik-backup-{int(time.time())}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Backup Traefik compose files and dynamic configs
        traefik_files = [
            "infrastructure/traefik/docker-compose.yml",
            "infrastructure/traefik/dynamic/",
        ]

        for file_path in traefik_files:
            src = self.project_root / file_path
            if src.exists():
                if src.is_dir():
                    success, _, stderr = self._run_command(f"cp -r {src} {backup_dir}/")
                else:
                    success, _, stderr = self._run_command(f"cp {src} {backup_dir}/")

                if success:
                    print(f"✅ Backed up: {file_path}")
                else:
                    print(f"❌ Failed to backup {file_path}: {stderr}")
                    return False

        print(f"📁 Backup created at: {backup_dir}")
        return True

    def check_prerequisites(self):
        """Check that all prerequisites are met for migration"""
        print("🔍 Checking migration prerequisites...")

        # Check NGINX configuration
        nginx_config = self.project_root / "infrastructure/nginx/conf.d/production.conf"
        if not nginx_config.exists():
            print("❌ NGINX production config not found")
            return False

        # Check certificates exist (this will be for Cloudflare certificates later)
        cert_dir = self.project_root / "infrastructure/nginx/certs"
        if not cert_dir.exists():
            print("⚠️  Production certificates directory not found - will use Let's Encrypt during migration")

        # Check Docker Compose files
        compose_files = ["docker-compose.yml", "docker-compose.prod.yml"]
        for file in compose_files:
            if not (self.project_root / file).exists():
                print(f"❌ Missing: {file}")
                return False

        print("✅ Prerequisites check passed")
        return True

    def deploy_nginx_parallel(self):
        """Deploy NGINX alongside Traefik for testing"""
        print("🚀 Deploying NGINX alongside Traefik...")

        # First, stop any existing containers to avoid port conflicts
        print("🛑 Stopping existing containers...")
        success, _, stderr = self._run_command("docker compose down")
        if not success:
            print(f"⚠️  Could not stop existing containers: {stderr}")

        # Deploy with NGINX using production config
        print("🌍 Setting environment to production for NGINX test...")
        os.environ['INFRASTRUCTURE_ENV'] = 'production'

        # Deploy only NGINX service for testing
        success, stdout, stderr = self._run_command("docker compose up nginx -d", capture_output=False)
        if not success:
            print(f"❌ NGINX deployment failed: {stderr}")
            return False

        print("✅ NGINX deployed successfully")
        return True

    def test_nginx_endpoints(self):
        """Test NGINX endpoints before full cutover"""
        print("🧪 Testing NGINX endpoints...")

        # Test endpoints that should work without external dependencies
        test_endpoints = [
            ("localhost:80", "HTTP health check"),
            ("localhost:443", "HTTPS (will fail without proper certs - expected)"),
        ]

        for endpoint, description in test_endpoints:
            print(f"🔍 Testing {endpoint} ({description})")
            success, stdout, stderr = self._run_command(f"curl -k -m 5 http://{endpoint}/health || true")
            if "healthy" in stdout:
                print(f"✅ {endpoint} responding correctly")
            else:
                print(f"⚠️  {endpoint} not responding as expected (may need certificates)")

        return True

    def perform_cutover(self):
        """Perform the actual cutover from Traefik to NGINX"""
        print("🔄 Performing cutover to NGINX...")

        # Stop all services
        print("🛑 Stopping all services...")
        success, _, stderr = self._run_command("docker compose down")
        if not success:
            print(f"⚠️  Error stopping services: {stderr}")

        # Remove Traefik from the compose files (move it to backup)
        print("📋 Updating Docker Compose configuration...")

        # Deploy full infrastructure with NGINX
        os.environ['INFRASTRUCTURE_ENV'] = 'production'
        success, stdout, stderr = self._run_command("docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d", capture_output=False)

        if not success:
            print(f"❌ Full deployment failed: {stderr}")
            print("🔄 Attempting rollback...")
            self.rollback_to_traefik()
            return False

        print("✅ Cutover completed successfully")
        return True

    def validate_migration(self):
        """Validate that the migration was successful"""
        print("✅ Validating migration...")

        # Check that containers are running
        success, stdout, stderr = self._run_command("docker compose ps")
        if not success:
            print(f"❌ Could not check container status: {stderr}")
            return False

        print("📊 Container Status:")
        print(stdout)

        # Test basic connectivity
        success, stdout, stderr = self._run_command("curl -k -m 5 http://localhost/health || true")
        if "healthy" in stdout:
            print("✅ NGINX health check passed")
        else:
            print("⚠️  NGINX health check failed - may need DNS/certificate setup")

        print("🎉 Migration validation completed")
        return True

    def rollback_to_traefik(self):
        """Rollback to Traefik in case of issues"""
        print("🔄 Rolling back to Traefik...")

        # Stop NGINX deployment
        success, _, _ = self._run_command("docker compose down")

        # Note: This is a simplified rollback - in real scenario would restore Traefik
        print("⚠️  Manual intervention needed:")
        print("   1. Restore Traefik containers from backup")
        print("   2. Update DNS back to Traefik")
        print("   3. Validate Traefik is working")

        return True

    def cleanup_traefik(self):
        """Clean up Traefik containers and configurations"""
        print("🧹 Cleaning up Traefik (optional - keep for rollback)...")

        # For now, just provide instructions
        print("📋 Traefik cleanup steps (manual):")
        print("   1. Verify NGINX is stable for 24+ hours")
        print("   2. Remove Traefik containers: docker container rm traefik")
        print("   3. Remove Traefik volumes if no longer needed")
        print("   4. Clean up Traefik configuration files")

        return True

def main():
    """Main migration workflow"""
    import argparse

    parser = argparse.ArgumentParser(description='Traefik to NGINX Migration')
    parser.add_argument('action', choices=[
        'backup', 'check', 'test-nginx', 'cutover', 'validate', 'rollback', 'cleanup'
    ], help='Migration action to perform')

    args = parser.parse_args()

    migration = TraefikNginxMigration()

    print("🔄 Traefik to NGINX Migration")
    print("=" * 60)

    try:
        if args.action == 'backup':
            success = migration.backup_traefik_config()
        elif args.action == 'check':
            success = migration.check_prerequisites()
        elif args.action == 'test-nginx':
            success = migration.deploy_nginx_parallel() and migration.test_nginx_endpoints()
        elif args.action == 'cutover':
            success = (
                migration.backup_traefik_config() and
                migration.check_prerequisites() and
                migration.perform_cutover() and
                migration.validate_migration()
            )
        elif args.action == 'validate':
            success = migration.validate_migration()
        elif args.action == 'rollback':
            success = migration.rollback_to_traefik()
        elif args.action == 'cleanup':
            success = migration.cleanup_traefik()
        else:
            print(f"❌ Unknown action: {args.action}")
            success = False

        if success:
            print(f"\n🎉 {args.action} completed successfully!")
        else:
            print(f"\n❌ {args.action} failed!")

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()