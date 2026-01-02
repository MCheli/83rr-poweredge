# Let's Encrypt SSL Certificates for Local Services

## Overview

This document describes the implementation of Let's Encrypt wildcard SSL certificates for **LAN-only services** (*.ops.markcheli.com) using Cloudflare DNS-01 challenge with automated renewal.

**Note**: Public services (*.markcheli.com) use Cloudflare Origin Certificates with 15-year validity and do not require Let's Encrypt.

## Problem Statement

The previous SSL configuration had several critical issues:

1. **Rate Limiting**: Multiple services requesting individual certificates triggered Let's Encrypt's rate limits
2. **LAN Domain Issues**: Internal services (*.ops.markcheli.com) couldn't complete HTTP-01 challenges
3. **DNS Provider Changes**: Google Domains was shut down, domain now managed by Squarespace
4. **Repeated Failures**: Failed challenges created a loop of retry attempts, worsening rate limits

## Solution: Manual Wildcard Certificates

### Benefits

- ✅ **No DNS API Required**: Works with any domain provider (Squarespace, etc.)
- ✅ **Single Certificate**: One wildcard cert covers all subdomains
- ✅ **No Rate Limits**: Eliminates individual domain certificate requests
- ✅ **LAN Compatibility**: Manual certs work for all services
- ✅ **Full Control**: Manual verification process, no automation failures

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                Manual Wildcard SSL Architecture                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Manual Certificate #1: *.markcheli.com                        │
│  ├── www.markcheli.com (public website)                        │
│  ├── flask.markcheli.com (public API)                          │
│  ├── jupyter.markcheli.com (public JupyterHub)                 │
│  └── ops.markcheli.com (whoami service)                        │
│                                                                 │
│  Manual Certificate #2: *.ops.markcheli.com                    │
│  ├── traefik-local.ops.markcheli.com (LAN-only)               │
│  ├── portainer-local.ops.markcheli.com (LAN-only)            │
│  ├── opensearch-local.ops.markcheli.com (LAN-only)            │
│  ├── logs-local.ops.markcheli.com (LAN-only)                  │
│  └── www-dev.ops.markcheli.com (LAN-only)                     │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Manual DNS Verification via Squarespace Domains               │
│  → Add TXT records manually during certificate acquisition     │
│  → No API access required                                       │
│  → Works with any DNS provider                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Traefik Configuration Changes

**File Provider for Manual Certificates:**
```yaml
volumes:
  - "/home/mcheli/traefik/dynamic:/etc/traefik/dynamic:ro"
  - "/home/mcheli/traefik/certs:/etc/traefik/certs:ro"

command:
  # File provider for certificate configuration
  - "--providers.file.directory=/etc/traefik/dynamic"
  - "--providers.file.watch=true"

  # HTTP-01 fallback (for single domains if needed)
  - "--certificatesresolvers.letsencrypt-http.acme.httpchallenge=true"
```

### 2. Dynamic Certificate Configuration

**dynamic/certificates.yml:**
```yaml
tls:
  certificates:
    - certFile: /etc/traefik/certs/wildcard-markcheli.crt
      keyFile: /etc/traefik/certs/wildcard-markcheli.key
    - certFile: /etc/traefik/certs/wildcard-ops-markcheli.crt
      keyFile: /etc/traefik/certs/wildcard-ops-markcheli.key
```

### 3. Service Label Updates

**Simplified TLS Configuration:**
```yaml
labels:
  - "traefik.http.routers.service.tls=true"
  # No certresolver needed - uses manual certificates
```

## Setup Instructions

### Step 1: Run Setup Script

The automated setup script guides you through the entire process:

```bash
./scripts/setup_manual_wildcard_ssl.sh
```

This will display the commands you need to run manually to obtain certificates.

### Step 2: Obtain Wildcard Certificates

**For *.markcheli.com (public services):**
```bash
sudo certbot certonly --manual --preferred-challenges dns \
  --email mpcheli7@gmail.com \
  --server https://acme-v02.api.letsencrypt.org/directory \
  --agree-tos \
  -d '*.markcheli.com' -d 'markcheli.com'
```

**For *.ops.markcheli.com (LAN services):**
```bash
sudo certbot certonly --manual --preferred-challenges dns \
  --email mpcheli7@gmail.com \
  --server https://acme-v02.api.letsencrypt.org/directory \
  --agree-tos \
  -d '*.ops.markcheli.com'
```

### Step 3: DNS Verification Process

During each certbot command:

