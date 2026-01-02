# Infrastructure Modernization Plan
**Project**: 83RR PowerEdge Infrastructure Overhaul
**Status**: Planning Phase
**Date**: January 2026

## 🎯 Executive Summary
This document outlines a comprehensive modernization of the 83RR PowerEdge infrastructure to improve development workflow, security, and operational flexibility.

## 🔄 Major Changes Overview

### 1. Reverse Proxy Migration: Traefik → NGINX
**Current**: Traefik with dynamic configuration files
**Target**: NGINX Proxy Manager for simplified management

### 2. Domain Management Migration: Squarespace → Cloudflare
**Current**: Manual DNS management through Squarespace dashboard
**Target**: Automated DNS management via Cloudflare API

### 3. SSL Certificate Management Migration: Let's Encrypt Manual → Cloudflare
**Current**: Manual wildcard certificates with 90-day renewals
**Target**: Cloudflare SSL with automatic management

### 4. Deployment Architecture: SSH + Portainer → Native Docker Compose
**Current**: SSH-based deployment with Portainer API management
**Target**: Native Docker Compose with environment-aware configs (localhost for dev, server for prod)

---

## 📋 Detailed Requirements (DRAFT - Needs Clarification)

### 🌐 NGINX Migration Requirements
- [ ] Replace Traefik reverse proxy with core NGINX ✅ **CONFIRMED**
- [ ] Use configuration files for routing (similar to current Traefik approach)
- [ ] Maintain all existing routing and SSL termination
- [ ] Preserve current service accessibility patterns
- [ ] Convert Traefik dynamic config files to NGINX server blocks

### 🏷️ Cloudflare Domain Management Requirements
- [ ] Transfer full domain registration from Squarespace to Cloudflare ✅ **CONFIRMED**
- [ ] Enable Claude Code full DNS management via Cloudflare API ✅ **CONFIRMED**
- [ ] Maintain existing domain structure (markcheli.com, ops.markcheli.com)
- [ ] Implement safety checks to prevent accidental critical DNS deletion

### 🔒 Cloudflare SSL Requirements
- [ ] Replace manual Let's Encrypt certificates with Cloudflare Origin Certificates ✅ **CONFIRMED**
- [ ] Configure Full (Strict) SSL mode for maximum security ✅ **CONFIRMED**
- [ ] Eliminate 90-day manual renewal process (15-year Origin Certificates)
- [ ] Maintain wildcard certificate coverage
- [ ] Deploy Cloudflare Origin Certificates to server

### 🏗️ Native Docker Compose Deployment Requirements
- [ ] Remove Portainer entirely - use native Docker Compose commands ✅ **CONFIRMED**
- [ ] Support local development environment (localhost access)
- [ ] Support production deployment with Claude running directly on server ✅ **CONFIRMED**
- [ ] Environment-aware Docker Compose configurations (base + overrides)
- [ ] Automatic build and push to GitHub Container Registry for production ✅ **CONFIRMED**
- [ ] All services available locally for testing ✅ **CONFIRMED**
- [ ] Auto-detect environment based on hostname/context ✅ **CONFIRMED**
- [ ] Remove SSH dependency - Claude runs locally in each environment ✅ **CONFIRMED**

---

## ❓ Critical Clarifying Questions

### NGINX Migration
1. **NGINX Variant**: ✅ **ANSWERED** - Core NGINX with configuration files
2. **Migration Strategy**: Parallel deployment with gradual cutover, or direct replacement?
3. **Feature Parity**: Any Traefik features you want to ensure are preserved?

### Cloudflare Integration
4. **Domain Transfer**: Are you transferring domain registration to Cloudflare or just DNS management?
5. **API Permissions**: What level of DNS change automation should Claude have? (A records only, or full DNS management?)
6. **Safety Constraints**: Should there be safeguards against accidentally breaking critical DNS records?

