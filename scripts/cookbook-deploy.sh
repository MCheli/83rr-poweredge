#!/usr/bin/env bash
# Runs ON the server: pull the new Cookbook image, restart the app and its public demo, verify both.
# Watchtower also picks up new images on its own; this is the by-hand path with checks.
set -euo pipefail
cd ~/83rr-poweredge
STAMP=$(date +%F-%H%M)
mkdir -p ~/cookbook-backups

echo "== backup"
if docker ps --format '{{.Names}}' | grep -qx cookbook-db; then
  docker exec cookbook-db pg_dump -U cookbook cookbook | gzip > ~/cookbook-backups/cookbook-$STAMP.sql.gz
  ls -la ~/cookbook-backups/cookbook-$STAMP.sql.gz
else
  echo "cookbook-db not running yet (first deploy); nothing to back up"
fi

echo "== pull"
docker compose pull cookbook cookbook-demo 2>&1 | tail -3

echo "== restart (migrations run in the entrypoint; the demo also reseeds Claudius)"
docker compose up -d cookbook-db cookbook 2>&1 | tail -3
docker compose up -d cookbook-demo-db cookbook-demo 2>&1 | tail -3

for svc in cookbook cookbook-demo; do
  for i in $(seq 1 40); do
    if docker exec "$svc" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" >/dev/null 2>&1; then
      echo "$svc healthy after ${i}x3s"; break
    fi
    sleep 3
  done
done

echo "== containers"
docker ps -a --format "{{.Names}} {{.Image}} {{.Status}}" | grep -E "^cookbook"
echo "== log tails"
docker logs --tail 15 cookbook 2>&1 | grep -v "GET /api/health"
docker logs --tail 15 cookbook-demo 2>&1 | grep -v "GET /api/health"

echo "== public checks"
curl -s -o /dev/null -w "cookbook health %{http_code}\n" https://cookbook.markcheli.com/api/health
curl -s https://cookbook.markcheli.com/api/auth/config; echo
curl -s https://cookbook.markcheli.com/api/recipes | python3 -c 'import json,sys; print("public recipes:", len(json.load(sys.stdin)))'
curl -s -o /dev/null -w "demo health %{http_code}\n" https://cookbook-demo.markcheli.com/api/health
curl -s https://cookbook-demo.markcheli.com/api/auth/config; echo
curl -s -o /dev/null -w "demo write %{http_code} (expect 403)\n" -X POST \
  -H 'Content-Type: application/json' -d '{"name":"x"}' https://cookbook-demo.markcheli.com/api/me/api-keys
