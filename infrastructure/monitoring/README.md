# Monitoring Stack

Comprehensive monitoring solution using Prometheus, Grafana, and various exporters for the 83RR PowerEdge infrastructure.

## Overview

The monitoring stack provides metrics collection, visualization, and alerting for all infrastructure components.

## Components

| Component | Role | Port | URL |
|-----------|------|------|-----|
| Prometheus | Metrics database | 9090 | https://prometheus-local.ops.markcheli.com |
| Grafana | Visualization | 3000 | https://grafana-local.ops.markcheli.com |
| cAdvisor | Container metrics | 8080 | https://cadvisor-local.ops.markcheli.com |
| Node Exporter | Host metrics | 9100 | Internal only |
| NGINX Exporter | NGINX metrics | 9113 | Internal only |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Monitoring Stack                                   │
│                                                                              │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐            │
│  │  Node Exporter │    │    cAdvisor    │    │ NGINX Exporter │            │
│  │   (Host CPU,   │    │  (Container    │    │  (Connections, │            │
│  │   Memory, Disk)│    │   Metrics)     │    │   Requests)    │            │
│  └───────┬────────┘    └───────┬────────┘    └───────┬────────┘            │
│          │                     │                     │                      │
│          └─────────────────────┼─────────────────────┘                      │
│                                ▼                                            │
│                    ┌─────────────────────┐                                  │
│                    │     Prometheus      │                                  │
│                    │  (Metrics Storage)  │                                  │
│                    │   30-day retention  │                                  │
│                    └──────────┬──────────┘                                  │
│                               │                                             │
│                               ▼                                             │
│                    ┌─────────────────────┐                                  │
│                    │      Grafana        │                                  │
│                    │  (Visualization)    │                                  │
│                    │    Dashboards       │                                  │
│                    └─────────────────────┘                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
monitoring/
├── prometheus.yml                 # Prometheus configuration
├── docker-compose.yml             # Standalone deployment (optional)
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── datasources.yaml   # Prometheus datasource
│       └── dashboards/
│           ├── dashboards.yaml    # Dashboard provider config
│           ├── system.json        # System metrics dashboard
│           ├── containers.json    # Container metrics dashboard
│           ├── docker-services.json # Per-service dashboard
│           ├── infrastructure-overview.json # Overview dashboard
│           └── nginx.json         # NGINX dashboard
├── grafana-dashboard.json         # Legacy dashboard (symlink)
└── grafana-dashboard-*.json       # Legacy dashboard files
```

## Prometheus Configuration

### Scrape Targets

```yaml
scrape_configs:
  - job_name: 'prometheus'
    targets: ['localhost:9090']

  - job_name: 'cadvisor'
    targets: ['cadvisor:8080']

  - job_name: 'node-exporter'
    targets: ['node-exporter:9100']

  - job_name: 'nginx-exporter'
    targets: ['nginx-exporter:9113']
```

### Checking Target Health

```bash
# Via Prometheus API
docker exec prometheus wget -qO- http://localhost:9090/api/v1/targets | \
  python3 -c "import sys,json; [print(f\"{t['labels']['job']}: {t['health']}\") for t in json.load(sys.stdin)['data']['activeTargets']]"

