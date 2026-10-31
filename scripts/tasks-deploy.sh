#!/usr/bin/env bash
# Runs ON the server: pull the new Tasks image, restart the app and its public demo, verify both.
# Watchtower also picks up new images on its own; this is the by-hand path with checks.
set -euo pipefail
cd ~/83rr-poweredge
STAMP=$(date +%F-%H%M)
mkdir -p ~/tasks-backups

echo "== backup"
docker exec tasks-db pg_dump -U tasks tasks | gzip > ~/tasks-backups/tasks-$STAMP.sql.gz
ls -la ~/tasks-backups/tasks-$STAMP.sql.gz

echo "== pull"
docker compose pull tasks tasks-demo 2>&1 | tail -3

echo "== restart (migrations run in the entrypoint; the demo also reseeds Claudius)"
docker compose up -d --no-deps tasks 2>&1 | tail -3
docker compose up -d tasks-demo-db tasks-demo 2>&1 | tail -3

for svc in tasks tasks-demo; do
  for i in $(seq 1 40); do
    if docker exec "$svc" curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
      echo "$svc healthy after ${i}x3s"; break
    fi
    sleep 3
  done
done

echo "== containers"
docker ps -a --format "{{.Names}} {{.Image}} {{.Status}}" | grep -E "^tasks"
echo "== demo log tail"
docker logs --tail 15 tasks-demo 2>&1 | grep -v "GET /api/health"

echo "== public checks"
curl -s -o /dev/null -w "tasks health %{http_code}\n" https://tasks.markcheli.com/api/health
curl -s https://tasks.markcheli.com/api/auth/config; echo
curl -s -o /dev/null -w "demo health %{http_code}\n" https://tasks-demo.markcheli.com/api/health
curl -s https://tasks-demo.markcheli.com/api/auth/config; echo
curl -s -o /dev/null -w "demo write %{http_code} (expect 403)\n" -X POST \
  -H 'Content-Type: application/json' -d '{"name":"x"}' https://tasks-demo.markcheli.com/api/api-keys
