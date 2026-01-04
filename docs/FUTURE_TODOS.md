# Future Development & Maintenance TODOs

*Last Updated: January 2, 2026*

This document provides a prioritized todo list for future development and improvements to the homelab infrastructure.

---

## 🚨 CRITICAL MAINTENANCE (High Priority)

### Let's Encrypt Certificate Monitoring
- **Action**: Monitor Let's Encrypt certificate auto-renewal for `*.ops.markcheli.com`
- **Schedule**: Certificates expire every 90 days
- **Current Setup**: Auto-renewal via cron (daily at 3:00 AM)
- **Verification**: `cat ~/letsencrypt/logs/renewal.log`
- **Manual Renewal**: `bash scripts/renew-letsencrypt-certs.sh`
- **Calendar Reminder**: Set reminder 30 days before expiration for verification

### Cloudflare Origin Certificates
- **Status**: ✅ Valid until 2040 (no action required for 14+ years)
- **Location**: `infrastructure/nginx/certs/wildcard-markcheli.{crt,key}`

---

## 🔧 CODE QUALITY & BEST PRACTICES (Medium-High Priority)

### Testing Framework
- **Current**: No automated tests for infrastructure
- **Goal**: Automated testing for NGINX configuration and service health
- **Actions**:
  - Create health check test suite for all services
  - Add NGINX configuration validation tests
  - Implement integration tests for service communication
  - Add SSL certificate expiration monitoring

### Configuration Management
- **Issue**: Some configuration values scattered across files
- **Action**: Centralize configuration
- **Files to create**:
  - `config/services.yaml` - Service definitions and health checks
  - `config/monitoring.yaml` - Monitoring thresholds and alerts
- **Benefits**: Easier updates, single source of truth

### Documentation Updates
- **Action**: Keep documentation synchronized with infrastructure changes
- **Files to maintain**:
  - CLAUDE.md - Update when deployment methods change
  - DEPLOYMENT_STATUS.md - Update when services added/removed
  - README.md - Keep current with architecture changes

---

## 🏗️ ARCHITECTURE & INFRASTRUCTURE (Medium Priority)

### Service Enhancements

**JupyterHub Multi-User Mode** (Optional):
- **Current**: Standalone JupyterLab (single user)
- **Future**: JupyterHub for multi-user support
- **Impact**: Non-critical, standalone mode is fully functional
- **Considerations**: Would require authentication setup, user management

**Personal Website Enhancements**:
- **Actions**:
  - Add more terminal commands and Easter eggs
  - Integrate with additional services
  - Add analytics/visitor tracking (privacy-respecting)

**Minecraft Server Optimization**:
- **Actions**:
  - Configure resource limits based on player activity
  - Add backup automation for world data
  - Implement automated restart schedule
  - Add performance monitoring

### Backup System Enhancement
- **Current**: Manual Docker volume backups
- **Goal**: Automated backup strategy
- **Actions**:
  - Automate database and volume backups
  - Implement off-site backup sync (rclone to cloud storage)
  - Create backup verification and restoration testing
  - Add retention policies and cleanup automation
  - Schedule: Daily backups with 30-day retention

### Alerting System
- **Current**: Grafana dashboards for monitoring
- **Goal**: Proactive alerting for infrastructure issues
- **Actions**:
  - Configure Prometheus Alertmanager
  - Add webhook integrations (email, Slack, Discord)
  - Create alert escalation procedures
  - Document on-call procedures and runbooks

---

## 📚 DOCUMENTATION (Medium Priority)

### Service-Specific Documentation
- **Goal**: Comprehensive guides for each service
- **Actions**:
  - Document common operations for each service
  - Create troubleshooting guides
  - Add configuration examples
  - Document backup/restore procedures

### Architecture Documentation
- **Files to create**:
  - `docs/ARCHITECTURE.md` - System design and data flows
  - `docs/RUNBOOKS.md` - Operational procedures
  - `docs/TROUBLESHOOTING.md` - Step-by-step issue resolution

### Code Examples & Templates
- **Goal**: Standardize new service addition
- **Actions**:
  - Create `templates/service-template/` directory
  - Add example NGINX server blocks
  - Document labeling conventions
  - Create docker-compose.yml template

---

## 🔐 SECURITY & COMPLIANCE (Medium-Low Priority)

### Security Hardening
- **Actions**:
  - Implement regular security scanning for container images
  - Add fail2ban or similar intrusion detection
  - Create security audit checklist
  - Review and update IP allowlists regularly
  - Implement secret rotation procedures

### Authentication Improvements
- **Current**: Basic authentication for some services
- **Future**: Centralized authentication
- **Options**:
  - OAuth2 proxy for all services
  - Authelia for unified authentication
  - LDAP integration for user management

### Compliance & Governance
- **Actions**:
  - Create CHANGELOG.md with semantic versioning
  - Implement pre-commit hooks for code quality
  - Add security.md with vulnerability reporting process
  - Document data retention policies

---

## ⚡ PERFORMANCE & OPTIMIZATION (Low Priority)