### SSL Management
7. **Certificate Type**: Cloudflare Universal SSL (15-year) or Origin Certificates (15-year)?
8. **SSL Mode**: Full (strict), Full, Flexible, or Off?
9. **HSTS/Security**: Maintain current security headers and policies?

### Local/Remote Deployment
10. **Environment Detection**: How should the system determine if it's running in dev vs prod? (Environment variable, hostname, config file?)
11. **Service Subset**: Should all services run locally, or only core ones for development?
12. **Data Persistence**: How should local dev handle data persistence vs production data?
13. **Port Management**: Should local services use different ports than production, or the same?

### Infrastructure Management
14. **Backwards Compatibility**: Need to maintain SSH-based deployment during transition?
15. **Rollback Strategy**: How quickly do you need to be able to rollback to current architecture?
16. **Testing Strategy**: Preference for parallel testing environment vs staged deployment?

---

## ✅ REQUIREMENTS FINALIZED

### **Confirmed Decisions:**
1. **NGINX**: Core NGINX with configuration files
2. **Domain Transfer**: Full registration transfer to Cloudflare
3. **DNS Management**: Claude has full DNS management permissions
4. **Migration**: Direct replacement strategy
5. **Services**: All services available locally for testing
6. **SSL**: Full (Strict) mode with Cloudflare Origin Certificates
7. **Deployment**: Remove Portainer, use native Docker Compose
8. **Architecture**: Claude runs directly on server (no SSH), auto-build/push for production

### **Best Practice Implementations:**
- **Environment Detection**: Auto-detect based on hostname/context
- **Docker Compose**: Single base file + environment-specific overrides
- **Local Development**: Use localhost ports with Docker Compose override
- **Production**: Auto-build/push images, use production compose file

---

## 🎯 Success Criteria (DRAFT)

### Phase 1 Success
- [ ] Local development environment runs all services via localhost
- [ ] Production environment maintains current functionality
- [ ] Zero downtime migration path identified

### Phase 2 Success
- [ ] NGINX replaces Traefik with feature parity
- [ ] Cloudflare DNS management operational
- [ ] Claude can safely manage DNS records via API

### Phase 3 Success
- [ ] Cloudflare SSL replaces manual certificates
- [ ] Automated certificate management operational
- [ ] No manual SSL renewal required

### Final Success
- [ ] All services work in both local and production environments
- [ ] All manual DNS/SSL processes eliminated
- [ ] Infrastructure management simplified and automated

---

## 🚨 Risk Assessment & Mitigation

### High Risk Areas
1. **DNS Cutover**: Risk of service outage during DNS migration
2. **SSL Transition**: Potential certificate validation issues
3. **NGINX Migration**: Complex routing rules may not translate directly

### Mitigation Strategies
- [ ] Parallel infrastructure testing
- [ ] Staged migration with rollback points
- [ ] Comprehensive testing at each phase

---

## 📅 Next Steps
1. **Clarify Requirements**: Answer critical questions above
2. **Design Phase**: Create detailed technical specifications
3. **Implementation Planning**: Break down into manageable tasks
4. **Risk Assessment**: Identify and plan for potential issues

---

## 🚀 IMPLEMENTATION PLAN

### **Phase 1: Docker Compose Architecture Redesign (2-3 days)**
1. **Create new Docker Compose structure**
   - Single `docker-compose.yml` base configuration
   - `docker-compose.override.yml` for local development (auto-loaded)
   - `docker-compose.prod.yml` for production deployment
   - Environment-aware service definitions

2. **Implement environment detection**
   - Auto-detect based on hostname/context
   - `INFRASTRUCTURE_ENV=development|production`
   - Default to development when running locally

3. **Update deployment scripts**
   - Completely rewrite `infrastructure_manager.py` for native Docker Compose
   - Remove all Portainer API dependencies
   - Add auto-build and push functionality for production
   - Remove SSH deployment logic

