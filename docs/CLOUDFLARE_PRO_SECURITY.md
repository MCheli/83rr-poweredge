# Cloudflare Pro Plan Security Configuration Guide

Complete guide to enabling all Pro plan security features for markcheli.com

**Last Updated:** January 3, 2026
**Plan:** Cloudflare Pro ($20/month)

---

## ✅ Features You CAN Enable (Pro Plan)

| Feature | Available | Configuration Required |
|---------|-----------|------------------------|
| **Super Bot Fight Mode** | ✅ YES | Manual (Dashboard) |
| **Cloudflare Managed Ruleset (WAF)** | ✅ YES | Manual (Dashboard) |
| **OWASP Core Ruleset (WAF)** | ✅ YES | Manual (Dashboard) |
| **Page Shield** | ❌ NO | Enterprise Only |

---

## 🚀 Quick Start

### Step 1: Run Automated Configuration

First, ensure you have your Zone ID in `.env`:

```bash
# Get Zone ID from: Cloudflare Dashboard → markcheli.com → Overview → Zone ID (right sidebar)
echo "CLOUDFLARE_ZONE_ID=your_zone_id_here" >> .env

# Run the Pro security configuration script
bash scripts/cloudflare_security_pro.sh
```

This script will automatically configure:
- ✅ High security level
- ✅ SSL/TLS strict mode
- ✅ Browser integrity checks
- ✅ HTTP/2 and HTTP/3
- ✅ TLS 1.3
- ✅ Automatic HTTPS rewrites
- ✅ And more basic settings

### Step 2: Manual Dashboard Configuration

The following features **require manual configuration** through the Cloudflare Dashboard:

---

## 1. Super Bot Fight Mode (Pro)

**What it does:** Detects and mitigates sophisticated bots using machine learning and behavioral analysis.

### Configuration Steps:

1. **Navigate to Bot Management**
   ```
   Cloudflare Dashboard → markcheli.com → Security → Bots
   ```

2. **Enable Super Bot Fight Mode**
   - Toggle **ON** the "Super Bot Fight Mode" switch
   - You'll see it's marked as "Pro" feature

3. **Configure Bot Detection**

   **Definitely Automated Traffic:**
   - Action: `Managed Challenge` (recommended)
   - This challenges obvious bots with a CAPTCHA

   **Likely Automated Traffic:**
   - Action: `Managed Challenge` (recommended)
   - Or use `JavaScript Detection` for lighter touch

   **Verified Bots:**
   - Action: `Allow` (recommended)
   - Allows legitimate bots like Googlebot, Bingbot
   - You can customize which verified bots to allow

4. **Optional: Static Resource Protection**
   - Toggle **ON** to protect images, CSS, JS from bot scraping
   - May slightly increase origin requests

5. **Configure Bot Score Threshold (Advanced)**
   - Click "Configure" under each category
   - Bot Score: 1-99 (lower = more likely bot)
   - Default thresholds are usually good:
     - Definitely Automated: < 30
     - Likely Automated: 30-99

### Recommended Settings for Your Setup:

```
✅ Super Bot Fight Mode: ON
✅ Definitely Automated: Managed Challenge
✅ Likely Automated: Managed Challenge
✅ Verified Bots: Allow
✅ Static Resource Protection: ON
```

---

## 2. Cloudflare Managed Ruleset (WAF)

**What it does:** Pre-configured security rules maintained by Cloudflare to block common attacks.

### Configuration Steps:

1. **Navigate to WAF**
   ```
   Cloudflare Dashboard → markcheli.com → Security → WAF → Managed Rules
   ```

2. **Deploy Cloudflare Managed Ruleset**
   - Click **"Deploy"** button on "Cloudflare Managed Ruleset"
   - Or if already deployed, click **"Configure"**

3. **Choose Deployment Mode**

   **For Initial Testing (Recommended):**
   - Mode: `Log` (logs attacks without blocking)
   - Sensitivity: `Medium`
   - Duration: 24-48 hours

   **After Testing:**
   - Mode: `Block` (blocks detected attacks)
   - Sensitivity: `Medium` or `High`

4. **Configure Rule Sensitivity**
   - **Low:** Fewer false positives, may miss some attacks
   - **Medium:** Balanced (recommended for most sites)
   - **High:** Maximum protection, may have more false positives

