#!/bin/bash
# Setup Second Disk for Data Storage
# Run this script with sudo on the server

set -e

echo "🔧 Setting up second disk (/dev/sdb) for data storage..."

# Step 1: Partition the disk
echo "📦 Creating partition on /dev/sdb..."
parted /dev/sdb --script mklabel gpt
parted /dev/sdb --script mkpart primary ext4 0% 100%

# Step 2: Format with ext4
echo "💾 Formatting partition with ext4..."
mkfs.ext4 -F /dev/sdb1

# Step 3: Create mount point
echo "📁 Creating mount point..."
mkdir -p /data

# Step 4: Mount the disk
echo "🔗 Mounting disk..."
mount /dev/sdb1 /data

# Step 5: Get UUID for fstab
UUID=$(blkid -s UUID -o value /dev/sdb1)
echo "📝 Adding to /etc/fstab for auto-mount..."
echo "UUID=$UUID /data ext4 defaults 0 2" >> /etc/fstab

# Step 6: Set permissions
echo "🔐 Setting permissions..."
chown mcheli:mcheli /data
chmod 755 /data

# Step 7: Create Docker directory
echo "🐳 Creating Docker data directory..."
mkdir -p /data/docker
chown root:root /data/docker

echo "✅ Second disk setup complete!"
echo "   - Mounted at: /data"
echo "   - Total space: $(df -h /data | tail -1 | awk '{print $2}')"
echo "   - Available space: $(df -h /data | tail -1 | awk '{print $4}')"
echo ""
echo "Next steps:"
echo "1. Stop Docker services"
echo "2. Move Docker data to /data/docker"
echo "3. Update Docker daemon configuration"
echo "4. Restart services"