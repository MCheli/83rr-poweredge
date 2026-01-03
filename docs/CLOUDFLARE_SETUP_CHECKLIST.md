# Cloudflare Pro Security Setup Checklist

**Zone ID:** 8df53cc0d17bed0bcfc0ea23926f25c5
**Domain:** markcheli.com
**Plan:** Pro ($20/month)
**Date:** January 3, 2026

---

## Quick Setup Checklist

Follow these steps in order to enable all available Pro plan security features:

---

## ✅ Step 1: Enable Super Bot Fight Mode (5 minutes)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/bots

### Instructions:

1. **Navigate to Bot Management**
   - Click the link above or: Dashboard → markcheli.com → Security → Bots

2. **Enable Super Bot Fight Mode**
   - Toggle the switch to **ON** (should show "Pro" badge)

3. **Configure Bot Actions**

   **Definitely Automated:**
   - [ ] Set to: `Managed Challenge` ⭐ RECOMMENDED
   - This challenges obvious bots with a CAPTCHA

   **Likely Automated:**
   - [ ] Set to: `Managed Challenge` ⭐ RECOMMENDED
   - Or use `JavaScript Detection` for lighter challenge

   **Verified Bots:**
   - [ ] Set to: `Allow` ⭐ RECOMMENDED
   - Allows legitimate bots (Google, Bing, etc.)
   - Click "Configure" to customize which bots to allow

4. **Static Resource Protection (Optional)**
   - [ ] Toggle **ON** to protect images, CSS, JS from scraping
   - May slightly increase origin load

5. **Save Changes**
   - [ ] Click "Save" at the bottom

**✅ Done! Super Bot Fight Mode is now active.**

---

## ✅ Step 2: Deploy Cloudflare Managed Ruleset (WAF) (10 minutes)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/waf

### Instructions:

1. **Navigate to WAF**
   - Click the link above or: Dashboard → markcheli.com → Security → WAF

2. **Go to Managed Rules Tab**
   - Click on "Managed rules" in the top navigation

3. **Deploy Cloudflare Managed Ruleset**
   - Find "Cloudflare Managed Ruleset"
   - Click **"Deploy"** button (or "Configure" if already deployed)

4. **Initial Configuration (IMPORTANT - Start in Log Mode)**

   **Deployment Mode:**
   - [ ] Set to: `Log` ⭐ START HERE
   - This logs attacks without blocking (for testing)

   **Sensitivity Level:**
   - [ ] Set to: `Medium` ⭐ RECOMMENDED
   - Options: Low / Medium / High

5. **Save and Monitor**
   - [ ] Click "Deploy" or "Save"
   - [ ] Wait **24-48 hours** before proceeding to Step 3

**⏳ Wait 24-48 hours and monitor security events before switching to Block mode!**

---

## ✅ Step 3: Review Logs and Switch to Block Mode (After 24-48 hours)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/events

### Instructions:

1. **Review Security Events**
   - Click the link above or: Dashboard → Security → Events

2. **Check for False Positives**
   - Look for legitimate requests being logged
   - Filter by:
     - Service: "WAF"
     - Rule: "Cloudflare Managed Ruleset"

3. **If No False Positives Found:**
   - [ ] Go back to WAF → Managed rules
   - [ ] Click "Configure" on Cloudflare Managed Ruleset
   - [ ] Change mode from `Log` to `Block` ⭐
   - [ ] Save changes

4. **If False Positives Found:**
   - [ ] Click on the event to see which rule triggered
   - [ ] Disable that specific rule OR
   - [ ] Create a WAF exception for that path/IP
   - [ ] Then switch to Block mode

**✅ Cloudflare Managed Ruleset now actively blocking threats!**

---

## ✅ Step 4: Deploy OWASP Core Ruleset (WAF) (10 minutes)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/waf

### Instructions:

1. **Navigate to WAF → Managed Rules**
   - Same location as Step 2

2. **Deploy OWASP Core Ruleset**
   - Find "Cloudflare OWASP Core Ruleset"
   - Click **"Deploy"** button

3. **Initial Configuration (Start in Log Mode)**

   **Paranoia Level:**
   - [ ] Set to: `PL2` ⭐ RECOMMENDED (Medium protection)
   - Options: PL1 (Low) / PL2 (Medium) / PL3 (High) / PL4 (Maximum)

   **Score Threshold:**
   - [ ] Set to: `60` ⭐ DEFAULT (recommended)
   - Lower = more strict (e.g., 40)
   - Higher = less strict (e.g., 80)

   **Action:**
   - [ ] Set to: `Log` ⭐ START HERE
   - Options: Log / Block / Managed Challenge

4. **Save and Monitor**
   - [ ] Click "Deploy"
   - [ ] Wait **24-48 hours** before switching to Block

**⏳ Wait 24-48 hours and monitor security events!**

---

## ✅ Step 5: Review OWASP Logs and Activate (After 24-48 hours)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/events

### Instructions:

1. **Review Security Events**
   - Dashboard → Security → Events
   - Filter by Rule: "OWASP Core Ruleset"

2. **Check for False Positives**
   - Look for legitimate requests being flagged
   - Common false positives:
     - Admin panels
     - API endpoints
     - Form submissions

3. **If No False Positives:**
   - [ ] Go to WAF → Managed rules
   - [ ] Configure OWASP Core Ruleset
   - [ ] Change action from `Log` to `Block` ⭐
   - [ ] Save changes