5. **Review and Customize Specific Rules (Optional)**
   - Click on the deployed ruleset
   - Review individual rules
   - You can disable specific rules if they cause false positives
   - Example: Disable "Block SQL injection" for `/api/sql-query` endpoint if needed

### Recommended Settings:

```
✅ Deployment: Enabled
✅ Mode: Log (test for 24-48h) → then Block
✅ Sensitivity: Medium
⚠️  Monitor logs before switching to Block mode
```

### Testing Process:

```bash
# Step 1: Deploy in Log mode
# Wait 24-48 hours

# Step 2: Review logs
# Dashboard → Security → Events
# Look for events tagged "Cloudflare Managed Ruleset"

# Step 3: Check for false positives
# Look for legitimate requests being flagged

# Step 4: Adjust rules if needed
# Disable specific rules causing false positives

# Step 5: Switch to Block mode
# Change mode from Log to Block
```

---

## 3. OWASP Core Ruleset (WAF)

**What it does:** Protection against OWASP Top 10 vulnerabilities (SQL injection, XSS, etc.)

### Configuration Steps:

1. **Navigate to WAF**
   ```
   Cloudflare Dashboard → markcheli.com → Security → WAF → Managed Rules
   ```

2. **Deploy OWASP Core Ruleset**
   - Click **"Deploy"** on "Cloudflare OWASP Core Ruleset"
   - Or click **"Configure"** if already deployed

3. **Set Paranoia Level (PL)**

   Paranoia levels determine how aggressive the rules are:

   - **PL1 (Low):** Basic protection, fewer false positives
   - **PL2 (Medium):** Good protection, balanced ⭐ **RECOMMENDED**
   - **PL3 (High):** Strong protection, may cause false positives
   - **PL4 (Maximum):** Maximum protection, likely false positives

4. **Configure Score Threshold**

   OWASP uses anomaly scoring:
   - Each triggered rule adds points
   - When total score exceeds threshold, action is taken
   - **Default: 60** (recommended starting point)
   - **Lower = more sensitive** (40-50 for stricter)
   - **Higher = less sensitive** (70-80 for looser)

5. **Choose Action**

   **For Initial Testing:**
   - Action: `Log`
   - Duration: 24-48 hours

   **After Testing:**
   - Action: `Block` or `Managed Challenge`

6. **Configure Specific Attack Categories (Optional)**

   You can adjust scores for specific attack types:
   - SQL Injection
   - Cross-Site Scripting (XSS)
   - Remote Code Execution (RCE)
   - Local File Inclusion (LFI)
   - Remote File Inclusion (RFI)
   - Session Fixation
   - Protocol Enforcement
   - And more...

### Recommended Settings:

```
✅ Deployment: Enabled
✅ Paranoia Level: PL2 (Medium)
✅ Score Threshold: 60
✅ Action: Log (test) → Block (production)
```

### Migration Path:

```
Phase 1 (Week 1):
  Paranoia Level: PL1
  Score Threshold: 60
  Action: Log

Phase 2 (Week 2):
  Paranoia Level: PL2
  Score Threshold: 60
  Action: Log
  (Review logs, check for false positives)

Phase 3 (Week 3):
  Paranoia Level: PL2
  Score Threshold: 60
  Action: Block
  (Production ready)
```

---

## 4. Page Shield (Enterprise Only)

**Status:** ❌ NOT AVAILABLE on Pro plan

**What it does:**
- Monitors third-party JavaScript
- Detects Magecart attacks
- Blocks malicious scripts
- Real-time JavaScript threat detection

**Requires:** Enterprise plan (~$5,000+/month)

### Free Alternative: Subresource Integrity (SRI)

If you're concerned about JavaScript security, you can manually implement SRI:

```html
<!-- Add integrity hashes to external scripts -->
<script
  src="https://cdn.example.com/library.js"
  integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/ux..."
  crossorigin="anonymous">
</script>
```

**Tools to generate SRI hashes:**
- https://www.srihash.org/
- `openssl dgst -sha384 -binary script.js | openssl base64 -A`

---

## 📊 Monitoring and Logs

### View Security Events

```
Dashboard → Security → Events
```

**Filter by:**
- Service: WAF, Bot Management, DDoS
- Action: Block, Challenge, Log
- Rule: Specific ruleset or rule
- Time range: Last hour, 24h, 7 days

### Key Metrics to Monitor:

