# Cloudflare Domain Transfer Guide
**Complete guide for transferring markcheli.com and ops.markcheli.com from Squarespace to Cloudflare**

## 📋 Overview

This guide covers the complete process of:
1. Setting up Cloudflare account and DNS management
2. Transferring domain registration from Squarespace to Cloudflare
3. Configuring automated DNS management for infrastructure
4. Testing and validating the transfer

**⏱️ Timeline:** 7-14 days (due to domain transfer approval process)
**💰 Cost:** Domain transfer fee (~$10-15 per domain)

---

## 🎯 Phase 1: Cloudflare Account Setup

### Step 1: Create Cloudflare Account
1. **Sign up at**: https://www.cloudflare.com/
2. **Choose plan**: Free plan is sufficient for DNS management
3. **Verify email** and complete account setup

### Step 2: Add Domains to Cloudflare (DNS Only)
**Important**: Do NOT change nameservers yet - we're preparing for transfer

1. **Add markcheli.com**:
   - Dashboard → Add a Site → Enter `markcheli.com`
   - Choose "Free" plan
   - **SKIP** nameserver change for now

2. **Add ops.markcheli.com** (if it exists as separate domain):
   - Repeat process for ops.markcheli.com
   - Or configure as subdomain of markcheli.com

### Step 3: Generate API Tokens
1. **Go to**: My Profile → API Tokens → Create Token
2. **Use template**: "Custom token"
3. **Configure permissions**:
   ```
   Zone → Zone Settings → Read
   Zone → Zone → Read
   Zone → DNS → Edit
   Account → Account → Read
   ```
4. **Zone Resources**:
   - Include → Zone → markcheli.com
   - Include → Zone → ops.markcheli.com (if separate)
5. **Client IP filtering**: Optional (add your IP for security)
6. **TTL**: No expiration (or set to 1 year)
7. **Create token** and **save securely**

### Step 4: Configure Local Environment
```bash
# Add to .env file
CLOUDFLARE_API_TOKEN=your_api_token_here
CLOUDFLARE_EMAIL=your_cloudflare_email  # Optional for token auth

# Test authentication
source venv/bin/activate
python scripts/cloudflare_dns_manager.py test
```

---

## 🎯 Phase 2: DNS Record Migration

### Step 1: Backup Current DNS Records
```bash
# Export current DNS from Squarespace (manual process)
# 1. Login to Squarespace
# 2. Settings → Domains → markcheli.com → DNS
# 3. Screenshot or document all records

# Create backup using our tool (after transfer)
python scripts/cloudflare_dns_manager.py backup --file squarespace_backup.json
```

### Step 2: Import DNS Records to Cloudflare
Cloudflare should automatically scan and import most records, but verify:

**Public Records (markcheli.com)**:
- `www.markcheli.com` → A → `173.48.98.211`
- `flask.markcheli.com` → A → `173.48.98.211`
- `jupyter.markcheli.com` → A → `173.48.98.211`
- `ha.markcheli.com` → A → `173.48.98.211`

**LAN Records (ops.markcheli.com)**:
- `*.ops.markcheli.com` → A → `192.168.1.179`

**Add missing records**:
```bash
# Example: Add a missing record
python scripts/cloudflare_dns_manager.py create \
  --domain markcheli.com \
  --name www \
  --type A \
  --content 173.48.98.211
```

### Step 3: Test DNS Resolution (Before Nameserver Change)
```bash
# Test individual records
dig @1.1.1.1 www.markcheli.com A
dig @1.1.1.1 jupyter.markcheli.com A

# Test with Cloudflare's nameservers directly
dig @isla.ns.cloudflare.com www.markcheli.com A
```

---

## 🎯 Phase 3: Domain Transfer Process

### Step 1: Prepare for Transfer
**At Squarespace**:
1. **Unlock domain**: Domains → markcheli.com → Transfer Domain
2. **Disable privacy protection** (temporarily)
3. **Get auth code**: Request authorization code
4. **Verify admin email** is accessible

**At Cloudflare**:
1. **Domain registration**: Dashboard → Domain Registration → Transfer Domain
2. **Enter domain**: markcheli.com
3. **Enter auth code** from Squarespace
4. **Review pricing**: Confirm transfer fee
5. **Submit transfer request**

### Step 2: Transfer Authorization
**Timeline**: 5-7 days

1. **Admin email confirmation**: Check for transfer authorization email
2. **Approve transfer**: Click approval link in email
3. **Squarespace notification**: They have 5 days to release domain
4. **Monitor status**: Check Cloudflare dashboard for updates

### Step 3: Complete Transfer
Once transfer is approved:
1. **Verify ownership**: Domain shows as "Active" in Cloudflare
2. **Update nameservers**: Should happen automatically
3. **Test resolution**: All DNS should now resolve through Cloudflare

---

## 🎯 Phase 4: Infrastructure Integration