4. **If False Positives:**
   - [ ] Review which OWASP rules triggered
   - [ ] Options:
     - Lower paranoia level (PL2 → PL1)
     - Increase score threshold (60 → 80)
     - Disable specific rules
     - Create WAF exception
   - [ ] Then switch to Block mode

**✅ OWASP Core Ruleset now protecting against OWASP Top 10!**

---

## ✅ Step 6: Additional Security Settings (Optional but Recommended)

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/ssl-tls

### SSL/TLS Settings:

1. **Navigate to SSL/TLS**
   - Dashboard → SSL/TLS → Overview

2. **Configure SSL Mode**
   - [ ] Set to: `Full (strict)` ⭐ REQUIRED
   - This validates your origin certificates

3. **Edge Certificates**
   - Click "Edge Certificates" tab
   - [ ] Enable: `Always Use HTTPS` ⭐
   - [ ] Enable: `Automatic HTTPS Rewrites` ⭐
   - [ ] Minimum TLS Version: `1.2` or `1.3` ⭐
   - [ ] Enable: `TLS 1.3` ⭐
   - [ ] Enable: `Opportunistic Encryption`

### Security Settings:

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/settings

1. **Security Level**
   - [ ] Set to: `High` ⭐ RECOMMENDED
   - Or `Medium` if you have many legitimate users

2. **Challenge Passage**
   - [ ] Set to: `30 minutes` ⭐
   - How long users stay validated after passing a challenge

3. **Browser Integrity Check**
   - [ ] Toggle: `ON` ⭐
   - Blocks requests from browsers without a valid user agent

---

## 📊 Monitoring Your Security

### View Security Events:

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/security/events

**What to Monitor:**

1. **Total Threats Blocked**
   - Check daily for first week
   - Look for unusual spikes

2. **Top Attack Types**
   - SQL injection
   - XSS (Cross-Site Scripting)
   - Bot attacks
   - Other web exploits

3. **False Positives**
   - Legitimate users being blocked
   - Look for patterns in:
     - URLs being blocked
     - Countries
     - User agents

4. **Bot Score Distribution**
   - See how bot traffic is classified
   - Adjust thresholds if needed

### Set Up Notifications (Recommended):

**Direct Link:** https://dash.cloudflare.com/8df53cc0d17bed0bcfc0ea23926f25c5/notifications

- [ ] Enable email notifications for:
  - Advanced DDoS Attack
  - HTTP DDoS Attack
  - WAF Weekly Summary

---

## 🧪 Testing Your Configuration

After everything is set up, test your security:

### Test Bot Detection:

```bash
# Should be challenged/blocked
curl -A "BadBot/1.0" https://www.markcheli.com/

# Should work fine
curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" https://www.markcheli.com/
```

### Test WAF Rules (when in Block mode):

```bash
# Test SQL injection (should be blocked)
curl "https://www.markcheli.com/?id=1' OR '1'='1"

# Test XSS (should be blocked)
curl "https://www.markcheli.com/?search=<script>alert('xss')</script>"

# Normal request (should work)
curl "https://www.markcheli.com/"
```

**Check results in:** Security → Events

---

## ✅ Final Checklist

### Immediate Setup (Do Now):
- [ ] Super Bot Fight Mode enabled
- [ ] Cloudflare Managed Ruleset deployed in **Log mode**
- [ ] OWASP Core Ruleset deployed in **Log mode**
- [ ] SSL set to Full (strict)
- [ ] Always Use HTTPS enabled
- [ ] Security Level set to High

### After 24-48 Hours:
- [ ] Reviewed security events for false positives
- [ ] Switched Cloudflare Managed Ruleset to **Block mode**
- [ ] Switched OWASP Core Ruleset to **Block mode**
- [ ] Configured email notifications

### Ongoing (Weekly):
- [ ] Check Security → Events dashboard
- [ ] Review attack trends
- [ ] Adjust rules if needed
- [ ] Monitor false positive reports

---

## 📋 Current Status

**Enabled Features:**
- [ ] Super Bot Fight Mode - Configured
- [ ] Cloudflare Managed Ruleset - Log Mode → Block Mode
- [ ] OWASP Core Ruleset (PL2) - Log Mode → Block Mode
- [ ] SSL/TLS Full (Strict)
- [ ] Always Use HTTPS
- [ ] Security Level: High

**Not Available (Enterprise Only):**
- ❌ Page Shield (requires $5,000+/month plan)

---

## 🆘 Troubleshooting

### Common Issues:

**1. Legitimate users being blocked**
- Check Security → Events for the blocked request
- See which rule triggered
- Options:
  - Create WAF exception for that path
  - Add IP to allowlist
  - Disable specific rule
  - Lower sensitivity/paranoia level

**2. API endpoints returning 403**
- Create WAF exception for /api/* paths
- Or adjust OWASP score threshold higher

**3. Admin panel blocked**
- Add your IP to IP Access Rules (allowlist)
- Or create WAF exception for /admin/*

**4. Too many challenges for real users**
- Lower Security Level from High to Medium
- Adjust bot score thresholds
- Change "Managed Challenge" to "JavaScript Detection"

---

## 🎯 Success Criteria

You'll know it's working when:

✅ Security → Events shows blocked attacks
✅ No legitimate users reporting access issues
✅ Bot traffic is being challenged appropriately
✅ Security score improves (check weekly summary emails)
✅ SQL injection and XSS attempts are blocked
✅ Search engine bots can still access your site

---

**Questions?** Check Cloudflare documentation or the full guide at `docs/CLOUDFLARE_PRO_SECURITY.md`

**Setup Time:** ~30 minutes + 24-48 hours monitoring