1. **Total Threats Mitigated**
   - Shows blocked/challenged requests
   - Trend over time

2. **Top Threat Categories**
   - Which attack types are most common
   - SQL injection, XSS, bot attacks, etc.

3. **False Positives**
   - Legitimate requests being blocked
   - Look for patterns in:
     - User agents
     - IP addresses
     - Request paths
     - Countries

4. **Bot Score Distribution**
   - See how bot traffic is distributed
   - Adjust thresholds if needed

---

## 🧪 Testing Your Security Configuration

### Test WAF Rules:

```bash
# Test SQL injection detection
curl "https://www.markcheli.com/?id=1' OR '1'='1"

# Test XSS detection
curl "https://www.markcheli.com/?search=<script>alert('xss')</script>"

# Test bot detection
curl -A "BadBot/1.0" https://www.markcheli.com/

# Test with normal browser
curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" https://www.markcheli.com/
```

**Expected results when in Block mode:**
- SQL injection: Should be blocked (403 or challenge)
- XSS: Should be blocked
- Bad bot: Should be challenged
- Normal browser: Should work (200 OK)

### Check Firewall Events:

```
Dashboard → Security → Events
```

Look for your test requests and verify they were:
- Detected correctly
- Handled with appropriate action (Block/Challenge/Log)

---

## ⚠️ Troubleshooting

### Common Issues:

**1. False Positives Blocking Legitimate Traffic**

**Solution:**
```
1. Go to Security → Events
2. Find the blocked request
3. Click to see which rule triggered
4. Options:
   a. Disable that specific rule
   b. Add IP to IP Access Rules (allow list)
   c. Create WAF exception for that path
   d. Reduce sensitivity/paranoia level
```

**2. API Endpoints Being Blocked**

**Solution:**
```
Create WAF Exception:
1. Security → WAF → Managed Rules
2. Click on deployed ruleset
3. Add "Skip" rule for:
   - URI Path: /api/*
   - Or specific endpoints
```

**3. High Bot Challenge Rate on Legitimate Users**

**Solution:**
```
1. Security → Bots → Configure
2. Adjust bot score thresholds
3. Or change action from Challenge to JavaScript Detection
4. Add user agents to allow list
```

---

## 📋 Summary Checklist

Use this checklist to ensure everything is configured:

### Automated Configuration (via script):
- [ ] Run `scripts/cloudflare_security_pro.sh`
- [ ] Verify SSL set to "Full (strict)"
- [ ] Verify "Always Use HTTPS" enabled
- [ ] Verify TLS 1.2+ minimum

### Manual Dashboard Configuration:
- [ ] Enable Super Bot Fight Mode
- [ ] Configure bot detection actions (Managed Challenge)
- [ ] Allow verified bots (Google, Bing)
- [ ] Deploy Cloudflare Managed Ruleset (start in Log mode)
- [ ] Deploy OWASP Core Ruleset (PL2, score 60, start in Log mode)
- [ ] Monitor for 24-48 hours
- [ ] Review security events for false positives
- [ ] Switch WAF rules to Block mode

### Ongoing Monitoring:
- [ ] Check Security → Events weekly
- [ ] Review false positive reports
- [ ] Adjust rules as needed
- [ ] Keep paranoia level at PL2 (increase to PL3 if needed)

---

## 🔗 Useful Links

- **Security Dashboard:** https://dash.cloudflare.com/{zone-id}/security
- **Bot Management:** https://dash.cloudflare.com/{zone-id}/security/bots
- **WAF:** https://dash.cloudflare.com/{zone-id}/security/waf
- **Events Log:** https://dash.cloudflare.com/{zone-id}/security/events

- **Cloudflare Docs - Bot Management:** https://developers.cloudflare.com/bots/
- **Cloudflare Docs - WAF:** https://developers.cloudflare.com/waf/
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/

---

## 💡 Best Practices

1. **Always test in Log mode first** (24-48 hours minimum)
2. **Monitor security events** regularly
3. **Start with lower paranoia levels** (PL1 or PL2)
4. **Create exceptions** for known-good traffic patterns
5. **Document any custom rules** you create
6. **Review false positives** and adjust rules accordingly
7. **Keep an eye on bot scores** and adjust thresholds if needed

---

**Need help?** Check the Security Events log or contact Cloudflare support (available on Pro plan).
