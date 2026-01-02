# OpenSearch Logging Stack

This directory contains the OpenSearch-based logging infrastructure for the homelab.

## Components

- **OpenSearch**: Search and analytics engine for log storage
- **OpenSearch Dashboards**: Web interface for log visualization and search
- **Logstash**: Log processing and transformation pipeline
- **Filebeat**: Lightweight log shipper for Docker containers

## Architecture

```
Docker Containers → Filebeat → Logstash → OpenSearch → OpenSearch Dashboards
```

## Access URLs

- **OpenSearch Dashboards**: https://logs-local.ops.markcheli.com (LAN only)
- **OpenSearch API**: https://opensearch-local.ops.markcheli.com (LAN only)

**Security Policy**: Both services are LAN-only for security. Access requires being on the local network (192.168.1.0/24).

## Configuration Files

- `docker-compose.yml`: Main service definitions
- `logstash.conf`: Logstash pipeline configuration
- `filebeat.yml`: Filebeat input and output configuration

## Security Notes

- OpenSearch security plugins are disabled for simplicity
- Both OpenSearch API and Dashboards are LAN-only for security
- Access restricted to local network (192.168.1.0/24, 10.0.0.0/8, 172.16.0.0/12)

## Log Collection

Filebeat automatically collects logs from:
- All Docker containers on the host
- Automatically adds Docker metadata (container name, image, etc.)
- Forwards to Logstash for processing
- Logstash enriches logs and forwards to OpenSearch

## Index Pattern

Logs are stored in daily indices: `logs-homelab-YYYY.MM.dd`

## Monitoring

- Filebeat monitoring data is sent to OpenSearch
- Logstash outputs debug information to stdout
- Check container logs for troubleshooting

## Deployment

```bash
# Deploy the stack
cd ~/83rr-poweredge
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d opensearch opensearch-dashboards

# Check status
docker ps --filter name=opensearch

# View logs
docker compose logs -f opensearch
docker compose logs -f opensearch-dashboards
```

## Troubleshooting

### Common Issues

1. **Memory Issues**: OpenSearch requires sufficient memory (1GB+ JVM heap)
2. **File Permissions**: Filebeat needs read access to Docker logs
3. **Network Connectivity**: Ensure all containers can communicate

### Debug Commands

```bash
# Check OpenSearch cluster health
curl http://opensearch-local.ops.markcheli.com/_cluster/health

# View Filebeat status
ssh 83rr-poweredge "docker exec filebeat filebeat test output"

# Check Logstash processing
ssh 83rr-poweredge "docker logs logstash"
```