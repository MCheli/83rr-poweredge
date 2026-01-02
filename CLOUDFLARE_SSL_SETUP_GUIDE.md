# Cloudflare SSL Configuration Guide

## ✅ Completed Setup

### Phase 5: Origin Certificates ✅
- **Wildcard Certificate for Public Services**: `*.markcheli.com` + `markcheli.com`
  - Certificate ID: `57932496887940500718799605873764947555957152569`
  - Valid until: 2040-12-29 (15 years)
  - Deployed to: `/etc/nginx/certs/wildcard-markcheli.{crt,key}`

- **Wildcard Certificate for LAN Services**: `*.ops.markcheli.com`
  - Certificate ID: `564973495528215771177954808559044565960719640986`
  - Valid until: 2040-12-29 (15 years)
  - Deployed to: `/etc/nginx/certs/wildcard-ops-markcheli.{crt,key}`

### NGINX Configuration ✅
- All 14 services configured to use appropriate wildcard certificates
- Public services use: `wildcard-markcheli.{crt,key}`
- LAN services use: `wildcard-ops-markcheli.{crt,key}`
- Certificates mounted in Docker container at `/etc/nginx/certs/`

## 🔄 Manual Step Required

### SSL Mode Configuration
**Current Status**: SSL mode is set to "Full" (encrypts but doesn't validate certificates)
**Required**: Change to "Full (Strict)" to validate Origin Certificates

#### Option 1: Manual Configuration (Recommended)
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your domain: `markcheli.com`
3. Go to **SSL/TLS** tab
4. Set **SSL/TLS encryption mode** to **Full (strict)**
5. Enable **Always Use HTTPS** (under Edge Certificates)
6. Set **Minimum TLS Version** to **1.2** (recommended)

#### Option 2: API Token Update (Advanced)
If you prefer to use the scripts, update your Cloudflare API token permissions:

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Edit your current token
3. Add permission: **Zone:Zone Settings:Edit**
4. Run: `python scripts/cloudflare_ssl_manager.py configure-ssl`

## 🚀 Next Steps

### Phase 6: Testing and Validation
1. **Start Infrastructure**: Deploy with Origin Certificates
2. **Test HTTPS Endpoints**: Verify all services work with new certificates
3. **Remove Let's Encrypt Dependencies**: Clean up old certificate management
4. **Validate Security**: Confirm Full (Strict) SSL mode is working

### Commands to Run
```bash
# Test certificate validation
python scripts/cloudflare_ssl_manager.py validate

# Check current SSL mode
python scripts/cloudflare_ssl_manager.py ssl-mode

# Deploy infrastructure with new certificates
python scripts/infrastructure_manager_new.py deploy-local  # for testing

# Full production deployment
python scripts/infrastructure_manager_new.py deploy-production --build-push
```

## 🔐 Security Benefits

### With Origin Certificates + Full (Strict):
- ✅ **End-to-End Encryption**: Traffic encrypted from visitors to your server
- ✅ **Certificate Validation**: Cloudflare validates your server's certificate
- ✅ **15-Year Validity**: No need for frequent certificate renewals
- ✅ **Wildcard Coverage**: Covers all current and future subdomains
- ✅ **Production Ready**: Enterprise-grade SSL configuration

### Previous Setup Issues Resolved:
- ❌ ~~Let's Encrypt 90-day renewals~~
- ❌ ~~Manual certificate management~~
- ❌ ~~Self-signed certificate warnings~~
- ❌ ~~Traefik ACME challenges~~
- ❌ ~~Certificate storage complexity~~

## 📋 Certificate Management

### Useful Commands
```bash
# List existing certificates
python scripts/cloudflare_ssl_manager.py list

# Create new certificate (if needed)
python scripts/cloudflare_ssl_manager.py create --hostnames "service.markcheli.com"

# Revoke certificate (if needed)
python scripts/cloudflare_ssl_manager.py revoke --cert-id <certificate_id>

# Validate local certificate files
python scripts/cloudflare_ssl_manager.py validate
```

### Certificate File Structure
```
infrastructure/nginx/certs/
├── wildcard-markcheli.crt      # Public services certificate
├── wildcard-markcheli.key      # Public services private key
├── wildcard-ops-markcheli.crt  # LAN services certificate
├── wildcard-ops-markcheli.key  # LAN services private key
├── fullchain.pem               # NGINX-compatible cert (latest)
├── privkey.pem                 # NGINX-compatible key (latest)
└── certificate_info.json       # Certificate metadata
```

## 🎯 Success Criteria

Infrastructure will be considered fully migrated when:

1. ✅ Origin Certificates generated and deployed
2. ✅ NGINX configured to use Origin Certificates
3. ⏳ SSL mode set to Full (Strict)
4. ⏳ All HTTPS endpoints return 200 status
5. ⏳ Let's Encrypt dependencies removed
6. ⏳ Full infrastructure deployment tested

**Current Progress: 3/6 complete** 🏗️