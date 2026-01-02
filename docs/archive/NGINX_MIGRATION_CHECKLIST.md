# NGINX Migration Checklist

## Pre-Migration Preparation
- [ ] Backup current Traefik configuration
- [ ] Ensure all certificates are in place:
  - [ ] /etc/nginx/certs/wildcard-markcheli.crt
  - [ ] /etc/nginx/certs/wildcard-markcheli.key
  - [ ] /etc/nginx/certs/wildcard-ops-markcheli.crt
  - [ ] /etc/nginx/certs/wildcard-ops-markcheli.key
- [ ] Test NGINX configuration syntax
- [ ] Verify all upstreams are defined
- [ ] Confirm route coverage matches Traefik

## Migration Steps
1. [ ] Deploy NGINX alongside Traefik (different ports)
2. [ ] Test NGINX routing with temporary DNS entries
3. [ ] Validate SSL certificates work correctly
4. [ ] Test all service endpoints
5. [ ] Switch DNS to point to NGINX
6. [ ] Monitor for any issues
7. [ ] Remove Traefik containers

## Validation
- [ ] All public services accessible (*.markcheli.com)
- [ ] All LAN services accessible (*.ops.markcheli.com)
- [ ] SSL certificates working correctly
- [ ] WebSocket connections working (Jupyter, Home Assistant)
- [ ] API routing working correctly
- [ ] Security headers present

## Rollback Plan
- [ ] Keep Traefik containers stopped but available
- [ ] DNS change back to Traefik if needed
- [ ] Traefik restart procedure documented