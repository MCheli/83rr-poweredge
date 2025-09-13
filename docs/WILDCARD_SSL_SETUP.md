# Wildcard SSL Certificate Setup

## Overview

This document describes the implementation of wildcard SSL certificates using Google Domains DNS-01 challenge to resolve Let's Encrypt rate limiting issues.

## Problem Statement

The previous SSL configuration had several critical issues:

1. **Rate Limiting**: Multiple services requesting individual certificates triggered Let's Encrypt's rate limits
2. **LAN Domain Issues**: Internal services (*.ops.markcheli.com) couldn't complete HTTP-01 challenges
3. **Repeated Failures**: Failed challenges created a loop of retry attempts, worsening rate limits

## Solution: Wildcard Certificates with DNS-01 Challenge

### Benefits

- ✅ **Single Certificate**: One wildcard cert covers all subdomains
- ✅ **No Rate Limits**: Eliminates individual domain certificate requests
- ✅ **LAN Compatibility**: DNS-01 works for internal services
- ✅ **Better Security**: Centralized certificate management
- ✅ **Future-Proof**: Easy to add new subdomains

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Wildcard SSL Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  *.markcheli.com Wildcard Certificate                          │
│  ├── www.markcheli.com (public website)                        │
│  ├── flask.markcheli.com (public API)                          │
│  └── home.markcheli.com (if public)                            │
│                                                                 │
│  *.ops.markcheli.com Wildcard Certificate                      │
│  ├── traefik-local.ops.markcheli.com (LAN-only)               │
│  ├── jupyter.ops.markcheli.com (LAN-only)                     │
│  ├── opensearch-local.ops.markcheli.com (LAN-only)            │
│  ├── logs-local.ops.markcheli.com (LAN-only)                  │
│  └── www-dev.ops.markcheli.com (LAN-only)                     │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  DNS-01 Challenge via Google Domains API                       │
│  → No public accessibility required                             │
│  → Works for all domains (public & LAN)                        │
│  → Automated DNS record management                              │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Traefik Configuration Changes

**DNS-01 Challenge Setup:**
```yaml
environment:
  - GOOGLE_DOMAINS_ACCESS_TOKEN=${GOOGLE_DOMAINS_ACCESS_TOKEN}

command:
  # DNS-01 challenge for wildcard certificates
  - "--certificatesresolvers.letsencrypt.acme.dnschallenge=true"
  - "--certificatesresolvers.letsencrypt.acme.dnschallenge.provider=gdom"
  - "--certificatesresolvers.letsencrypt.acme.dnschallenge.resolvers=8.8.8.8:53,1.1.1.1:53"

  # Fallback HTTP-01 for compatibility
  - "--certificatesresolvers.letsencrypt-http.acme.httpchallenge=true"
  - "--certificatesresolvers.letsencrypt-http.acme.httpchallenge.entrypoint=web"
```

### 2. Service Label Updates

**Wildcard Domain Specification:**
```yaml
labels:
  - "traefik.http.routers.service.tls.certresolver=letsencrypt"
  - "traefik.http.routers.service.tls.domains[0].main=*.markcheli.com"
  # or
  - "traefik.http.routers.service.tls.domains[0].main=*.ops.markcheli.com"
```

### 3. Environment Configuration

**Required .env Variables:**
```bash
# Google Domains DNS-01 Challenge
GOOGLE_DOMAINS_ACCESS_TOKEN=your_google_domains_access_token_here
```

## Setup Instructions

### Step 1: Generate Google Domains Access Token

