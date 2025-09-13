# SSH Session Management

## Critical Infrastructure Limitation

**⚠️ IMPORTANT: This server has a maximum limit of 2 concurrent SSH sessions.**

This limitation affects all deployment operations and remote management tasks. Exceeding this limit will cause connection failures and deployment errors.

## SSH Session Guidelines

### 1. Deployment Operations

**✅ DO:**
- Use `scripts/deploy_all_services.py` for sequential deployments
- Wait for each deployment to complete before starting another
- Use single SSH connections that properly close
- Monitor SSH session usage before running operations

**❌ DON'T:**
- Run multiple deployment scripts simultaneously
- Keep SSH connections open unnecessarily
- Run parallel operations that require SSH
- Use interactive SSH sessions during deployments

### 2. Script Compliance

All SSH-related scripts have been updated to respect session limits:

#### `scripts/deploy_via_ssh.py`
- ✅ Uses exactly 1 SSH session per deployment
- ✅ Includes proper connection timeouts
- ✅ Automatically closes sessions on completion
- ✅ Includes connection cleanup in error cases

#### `scripts/deploy_all_services.py` (NEW)
- ✅ Deploys services sequentially to avoid conflicts
- ✅ Waits for service stabilization between deployments
- ✅ Includes SSH connectivity verification
- ✅ Provides comprehensive deployment status

#### `scripts/setup_manual_wildcard_ssl.sh`
- ✅ Minimizes SSH usage
- ✅ Focuses on local certificate management
- ✅ Uses SSH only for final verification steps

## Usage Patterns

### Single Service Deployment
```bash
# Uses 1 SSH session, properly closed
python3 scripts/deploy_via_ssh.py traefik infrastructure/traefik/docker-compose.yml
```

### All Services Deployment (Recommended)
```bash
# Sequential deployment with session management
python3 scripts/deploy_all_services.py
```

### Service Verification Only
```bash
# Check status without deployment
python3 scripts/deploy_all_services.py --verify-only
```

## Monitoring SSH Sessions

### Check Current Sessions
```bash
# From another terminal or local access
who
# or
ss -t state established '( dport = :22 or sport = :22 )'
```

### Session Limit Troubleshooting

**If you encounter "Connection refused" errors:**

1. **Check active sessions:**
   ```bash
   # From server console or local access
   who | grep ssh
   ```

2. **Wait for sessions to close:**
   - Deployment scripts automatically close sessions
   - Wait 30-60 seconds between operations
   - Kill stuck processes if necessary

3. **Use sequential operations:**
   ```bash
   # Wait for completion
   python3 scripts/deploy_via_ssh.py service1 path1

   # Only then start next deployment
   python3 scripts/deploy_via_ssh.py service2 path2
   ```

## Connection Configuration

### SSH Client Settings

All scripts now use optimized SSH settings:

```bash
ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 user@host
```

**Settings explained:**
- `ConnectTimeout=30`: Fail quickly if server unavailable
- `ServerAliveInterval=10`: Detect broken connections
- Automatic session cleanup on completion

### SCP File Transfer

File transfers use separate, short-lived connections:

```bash
scp -o ConnectTimeout=30 file user@host:/path
```

## Best Practices

### 1. Deployment Workflow

**Recommended sequence:**
1. Plan deployments in advance
2. Use `deploy_all_services.py` for comprehensive updates
3. Monitor SSH session usage
4. Verify services after deployment
5. Test SSL endpoints

### 2. Emergency Access

**If SSH sessions are exhausted:**
- Use server console/KVM access if available
- Wait for automatic session timeout (typically 5-10 minutes)
- Kill stuck SSH processes via console
- Restart SSH service as last resort: `sudo systemctl restart ssh`

### 3. Development Workflow

**For active development:**
- Use local development environment when possible
- Batch deployment operations
- Test locally before remote deployment
- Use verification scripts to check status without deployments

## Script Updates Made

### Enhanced Connection Management

1. **Timeout Settings**: All SSH connections have 30s timeout
2. **Connection Cleanup**: Explicit session termination
3. **Error Handling**: Proper cleanup on failures
4. **Sequential Processing**: No parallel SSH operations

### New Features

1. **Deployment Orchestrator**: `deploy_all_services.py`
   - Manages service deployment order
   - Respects SSH session limits
   - Includes health verification
   - SSL certificate testing

2. **Enhanced Monitoring**:
   - Connection status checks
   - Service health verification
   - SSL endpoint testing
   - Container status reporting

## Migration Notes

### From Parallel to Sequential

**Before (caused session limit issues):**
```bash
# Multiple simultaneous SSH connections - DON'T DO THIS
python3 deploy_via_ssh.py traefik ... &
python3 deploy_via_ssh.py website ... &
python3 deploy_via_ssh.py jupyter ... &
```

**After (respects session limits):**
```bash
# Single orchestrated deployment - RECOMMENDED
python3 scripts/deploy_all_services.py
```

### Legacy Script Compatibility

All existing scripts maintain compatibility while adding session management:
- Same command-line interfaces
- Same functionality
- Enhanced reliability
- Better error handling

This SSH session management ensures reliable deployments and prevents infrastructure access issues caused by connection limit exceeded errors.