### Container Optimization
- **Actions**:
  - Review and optimize Docker image sizes
  - Implement multi-stage builds where applicable
  - Add container resource limits and requests
  - Optimize NGINX caching strategies

### Network Performance
- **Actions**:
  - Implement HTTP/3 support in NGINX
  - Add caching strategies for static content
  - Optimize NGINX worker processes and connections
  - Monitor and tune container network performance

### Monitoring Optimization
- **Actions**:
  - Optimize Prometheus metric retention
  - Add custom metrics for application performance
  - Create detailed performance dashboards in Grafana
  - Implement distributed tracing (optional)

---

## 🧪 TESTING & QUALITY ASSURANCE (Low Priority)

### Automated Testing
- **Files to create**:
  - `tests/test_deployment.py` - Docker Compose validation
  - `tests/test_health_checks.py` - Service health validation
  - `tests/test_integration.py` - End-to-end service testing
  - `tests/test_ssl.py` - SSL certificate validation

### Validation Framework
- **Actions**:
  - Create NGINX configuration validation scripts
  - Add network connectivity testing
  - Implement SSL certificate expiration monitoring
  - Create load testing procedures for critical services

---

## 📊 MONITORING & OBSERVABILITY (Enhancement)

### Advanced Monitoring
- **Current**: Prometheus + Grafana + cAdvisor
- **Future Enhancements**:
  - Add application-level metrics to custom services
  - Implement distributed tracing (Jaeger/Zipkin)
  - Enhanced OpenSearch log analysis with ML
  - Create custom alerting rules

### Dashboard Improvements
- **Actions**:
  - Create service-specific Grafana dashboards
  - Add custom panels for business metrics
  - Implement log correlation with metrics
  - Add capacity planning dashboards

---

## 🔄 MAINTENANCE & OPERATIONS

### Regular Maintenance Tasks
- **Weekly**:
  - Review service logs for errors
  - Check disk space usage
  - Verify backup completion
  - Review Grafana dashboards for anomalies

- **Monthly**:
  - Update Docker images for security patches
  - Review and rotate secrets/credentials
  - Verify SSL certificate status
  - Review resource usage trends

- **Quarterly**:
  - Full infrastructure health audit
  - Review and update documentation
  - Performance baseline review
  - Disaster recovery drill

### Disaster Recovery
- **Actions**:
  - Document full system restoration procedures
  - Create infrastructure-as-code for rapid rebuild
  - Test backup restoration procedures
  - Document emergency contact procedures
  - Create network configuration backup

---

## 📅 IMPLEMENTATION PRIORITY

### Phase 1 (Next 1-2 Months)
1. ✅ Complete documentation updates (in progress)
2. Implement automated backup system
3. Add health check test suite
4. Configure Prometheus Alertmanager

### Phase 2 (Next 3-6 Months)
1. Create architecture and runbook documentation
2. Implement security hardening measures
3. Add centralized authentication
4. Optimize container resource usage

### Phase 3 (Next 6-12 Months)
1. Advanced monitoring and tracing
2. Performance optimization
3. Disaster recovery testing
4. JupyterHub multi-user mode (if needed)

### Phase 4 (Ongoing)
1. Regular security updates
2. Documentation maintenance
3. Performance monitoring
4. Capacity planning

---

## 🎯 QUICK WINS FOR NEXT SESSION

These items can be completed quickly and provide immediate value:

1. **Archive completed migration documentation** (1 hour)
   - Move INFRASTRUCTURE_MODERNIZATION_PLAN.md, NGINX_MIGRATION_CHECKLIST.md to docs/archive/

2. **Create backup automation script** (2-3 hours)
   - Automated daily backups for critical volumes
   - Retention policy implementation
   - Backup verification

3. **Add SSL expiration monitoring** (1 hour)
   - Script to check Let's Encrypt certificate expiration
   - Email alerts for certificates expiring soon

4. **Create service health dashboard** (2 hours)
   - Grafana dashboard showing all service health
   - HTTP endpoint monitoring
   - Container status visualization

5. **Document common operations** (2 hours)
   - Quick reference guide for service management
   - Common troubleshooting procedures
   - Emergency procedures documentation

---

## ✅ COMPLETED ITEMS

### Phase 6 - Infrastructure Modernization (Completed January 2, 2026)
- ✅ Migrated from Traefik to NGINX
- ✅ Implemented Cloudflare Origin Certificates (15-year validity)
- ✅ Eliminated SSH deployment dependencies
- ✅ Native Docker Compose architecture
- ✅ Deployed monitoring stack (Prometheus/Grafana/cAdvisor)
- ✅ Implemented Let's Encrypt auto-renewal for LAN services
- ✅ Updated CLAUDE.md to reflect current architecture
- ✅ All 10 services operational (100%)
- ✅ Personal Website deployment successful
- ✅ Cloudflare SSL mode set to "Full (Strict)"

---

*This document should be updated regularly to reflect completed items and newly discovered improvements.*
