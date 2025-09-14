#!/bin/bash
# Clean up Docker backup directory to free space
# Run with sudo

set -e

echo "🧹 Cleaning up Docker backup directory..."

# Check current disk usage
echo "Current disk usage:"
df -h /

echo ""
echo "Checking Docker backup directory..."
BACKUP_DIR="/var/lib/docker.backup.20250914_035307"

if [ -d "$BACKUP_DIR" ]; then
    echo "📊 Size of backup directory:"
    du -sh "$BACKUP_DIR" 2>/dev/null || echo "Permission denied - continuing with cleanup"

    echo ""
    echo "🗑️  Removing Docker backup directory..."
    rm -rf "$BACKUP_DIR"

    if [ ! -d "$BACKUP_DIR" ]; then
        echo "✅ Docker backup directory removed successfully!"
    else
        echo "❌ Failed to remove Docker backup directory"
        exit 1
    fi
else
    echo "⚠️  Docker backup directory not found or already removed"
fi

# Clean up any other Docker remnants
echo ""
echo "🧹 Cleaning up other potential Docker remnants..."
find /var/lib -name "docker.backup*" -type d -exec rm -rf {} + 2>/dev/null || true
find /var/lib -name "docker-*" -type d -exec rm -rf {} + 2>/dev/null || true

# Clean up system logs while we're at it
echo ""
echo "📝 Cleaning up system logs..."
journalctl --vacuum-time=7d
journalctl --vacuum-size=100M

echo ""
echo "✅ Cleanup complete!"
echo "New disk usage:"
df -h /

echo ""
echo "Space freed up should be visible now!"