### **Phase 2: Local Development Environment (1-2 days)**
1. **Create local development setup**
   - Configure `docker-compose.override.yml` for localhost access
   - Use local build contexts (current development code)
   - Setup development ports (8080, 8081, etc.)
   - Separate data volumes for local development

2. **Test local environment**
   - Verify all services run locally via `docker compose up`
   - Test service-to-service communication
   - Validate local development workflow

### **Phase 3: NGINX Migration (3-4 days)**
1. **Create NGINX configuration structure**
   - Convert Traefik dynamic configs to NGINX server blocks
   - Create `infrastructure/nginx/` directory with configs
   - Implement environment-aware NGINX configs
   - Setup SSL certificate handling

2. **Implement NGINX in Docker Compose**
   - Add NGINX service to docker-compose.yml
   - Configure local development routing (localhost)
   - Configure production routing (domains)
   - Test routing and SSL termination

3. **Direct cutover from Traefik**
   - Deploy NGINX via new Docker Compose system
   - Remove Traefik containers and configurations
   - Update DNS if needed for routing changes

### **Phase 4: Cloudflare Domain Transfer (1-2 weeks)**
**Note: This has external dependencies and timing**
1. **Setup Cloudflare account and API**
   - Create Cloudflare account
   - Generate API tokens with DNS management permissions
   - Create `scripts/cloudflare_dns_manager.py`

2. **Domain transfer process**
   - Initiate domain transfer from Squarespace to Cloudflare
   - Wait for transfer approval and completion
   - Verify all DNS records transferred correctly

3. **Integrate DNS management**
   - Add DNS management to `infrastructure_manager.py`
   - Implement safety checks to prevent critical record deletion
   - Test automated DNS record creation/updates

### **Phase 5: Cloudflare SSL Implementation (1 day)**
1. **Generate Origin Certificates**
   - Create wildcard certificates for `*.markcheli.com` and `*.ops.markcheli.com`
   - Download certificate files

2. **Deploy certificates**
   - Update NGINX configuration with Origin Certificates
   - Set Cloudflare SSL mode to Full (Strict)
   - Remove Let's Encrypt certificates and renewal scripts

3. **Validation and cleanup**
   - Test all HTTPS endpoints
   - Remove manual SSL renewal processes
   - Update documentation

### **Phase 6: Production Deployment & Legacy Cleanup (2-3 days)**
1. **Production deployment testing**
   - Test auto-build and push to GitHub Container Registry
   - Deploy directly on production server using new system
   - Verify all services work with domain routing

2. **Remove legacy systems**
   - **Remove Portainer entirely** (containers, configurations, scripts)
   - Remove all SSH-based deployment scripts
   - Clean up old Traefik configurations
   - Archive Squarespace DNS documentation

3. **Documentation and validation**
   - Update CLAUDE.md with new procedures
   - Create rollback procedures
   - Final end-to-end testing

---

## 📋 DETAILED TODO LIST

### **Docker Compose Architecture Redesign**
- [ ] Create single `docker-compose.yml` base configuration
- [ ] Create `docker-compose.override.yml` for local development
- [ ] Create `docker-compose.prod.yml` for production deployment
- [ ] Implement environment detection using hostname/context
- [ ] Completely rewrite `infrastructure_manager.py` for native Docker Compose
- [ ] Remove all Portainer API dependencies from scripts
- [ ] Add auto-build and push functionality for production deployments
- [ ] Remove SSH deployment logic from all scripts

### **Local Development Environment**
- [ ] Configure `docker-compose.override.yml` for localhost access
- [ ] Setup local build contexts for development code
- [ ] Configure development ports (8080, 8081, etc.)
- [ ] Create separate data volumes for local development
- [ ] Test all services locally via `docker compose up`
- [ ] Validate service-to-service communication in local environment
- [ ] Test local development workflow end-to-end