### Step 1: Integrate DNS Manager
```bash
# Sync all infrastructure DNS records
python scripts/cloudflare_dns_manager.py sync

# Verify all records are correct
python scripts/cloudflare_dns_manager.py list --domain markcheli.com
python scripts/cloudflare_dns_manager.py list --domain ops.markcheli.com
```

### Step 2: Update Infrastructure Manager
The DNS manager is designed to integrate with the infrastructure manager:

```bash
# Future integration - will be added to infrastructure_manager.py
python scripts/infrastructure_manager_new.py deploy --update-dns
```

### Step 3: Test Automated DNS Management
```bash
# Test creating a new service record
python scripts/cloudflare_dns_manager.py create \
  --domain ops.markcheli.com \
  --name test-service-local \
  --type A \
  --content 192.168.1.179

# Verify it was created
dig test-service-local.ops.markcheli.com A

# Clean up test record
python scripts/cloudflare_dns_manager.py delete \
  --domain ops.markcheli.com \
  --name test-service-local.ops.markcheli.com
```

---

## 🎯 Phase 5: Validation & Testing

### Step 1: Service Accessibility Test
```bash
# Test all public services
curl -I https://www.markcheli.com
curl -I https://flask.markcheli.com
curl -I https://jupyter.markcheli.com
curl -I https://ha.markcheli.com

# Test LAN services (from local network)
curl -I https://logs-local.ops.markcheli.com
curl -I https://grafana-local.ops.markcheli.com
```

### Step 2: DNS Propagation Validation
```bash
# Check global DNS propagation
dig @8.8.8.8 www.markcheli.com A        # Google DNS
dig @1.1.1.1 www.markcheli.com A        # Cloudflare DNS
dig @208.67.222.222 www.markcheli.com A # OpenDNS

# All should return the same result
```

### Step 3: Email & MX Records
**Important**: Verify email still works after transfer
- Test sending/receiving email
- Check MX records are correct
- Verify SPF/DKIM/DMARC records

---

## 🛡️ Safety Features

### Protected Records
The DNS manager includes safety features:

**Protected from deletion**:
- `@` (root domain)
- `www`
- `mail`
- `_dmarc`
- `_domainkey`
- Any record with MX, SPF, DKIM patterns

### Backup & Recovery
```bash
# Create backup before any changes
python scripts/cloudflare_dns_manager.py backup

# Restore if needed (dry run first)
python scripts/cloudflare_dns_manager.py restore --file backup.json --dry-run
python scripts/cloudflare_dns_manager.py restore --file backup.json
```

### Validation Checks
- IPv4/IPv6 address validation
- CNAME target validation
- MX record priority validation
- TTL range validation

---

## 🚨 Troubleshooting

### Transfer Issues
**Transfer pending too long**:
- Contact Squarespace support to expedite
- Check admin email for pending approvals
- Verify auth code is correct

**DNS not resolving**:
- Check nameservers: `dig NS markcheli.com`
- Verify records in Cloudflare dashboard
- Clear local DNS cache: `sudo dscacheutil -flushcache`

### Common Problems

**Email stops working**:
```bash
# Check MX records
dig MX markcheli.com

# Verify in Cloudflare dashboard
# Common fix: Re-add MX records if missing
```

**Website not accessible**:
```bash
# Check A records
dig www.markcheli.com A

# Verify in Cloudflare dashboard
# Check for "proxied" vs "DNS only" setting
```

**LAN services not working**:
- Verify local DNS resolution
- Check ops.markcheli.com subdomain setup
- Ensure LAN IPs are correct (192.168.1.179)

---

## 📋 Pre-Transfer Checklist

**Squarespace Preparation**:
- [ ] Document all current DNS records
- [ ] Unlock domain for transfer
- [ ] Disable privacy protection
- [ ] Obtain authorization code
- [ ] Verify admin email access

**Cloudflare Preparation**:
- [ ] Account created and verified
- [ ] API tokens generated and tested
- [ ] DNS records imported and validated
- [ ] Backup of current DNS created

**Infrastructure Preparation**:
- [ ] DNS manager script tested
- [ ] Integration with infrastructure manager planned
- [ ] Rollback procedure documented

---

## 📞 Emergency Contacts

**Squarespace Support**: 1-646-580-3456
**Cloudflare Support**: https://support.cloudflare.com/

**Rollback Plan**:
1. Contact Squarespace to reverse transfer (if within 5 days)
2. Update nameservers back to Squarespace
3. Restore original DNS configuration

---

## ✅ Success Criteria

Transfer is complete when:
- [ ] Domains show as "Active" in Cloudflare
- [ ] All DNS records resolve correctly
- [ ] All websites/services accessible
- [ ] Email functionality verified
- [ ] DNS manager script working
- [ ] Infrastructure automation tested

**Estimated completion**: 7-14 days from start of transfer process.