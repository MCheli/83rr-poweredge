# 83RR PowerEdge Infrastructure Makefile
# Simplifies common development and operations tasks

.PHONY: help up down restart logs status build clean test health \
        nginx-reload nginx-test prometheus-reload grafana-reload \
        venv deps shell backup

# Default target
help:
	@echo "83RR PowerEdge Infrastructure - Available Commands"
	@echo ""
	@echo "Deployment:"
	@echo "  make up              - Start all services (production)"
	@echo "  make up-dev          - Start all services (development)"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make restart s=NAME  - Restart specific service"
	@echo ""
	@echo "Building:"
	@echo "  make build           - Build all services"
	@echo "  make build s=NAME    - Build specific service"
	@echo "  make build-no-cache  - Build all services without cache"
	@echo ""
	@echo "Monitoring:"
	@echo "  make status          - Show container status"
	@echo "  make logs            - Follow all logs"
	@echo "  make logs s=NAME     - Follow specific service logs"
	@echo "  make health          - Run health checks on all services"
	@echo ""
	@echo "NGINX:"
	@echo "  make nginx-test      - Test NGINX configuration"
	@echo "  make nginx-reload    - Reload NGINX configuration"
	@echo ""
	@echo "Monitoring Stack:"
	@echo "  make prometheus-reload  - Reload Prometheus configuration"
	@echo "  make grafana-reload     - Restart Grafana to reload dashboards"
	@echo ""
	@echo "Python:"
	@echo "  make venv            - Create Python virtual environment"
	@echo "  make deps            - Install Python dependencies"
	@echo ""
	@echo "Utilities:"
	@echo "  make shell s=NAME    - Open shell in container"
	@echo "  make clean           - Remove stopped containers and unused images"
	@echo "  make clean-all       - Remove all unused Docker resources"
	@echo "  make test            - Run infrastructure tests"
	@echo ""
	@echo "Examples:"
	@echo "  make restart s=nginx"
	@echo "  make logs s=grafana"
	@echo "  make build s=personal-website"

# =============================================================================
# Deployment Commands
# =============================================================================

up:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

up-dev:
	docker compose up -d

down:
	docker compose down

restart:
ifdef s
	docker compose restart $(s)
else
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
endif

# =============================================================================
# Building Commands
# =============================================================================

build:
ifdef s
	docker compose build $(s)
else
	docker compose build
endif

build-no-cache:
ifdef s
	docker compose build --no-cache $(s)
else
	docker compose build --no-cache
endif

# =============================================================================
# Monitoring Commands
# =============================================================================

status:
	@echo "=== Container Status ==="
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -20
	@echo ""
	@echo "=== Disk Usage ==="
	@df -h / | tail -1
	@echo ""
	@echo "=== Memory Usage ==="
	@free -h | head -2

logs:
ifdef s
	docker compose logs -f --tail=100 $(s)
else
	docker compose logs -f --tail=50
endif

health:
	@echo "=== Service Health Checks ==="
	@echo ""
	@echo "NGINX:"
	@curl -sf http://localhost/health && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "Personal Website (www.markcheli.com):"
	@curl -sf -o /dev/null -w "%{http_code}" https://www.markcheli.com && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "Flask API (flask.markcheli.com):"
	@curl -sf https://flask.markcheli.com/health && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "Prometheus:"
	@curl -sf http://localhost:9090/-/healthy && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "Grafana:"
	@docker exec grafana wget -q --spider http://localhost:3000/api/health && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "OpenSearch:"
	@docker exec opensearch curl -sf http://localhost:9200/_cluster/health | grep -q '"status"' && echo " [OK]" || echo " [FAIL]"
	@echo ""
	@echo "=== Prometheus Targets ==="
	@docker exec prometheus wget -qO- http://localhost:9090/api/v1/targets 2>/dev/null | \
		python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"  {t['labels'].get('job','?'):20} {t['health']}\") for t in d.get('data',{}).get('activeTargets',[])]" 2>/dev/null || echo "  Unable to fetch targets"

# =============================================================================
# NGINX Commands
# =============================================================================

nginx-test:
	docker compose exec nginx nginx -t

nginx-reload:
	docker compose exec nginx nginx -s reload

# =============================================================================
# Monitoring Stack Commands
# =============================================================================

prometheus-reload:
	docker compose restart prometheus
	@echo "Waiting for Prometheus to start..."
	@sleep 5
	docker compose exec nginx nginx -s reload

grafana-reload:
	docker compose restart grafana
	@echo "Waiting for Grafana to start..."
	@sleep 5
	docker compose exec nginx nginx -s reload

# =============================================================================
# Python Commands
# =============================================================================

venv:
	python3 -m venv venv
	@echo "Virtual environment created. Activate with: source venv/bin/activate"

deps:
	. venv/bin/activate && pip install -r requirements.txt

# =============================================================================
# Utility Commands
# =============================================================================

shell:
ifndef s
	@echo "Error: Specify service with s=NAME"
	@echo "Example: make shell s=nginx"
	@exit 1
endif
	docker exec -it $(s) /bin/sh || docker exec -it $(s) /bin/bash

clean:
	docker container prune -f
	docker image prune -f

clean-all:
	@echo "WARNING: This will remove all unused Docker resources!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker system prune -a -f

test:
	@echo "Running infrastructure tests..."
	. venv/bin/activate && python scripts/test_infrastructure.py

# =============================================================================
# Quick Access Commands
# =============================================================================

# Open Grafana in browser (macOS)
open-grafana:
	open https://grafana-local.ops.markcheli.com

# Open logs dashboard in browser (macOS)
open-logs:
	open https://logs-local.ops.markcheli.com

# Open Prometheus in browser (macOS)
open-prometheus:
	open https://prometheus-local.ops.markcheli.com

# Show recent git commits
git-log:
	git log --oneline -10

# Quick git status
git-status:
	git status -s