# Via make command
make health
```

## Grafana Dashboards

### Available Dashboards

| Dashboard | Description |
|-----------|-------------|
| **Infrastructure Overview** | Single pane of glass - CPU, memory, disk, network, container status |
| **System Metrics** | Detailed host metrics - CPU modes, memory breakdown, disk I/O, network |
| **Docker Containers** | Container CPU/memory usage, network traffic |
| **Docker Services** | Per-service metrics for each container |
| **NGINX** | Connections, requests, upstream health |

### Access Grafana

- **URL**: https://grafana-local.ops.markcheli.com
- **Username**: admin
- **Password**: admin123 (or `$GRAFANA_ADMIN_PASSWORD` in production)

### Dashboard Provisioning

Dashboards are automatically provisioned from JSON files in `grafana/provisioning/dashboards/`.

To add a new dashboard:
1. Create JSON file in `grafana/provisioning/dashboards/`
2. Ensure proper permissions: `chmod 644 <file>.json`
3. Restart Grafana: `make grafana-reload`

## Exporters

### Node Exporter (Host Metrics)

Collects system-level metrics from the Docker host:
- CPU usage (per-core, per-mode)
- Memory (total, available, cached, buffers)
- Disk (usage, I/O, filesystem)
- Network (interface traffic, errors)
- System load averages
- Uptime

### cAdvisor (Container Metrics)

Collects per-container metrics:
- CPU usage
- Memory usage and limits
- Network I/O
- Filesystem I/O
- Container restart counts

### NGINX Exporter

Collects NGINX stub_status metrics:
- Active connections
- Reading/Writing/Waiting connections
- Total requests
- Accepted/Handled connections

## Management Commands

```bash
# Reload Prometheus configuration
make prometheus-reload

# Reload Grafana (restart to pick up new dashboards)
make grafana-reload

# View Prometheus targets
make health

# Check specific exporter
docker exec prometheus wget -qO- http://node-exporter:9100/metrics | head -20

# Access Prometheus web UI
open https://prometheus-local.ops.markcheli.com
```

## Useful Prometheus Queries

### System Metrics

```promql
# CPU usage percentage
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage percentage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk usage percentage
(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100

# System load (1m average)
node_load1
```

### Container Metrics

```promql
# Container CPU usage (cores)
rate(container_cpu_usage_seconds_total{name!=""}[1m])

# Container memory usage
container_memory_usage_bytes{name!=""}

# Container network received (bytes/sec)
rate(container_network_receive_bytes_total{name!=""}[1m])
```

### NGINX Metrics

```promql
# Active connections
nginx_connections_active

# Requests per second
rate(nginx_http_requests_total[1m])

# Dropped connections
nginx_connections_accepted - nginx_connections_handled
```

## Data Retention

- **Prometheus**: 30-day retention (configured in docker-compose.yml)
- **Storage**: Data stored in `prometheus_data` Docker volume

To change retention:
```yaml
# In docker-compose.yml
command:
  - '--storage.tsdb.retention.time=30d'  # Adjust as needed
```

## Alerting (Future)

Prometheus Alertmanager can be added for alerting:
1. Add alertmanager service to docker-compose.yml
2. Configure alert rules in prometheus.yml
3. Set up notification channels (email, Slack, etc.)

## Troubleshooting

### Grafana Dashboard Shows "No Data"

```bash
# Check Prometheus is scraping targets
docker exec prometheus wget -qO- http://localhost:9090/api/v1/targets

# Verify datasource UID matches dashboard
cat infrastructure/monitoring/grafana/provisioning/datasources/datasources.yaml
# uid should be "prometheus"

# Test query in Prometheus
docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up"
```

### Exporter Not Responding

```bash
# Check exporter container
docker ps | grep exporter

# View exporter logs
docker compose logs node-exporter
docker compose logs nginx-exporter

# Test exporter metrics endpoint
docker exec prometheus wget -qO- http://node-exporter:9100/metrics | head
```

### Prometheus High Memory Usage

```bash
# Check current memory
docker stats prometheus --no-stream

# Reduce retention period
# Edit docker-compose.yml: --storage.tsdb.retention.time=15d

# Compact TSDB
docker exec prometheus promtool tsdb compact /prometheus
```

### Dashboard Provisioning Fails

```bash
# Check Grafana logs
docker compose logs grafana | grep -i "provision\|error"

# Verify file permissions
ls -la infrastructure/monitoring/grafana/provisioning/dashboards/

# Fix permissions if needed
chmod 644 infrastructure/monitoring/grafana/provisioning/dashboards/*.json
chmod 644 infrastructure/monitoring/grafana/provisioning/dashboards/*.yaml
```

---

Part of the 83RR PowerEdge homelab infrastructure.
