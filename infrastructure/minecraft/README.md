# Mark Cheli's Minecraft Server

A containerized Minecraft Java Edition server hosted at `minecraft.markcheli.com`.

## 🎮 Server Details

- **Server Address**: `minecraft.markcheli.com:25565`
- **Version**: Latest Minecraft Java Edition
- **Type**: Vanilla Survival Server
- **Max Players**: 20
- **Difficulty**: Normal
- **MOTD**: "Welcome to Mark Cheli's Minecraft Server! Have fun building!"

## 🌐 Web Interface

- **Status Page**: https://minecraft.markcheli.com
- **Features**: Real-time server status, player count, and server information

## 🏗️ Architecture

```
┌─────────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Minecraft Client  │◄──►│   NGINX          │◄──►│   Minecraft     │
│   Port: 25565       │    │   TCP Passthrough│    │   Server        │
└─────────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🚀 Features

### Minecraft Server
- **Latest Minecraft Version**: Automatically updates to the latest stable release
- **Vanilla Experience**: Pure Minecraft without mods or plugins
- **Persistent World**: World data is preserved across container restarts
- **RCON Management**: Remote console access for administration
- **Health Monitoring**: Built-in health checks with automatic recovery

### Web Interface
- **Real-time Status**: Live server information and player count
- **SSL Secured**: HTTPS access via Let's Encrypt certificates
- **Responsive Design**: Works on desktop and mobile devices
- **Performance Metrics**: Server performance and uptime statistics

## 🔧 Configuration

### Server Settings
- **Memory**: 4GB RAM allocation
- **View Distance**: 10 chunks
- **Spawn Protection**: 16 blocks radius
- **Nether**: Enabled
- **PVP**: Enabled (can be changed via RCON)

### Network Configuration
- **Game Port**: 25565 (TCP)
- **RCON Port**: 25575 (internal only)
- **Web Interface**: 443 (HTTPS)

## 📊 Monitoring & Health Checks

### Server Health
- **Health Check Interval**: 30 seconds
- **Startup Grace Period**: 120 seconds (server initialization)
- **Auto-Recovery**: Container restarts on failure

### Web Interface Health
- **Monitoring Interval**: 10 seconds between server polls
- **Status Updates**: Real-time server status updates
- **Health Check**: HTTP endpoint monitoring

## 🛠️ Management

### Starting/Stopping
The server is the `minecraft` service in the main `docker-compose.yml` (there is
no standalone compose file here any more). From `~/83rr-poweredge`:
```bash
# Start / recreate the Minecraft server
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d minecraft

# Stop the server
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop minecraft

# View logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f minecraft
```

### Server Administration
```bash
# Connect to RCON (requires RCON client)
# Password: minecraft
# Port: 25575 (accessible only from server)

# Example RCON commands:
/say Hello everyone!
/weather clear
/time set day
/gamemode creative <player>
```

### Data Management
```bash
# Backup world data
# (the live world is the volume 83rr-poweredge_minecraft_data_local; the
# nightly NAS backup already copies it)
docker run --rm -v 83rr-poweredge_minecraft_data_local:/data -v $(pwd):/backup alpine tar czf /backup/minecraft-backup-$(date +%Y%m%d).tar.gz /data

# Restore from backup (stop the server first)
docker run --rm -v 83rr-poweredge_minecraft_data_local:/data -v $(pwd):/backup alpine tar xzf /backup/minecraft-backup.tar.gz -C /
```

## 🔒 Security Features

- **SSL Certificates**: Automatic Let's Encrypt certificates for web interface
- **Network Isolation**: Internal Docker network for service communication
- **Container Security**: Non-root container execution
- **Health Monitoring**: Automatic failure detection and recovery
- **Resource Limits**: Memory and CPU constraints

## 📁 File Structure

```
infrastructure/minecraft/
├── README.md              # This documentation
├── config/, web/          # Leftovers of the old standalone setup
└── /data (in the container, volume 83rr-poweredge_minecraft_data_local)
    ├── world/             # Main world files
    ├── world_nether/      # Nether dimension
    ├── world_the_end/     # End dimension
    ├── server.properties  # Server configuration
    ├── whitelist.json     # Player whitelist
    ├── ops.json           # Operator privileges
    └── logs/              # Server logs
```

## 🌐 DNS Configuration

The server requires DNS configuration for `minecraft.markcheli.com`:
- **A Record**: Points to server IP address (173.48.155.66)
- **SRV Record** (optional): `_minecraft._tcp.minecraft.markcheli.com`

## 🚨 Troubleshooting

### Common Issues

1. **Server won't start**:
   ```bash
   # Check logs
   docker-compose logs minecraft

   # Common causes:
   # - Insufficient memory
   # - Port already in use
   # - Corrupt world data
   ```

2. **Can't connect to server**:
   ```bash
   # Test network connectivity
   telnet minecraft.markcheli.com 25565

   # Check NGINX routing
   docker logs nginx
   ```

3. **Web interface not accessible**:
   ```bash
   # Check web container status
   docker-compose ps minecraft-web

   # Test internal connectivity
   docker-compose exec minecraft-web wget -q -O- http://localhost:8080
   ```

### Performance Tuning
- **Memory**: Adjust `MEMORY` environment variable based on player count
- **View Distance**: Lower `VIEW_DISTANCE` for better performance
- **Garbage Collection**: Add JVM tuning via `JVM_OPTS` if needed

## 📞 Support

- **Server Issues**: Check container logs and restart if needed
- **Game Questions**: Refer to official Minecraft documentation
- **Infrastructure**: Part of the Mark Cheli homelab infrastructure

---

Built with ❤️ by Mark Cheli | Powered by Docker and NGINX