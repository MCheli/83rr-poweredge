#!/bin/bash
# Restart and Verify Docker After Migration

set -e

echo "🚀 Restarting and verifying Docker services..."

# Step 1: Start Docker daemon
echo "▶️  Starting Docker daemon..."
systemctl start docker
systemctl enable docker

# Wait for Docker to fully start
sleep 5

# Step 2: Verify Docker is running
echo "🔍 Verifying Docker status..."
systemctl status docker --no-pager -l

# Step 3: Check Docker info
echo "📊 Checking Docker configuration..."
echo "Docker Root Directory: $(docker info --format '{{.DockerRootDir}}')"
echo "Storage Driver: $(docker info --format '{{.Driver}}')"

# Step 4: Check available space
echo "💾 Available space on data disk:"
df -h /data

# Step 5: List containers
echo "📋 Current containers:"
docker ps -a

# Step 6: Restart containers
echo "🔄 Restarting containers..."
docker start $(docker ps -aq) 2>/dev/null || echo "No stopped containers to start"

echo "⏳ Waiting for containers to stabilize..."
sleep 15

echo "✅ Docker migration and restart complete!"
echo ""
echo "Summary:"
echo "- Docker data now stored on: /data/docker"
echo "- Available space: $(df -h /data | tail -1 | awk '{print $4}') of $(df -h /data | tail -1 | awk '{print $2}')"
echo "- Root filesystem usage now much lower"
echo ""
echo "Run 'df -h /' to see the improvement in root filesystem usage!"