#!/bin/bash
# Migrate Docker to Second Disk
# Run this script with sudo AFTER setup_data_disk.sh

set -e

echo "🐳 Migrating Docker to data disk..."

# Step 1: Stop all containers and Docker daemon
echo "⏹️  Stopping Docker services..."
systemctl stop docker
systemctl stop docker.socket

# Step 2: Verify Docker is stopped
echo "🔍 Verifying Docker is stopped..."
if pgrep dockerd > /dev/null; then
    echo "❌ Docker still running. Please stop manually and retry."
    exit 1
fi

# Step 3: Move Docker data
echo "📦 Moving Docker data to /data/docker..."
if [ -d "/var/lib/docker" ]; then
    rsync -aP /var/lib/docker/ /data/docker/

    # Backup original directory
    mv /var/lib/docker /var/lib/docker.backup.$(date +%Y%m%d_%H%M%S)
    echo "✅ Original Docker data backed up to /var/lib/docker.backup.$(date +%Y%m%d_%H%M%S)"
else
    echo "⚠️  /var/lib/docker doesn't exist, creating new structure..."
fi

# Step 4: Create Docker daemon configuration
echo "⚙️  Configuring Docker daemon..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << EOF
{
    "data-root": "/data/docker",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF

# Step 5: Create symlink for compatibility (optional)
ln -sf /data/docker /var/lib/docker

# Step 6: Set proper permissions
chown -R root:root /data/docker

echo "✅ Docker migration complete!"
echo ""
echo "Next steps:"
echo "1. Start Docker: systemctl start docker"
echo "2. Verify containers: docker ps"
echo "3. Check new location: docker info | grep 'Docker Root Dir'"
echo ""
echo "New Docker data location: /data/docker"
echo "Available space: $(df -h /data | tail -1 | awk '{print $4}')"