1. Go to [Google Domains DNS](https://domains.google.com/registrar/markcheli.com/dns)
2. Navigate to DNS → Manage DNS API
3. Create a new access token with DNS modification permissions
4. Copy the token to your `.env` file

### Step 2: Deploy Wildcard SSL Configuration

Run the automated deployment script:

```bash
python3 scripts/deploy_wildcard_ssl.py
```

**Manual Deployment:**
```bash
# Deploy Traefik first
cd infrastructure/traefik
docker compose down && docker compose up -d

# Wait for DNS propagation (2-5 minutes)
sleep 300

# Deploy other services
cd ../personal-website
docker compose down && docker compose up -d

cd ../jupyter
docker compose down && docker compose up -d

cd ../opensearch
docker compose down && docker compose up -d
```

### Step 3: Verification

**Check Certificate Status:**
```bash
# View certificate information
python3 scripts/deploy_wildcard_ssl.py --cert-info

# Verify all services
python3 scripts/deploy_wildcard_ssl.py --verify-only

# Check Traefik logs
docker logs traefik | grep -i certificate
```

**Test SSL Endpoints:**
```bash
# Public services
curl -I https://www.markcheli.com
curl -I https://flask.markcheli.com

# LAN services (from local network)
curl -I https://traefik-local.ops.markcheli.com
curl -I https://jupyter.ops.markcheli.com
```

## Service Mapping

| Service | Domain | Type | Certificate |
|---------|---------|------|-------------|
| Website | www.markcheli.com | Public | *.markcheli.com |
| Flask API | flask.markcheli.com | Public | *.markcheli.com |
| Website Dev | www-dev.ops.markcheli.com | LAN | *.ops.markcheli.com |
| Traefik Dashboard | traefik-local.ops.markcheli.com | LAN | *.ops.markcheli.com |
| JupyterHub | jupyter.ops.markcheli.com | LAN | *.ops.markcheli.com |
| OpenSearch | opensearch-local.ops.markcheli.com | LAN | *.ops.markcheli.com |
| Logs Dashboard | logs-local.ops.markcheli.com | LAN | *.ops.markcheli.com |

## Troubleshooting

### Common Issues

**1. DNS Propagation Delays**
```bash
# Check DNS propagation
dig TXT _acme-challenge.markcheli.com

# Wait longer for DNS updates (up to 10 minutes)
```

**2. Google Domains Token Issues**
```bash
# Verify token permissions in Google Domains console
# Ensure token has DNS modification rights
```

**3. Certificate Generation Failures**
```bash
# Check Traefik logs
docker logs traefik | grep -i acme

# Clear certificate cache if needed
docker exec traefik rm /letsencrypt/acme.json
docker restart traefik
```

**4. Service Access Issues**
```bash
# Verify service labels
docker inspect SERVICE_NAME | grep -A 20 Labels

# Check Traefik routing
curl http://localhost:8080/api/http/routers
```

### Recovery Procedures

**Reset Certificates:**
```bash
# Stop all services
cd infrastructure/traefik
docker compose down

# Clear certificate storage
sudo rm -rf /home/mcheli/letsencrypt/*

# Restart Traefik
docker compose up -d

# Wait for certificate generation
sleep 300
```

**Fallback to HTTP-01:**
```yaml
# Temporarily use HTTP-01 resolver
labels:
  - "traefik.http.routers.service.tls.certresolver=letsencrypt-http"
```

## Monitoring

### Certificate Expiration

Wildcard certificates auto-renew 30 days before expiration. Monitor with:

```bash
# Check certificate expiration
docker exec traefik cat /letsencrypt/acme.json | jq '.letsencrypt.Certificates[] | {domain: .domain.main, expires: .certificate}'

# Set up monitoring alert
# Add to your monitoring system for certificate expiration dates
```

### Health Checks

```bash
# Daily SSL health check
python3 scripts/deploy_wildcard_ssl.py --verify-only

# Certificate renewal logs
docker logs traefik | grep -i renew
```

## Migration Notes

### From Individual Certificates

The migration automatically handles:
- ✅ Removing individual certificate requests
- ✅ Adding wildcard domain specifications
- ✅ Updating DNS challenge configuration
- ✅ Preserving all service routing

### Rollback Plan

If issues occur, rollback steps:
1. Revert Traefik configuration to HTTP-01 challenge
2. Remove wildcard domain specifications
3. Restart services individually
4. Wait for HTTP-01 certificates to generate

## Security Considerations

1. **Google Domains Token**: Store securely, rotate periodically
2. **DNS Access**: Minimal permissions (DNS modify only)
3. **Certificate Storage**: Secure `/home/mcheli/letsencrypt/` directory
4. **LAN Access**: Maintain IP allowlist middleware for internal services

## Future Enhancements

1. **Multiple DNS Providers**: Add Cloudflare DNS-01 as backup
2. **Certificate Monitoring**: Automated expiration alerts
3. **Automated Testing**: Regular SSL validation checks
4. **Documentation**: Service-specific SSL guides