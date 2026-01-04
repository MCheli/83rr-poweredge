# Fluent Bit Log Shipper

Fluent Bit collects logs from all Docker containers and ships them to OpenSearch for centralized log management.

## Overview

- **Role**: Log collection and forwarding
- **Image**: fluent/fluent-bit:3.2
- **Output**: OpenSearch (logs-homelab-* indices)
- **Input**: Docker container JSON logs

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Docker Host                                     │
│                                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                                    │
│  │  nginx   │ │  grafana │ │  flask   │  ... other containers              │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                                    │
│       │            │            │                                           │
│       ▼            ▼            ▼                                           │
│  /var/lib/docker/containers/*/*.log (JSON format)                          │
│                      │                                                       │
│                      ▼                                                       │
│              ┌──────────────┐                                               │
│              │  Fluent Bit  │                                               │
│              │              │                                               │
│              │  • Parse     │                                               │
│              │  • Enrich    │                                               │
│              │  • Forward   │                                               │
│              └──────┬───────┘                                               │
│                     │                                                        │
│                     ▼                                                        │
│              ┌──────────────┐         ┌─────────────────────┐              │
│              │  OpenSearch  │────────►│ OpenSearch Dashboards│              │
│              └──────────────┘         └─────────────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
fluent-bit/
├── fluent-bit.conf      # Main configuration
├── parsers.conf         # Log parsers (Docker JSON format)
├── docker_metadata.lua  # Lua script for container name extraction
└── extract_container.lua # Alternative container ID extraction
```

## Configuration

### Input (fluent-bit.conf)

```ini
[INPUT]
    Name              tail
    Path              /var/lib/docker/containers/*/*.log
    Parser            docker
    Tag               docker.<container_id>
    Tag_Regex         (?<container_id>[a-z0-9]{64})-json\.log$
    Refresh_Interval  10
    Mem_Buf_Limit     5MB
    Skip_Long_Lines   On
    DB                /var/log/flb_docker.db
    Read_from_Head    On
```

### Filters

1. **Lua Filter**: Extracts container name from Docker config
2. **Modify Filter**: Adds environment labels (homelab, 83rr-poweredge)

### Output

```ini
[OUTPUT]
    Name            opensearch
    Match           *
    Host            opensearch
    Port            9200
    Logstash_Format On
    Logstash_Prefix logs-homelab
    Suppress_Type_Name On
```

## Log Fields

Each log entry includes:

| Field | Description | Example |
|-------|-------------|---------|
| `@timestamp` | Log timestamp | 2026-01-04T12:00:00Z |
| `log` | Original log message | "GET / HTTP/1.1" 200 |
| `stream` | stdout or stderr | stdout |
| `container_id` | Short container ID | abc123def456 |
| `container_name` | Container name | nginx |
| `environment` | Environment label | homelab |
| `infrastructure` | Infrastructure label | 83rr-poweredge |

## Management Commands

```bash
# View Fluent Bit logs
make logs s=fluent-bit
# or: docker compose logs -f fluent-bit

# Restart Fluent Bit
make restart s=fluent-bit

# Check Fluent Bit metrics
curl http://localhost:2020/api/v1/metrics

# Reset position database (re-read all logs)
docker compose stop fluent-bit
docker run --rm -v 83rr-poweredge_fluent_bit_data:/data alpine rm -f /data/flb_docker.db
docker compose up -d fluent-bit
```

## Viewing Logs in OpenSearch

1. Access OpenSearch Dashboards: https://logs-local.ops.markcheli.com
2. Go to **Discover**
3. Select index pattern: `logs-homelab-*`
4. Filter by `container_name` to view specific service logs

### Useful Queries

```
# All nginx logs
container_name: nginx

# Error logs from any container
log: *error* OR log: *Error* OR log: *ERROR*

# Logs from last hour
@timestamp: [now-1h TO now]

# Flask API requests
container_name: flask-api AND log: *GET* OR log: *POST*
```

## Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `/var/lib/docker/containers` | `/var/lib/docker/containers:ro` | Docker log files |
| `fluent_bit_data` volume | `/var/log` | Position database |
| `./fluent-bit.conf` | `/fluent-bit/etc/fluent-bit.conf` | Configuration |
| `./parsers.conf` | `/fluent-bit/etc/parsers.conf` | Parsers |
| `./docker_metadata.lua` | `/fluent-bit/etc/docker_metadata.lua` | Lua script |

## Index Management

Logs are stored in daily indices:
- Pattern: `logs-homelab-YYYY.MM.DD`
- Example: `logs-homelab-2026.01.04`

### Check Index Status

```bash
# List all log indices
docker exec opensearch curl -s "http://localhost:9200/_cat/indices/logs-homelab-*?v&s=index"

# Count documents
docker exec opensearch curl -s "http://localhost:9200/logs-homelab-*/_count"
```

## Troubleshooting

### Logs Not Appearing in OpenSearch

```bash
# Check Fluent Bit is running
docker ps | grep fluent-bit

# Check Fluent Bit logs for errors
docker compose logs fluent-bit | grep -i error

# Verify OpenSearch is healthy
docker exec opensearch curl -s http://localhost:9200/_cluster/health

# Check Fluent Bit can reach OpenSearch
docker exec fluent-bit wget -qO- http://opensearch:9200/
```

### Missing Container Names

The Lua script reads container names from Docker config files. Ensure:
- `/var/lib/docker/containers` is mounted read-only
- Containers have been running long enough for config files to exist

### High Memory Usage

Adjust `Mem_Buf_Limit` in fluent-bit.conf if Fluent Bit uses too much memory:
```ini
Mem_Buf_Limit     10MB  # Increase buffer limit
```

### Duplicate Logs After Restart

The position database (`/var/log/flb_docker.db`) tracks read positions. If logs are duplicated:
1. Check if the database was deleted
2. Verify `Read_from_Head` is only enabled for initial ingestion

## Performance Tuning

| Setting | Default | Description |
|---------|---------|-------------|
| `Flush` | 5 | Seconds between output flushes |
| `Refresh_Interval` | 10 | Seconds between file checks |
| `Mem_Buf_Limit` | 5MB | Maximum memory buffer per input |
| `Buffer_Size` | 5MB | Output buffer size |

---

Part of the 83RR PowerEdge homelab infrastructure.