### **NGINX Migration & Configuration**
- [ ] Create `infrastructure/nginx/` directory structure
- [ ] Convert Traefik dynamic configs to NGINX server blocks
- [ ] Implement environment-aware NGINX configurations
- [ ] Add NGINX service to docker-compose.yml
- [ ] Configure local development routing (localhost)
- [ ] Configure production routing (domains)
- [ ] Setup SSL certificate handling in NGINX
- [ ] Test NGINX routing and SSL termination
- [ ] Perform direct cutover from Traefik to NGINX
- [ ] Remove Traefik containers and configurations

### **Cloudflare Integration**
- [ ] Create Cloudflare account and generate API tokens with DNS permissions
- [ ] Create `scripts/cloudflare_dns_manager.py`
- [ ] Implement DNS safety checks to prevent critical record deletion
- [ ] Integrate DNS management into `infrastructure_manager.py`
- [ ] Initiate domain transfer from Squarespace to Cloudflare
- [ ] Wait for domain transfer completion (external dependency)
- [ ] Verify DNS record transfer accuracy
- [ ] Test automated DNS record creation and updates

### **SSL Migration**
- [ ] Generate Cloudflare Origin Certificates (wildcard for both domains)
- [ ] Deploy Origin Certificates to NGINX configuration
- [ ] Update NGINX SSL configuration for Origin Certificates
- [ ] Set Cloudflare SSL mode to Full (Strict)
- [ ] Test all HTTPS endpoints with new certificates
- [ ] Remove Let's Encrypt certificates and renewal scripts

### **Production Deployment & Legacy Cleanup**
- [ ] Test auto-build and push to GitHub Container Registry
- [ ] Deploy directly on production server using new Docker Compose system
- [ ] Verify all services work with domain routing in production
- [ ] **Remove Portainer entirely** (containers, configurations, API scripts)
- [ ] Remove all SSH-based deployment scripts (`ssh_manager.py`, etc.)
- [ ] Remove `portainer_stack_manager.py` and related scripts
- [ ] Clean up old Traefik configurations and dynamic files
- [ ] Update CLAUDE.md with new native Docker Compose procedures
- [ ] Create rollback procedures for new architecture
- [ ] Archive Squarespace DNS documentation
- [ ] Final end-to-end testing of both local and production environments

---

## ⚠️ RISKS & ROLLBACK PLAN

### **High-Risk Operations**
1. **Docker Compose Architecture Change**: Complete deployment system overhaul
2. **Portainer Removal**: Loss of web-based container management
3. **DNS Cutover**: Domain transfer could cause temporary outages
4. **NGINX Direct Replacement**: No parallel system during cutover
5. **SSL Mode Change**: Could break existing connections

### **Rollback Procedures**
1. **Docker Compose → Portainer**:
   - Restore Portainer containers and API scripts
   - Redeploy using old `portainer_stack_manager.py`
   - Restore SSH-based deployment workflow

2. **NGINX → Traefik**:
   - Keep Traefik configs during transition
   - Redeploy Traefik containers via Docker Compose
   - Update DNS routing if needed

3. **DNS Issues**:
   - Use Cloudflare dashboard for immediate fixes
   - Keep Squarespace account active during transfer
   - Emergency DNS changes via Cloudflare API

4. **SSL Problems**:
   - Revert to Let's Encrypt certificates
   - Restore manual renewal scripts
   - Change Cloudflare SSL mode back to compatible setting

### **Safety Measures**
- **Backup all configurations** before changes (git commits)
- **Test thoroughly in local environment** before production deployment
- **Keep legacy scripts** until new system proven stable
- **Maintain parallel access** (keep Portainer running during Docker Compose testing)
- **Have emergency contacts** ready during DNS transfer
- **Preserve current SSL certificates** until Origin Certificates proven working
- **Document exact rollback steps** for each phase

---

*This implementation plan provides a structured approach to modernizing the infrastructure while minimizing downtime and risk.*