1. **TXT Record Creation**: certbot will ask you to create a TXT record
2. **DNS Management**: Go to [Squarespace Domains](https://domains.squarespace.com)
3. **Add TXT Record**: Add the record exactly as instructed by certbot
4. **Wait for Propagation**: Use `dig TXT _acme-challenge.markcheli.com` to verify
5. **Continue**: Press Enter in certbot to continue verification

### Step 4: Install Certificates

After obtaining both certificates:

```bash
./scripts/setup_manual_wildcard_ssl.sh --install
```

### Step 5: Deploy Services

```bash
./scripts/setup_manual_wildcard_ssl.sh --deploy
```

### Step 6: Test SSL Functionality

```bash
./scripts/setup_manual_wildcard_ssl.sh --test
```

## Certificate Management

### Directory Structure

```
/home/mcheli/traefik/
├── certs/
│   ├── wildcard-markcheli.crt
│   ├── wildcard-markcheli.key
│   ├── wildcard-ops-markcheli.crt
│   └── wildcard-ops-markcheli.key
└── dynamic/
    └── certificates.yml
```

### Certificate Renewal

Wildcard certificates are valid for 90 days. **IMPORTANT**: Current certificates expire approximately 90 days after initial setup.

**Manual Renewal Process (Required every 90 days):**
1. **Run renewal command for first wildcard:**
   ```bash
   sudo certbot certonly --manual --preferred-challenges dns \
     --email mpcheli7@gmail.com \
     --server https://acme-v02.api.letsencrypt.org/directory \
     --agree-tos \
     -d '*.markcheli.com' -d 'markcheli.com'
   ```

2. **Run renewal command for second wildcard:**
   ```bash
   sudo certbot certonly --manual --preferred-challenges dns \
     --email mpcheli7@gmail.com \
     --server https://acme-v02.api.letsencrypt.org/directory \
     --agree-tos \
     -d '*.ops.markcheli.com'
   ```

3. **Complete DNS verification for each certificate** (as described in Step 3 above)

4. **Install updated certificates:**
   ```bash
   ./scripts/setup_manual_wildcard_ssl.sh --install
   ```

5. **Deploy services with new certificates:**
   ```bash
   ./scripts/setup_manual_wildcard_ssl.sh --deploy
   ```

**Set Calendar Reminder:**
- Create calendar reminder 30 days before expiration
- Allow 1-2 hours for renewal process including DNS propagation

## Service Mapping

| Service | Domain | Type | Certificate |
|---------|---------|------|-------------|
| Website | www.markcheli.com | Public | *.markcheli.com |
| Flask API | flask.markcheli.com | Public | *.markcheli.com |
| Website Dev | www-dev.ops.markcheli.com | LAN | *.ops.markcheli.com |
| Traefik Dashboard | traefik-local.ops.markcheli.com | LAN | *.ops.markcheli.com |
| JupyterHub | jupyter.markcheli.com | Public | *.markcheli.com |
| OpenSearch | opensearch-local.ops.markcheli.com | LAN | *.ops.markcheli.com |
| Logs Dashboard | logs-local.ops.markcheli.com | LAN | *.ops.markcheli.com |

## Troubleshooting

### Common Issues

**1. DNS Propagation Delays**
```bash
# Check if TXT record is visible
dig TXT _acme-challenge.markcheli.com

# Wait for propagation (usually 5-15 minutes)
```

**2. Certificate Not Found**
```bash
# Check if certificates were created
sudo ls -la /etc/letsencrypt/live/

# Verify certificate validity
openssl x509 -in /etc/letsencrypt/live/markcheli.com/fullchain.pem -text -noout
```

**3. Permission Issues**
```bash
# Fix certificate permissions
sudo chown $USER:$USER /home/mcheli/traefik/certs/*.crt
sudo chown $USER:$USER /home/mcheli/traefik/certs/*.key
sudo chmod 644 /home/mcheli/traefik/certs/*.crt
sudo chmod 600 /home/mcheli/traefik/certs/*.key
```

**4. Traefik Not Loading Certificates**
```bash
# Check dynamic configuration
docker exec traefik cat /etc/traefik/dynamic/certificates.yml

# Restart Traefik
cd infrastructure/traefik
docker compose restart
```

### Recovery Procedures

**Reset Everything:**
```bash
# Stop all services
docker compose -f infrastructure/traefik/docker-compose.yml down
docker compose -f infrastructure/personal-website/docker-compose.yml down

# Clear certificate directories
sudo rm -rf /home/mcheli/traefik/certs/*
sudo rm -rf /home/mcheli/traefik/dynamic/*

# Start over with setup script
./scripts/setup_manual_wildcard_ssl.sh
```

## Advantages vs Automated DNS-01

### Manual Approach Benefits:
- ✅ **Works with any DNS provider** (no API required)
- ✅ **No rate limiting failures** due to API issues
- ✅ **Full control** over the verification process
- ✅ **No dependency** on external API uptime
- ✅ **Works immediately** without provider setup

### Considerations:
- ⚠️  **Manual renewal process** (every 60-90 days)
- ⚠️  **Requires DNS access** during renewal
- ⚠️  **More steps** during initial setup

## Security Considerations

1. **Certificate Storage**: Secure `/home/mcheli/traefik/certs/` directory
2. **File Permissions**: Private keys have 600 permissions
3. **DNS Access**: Secure access to Squarespace Domains account
4. **Renewal Reminders**: Set up calendar reminders for renewals
5. **LAN Access**: Maintain IP allowlist middleware for internal services

## Migration Notes

### From DNS-01 Automated Approach

The migration automatically handles:
- ✅ Removing DNS provider dependencies
- ✅ Updating Traefik configuration for file-based certificates
- ✅ Maintaining all service routing
- ✅ Preserving security headers and middleware

### Benefits Over Previous Setup:
- No more Let's Encrypt rate limiting due to failed API calls
- No dependency on Google Domains (now defunct)
- Works with Squarespace Domains or any other provider
- Simpler troubleshooting (manual verification process)

This manual approach provides a reliable, provider-independent solution for wildcard SSL certificates that eliminates the rate limiting issues you were experiencing.