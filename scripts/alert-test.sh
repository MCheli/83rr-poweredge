#!/usr/bin/env bash
# alert-test.sh — prove both alert paths still reach ntfy (topic homelab).
# Sends one test through OpenSearch alerting (a one-off monitor run, same path as a real alert)
# and one through Uptime Kuma's own ntfy provider, then checks both landed in ntfy's message
# cache. Run weekly by the Mac mini's homelab-weekly-check (act.sh alert-test). Reads no secrets
# itself: the token lives in the OpenSearch channel and in Kuma's notification config.
# Exit 0 = both delivered; non-zero = alerting is broken, say so loudly.
set -u
cd "$(dirname "$0")/.." || exit 2
start=$(date +%s)
fail=0

python3 infrastructure/opensearch/config/alerting/wire-ntfy.py --test-only || fail=1

docker cp -q infrastructure/ntfy/kuma-ntfy.js uptime-kuma:/app/kuma-ntfy.js &&
  docker exec -i -w /app uptime-kuma node kuma-ntfy.js test </dev/null || fail=1
docker exec uptime-kuma rm -f /app/kuma-ntfy.js

sleep 2
d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
docker cp -q ntfy:/var/lib/ntfy/cache.db "$d/cache.db" || { echo "cannot read ntfy cache"; exit 1; }
python3 - "$d/cache.db" "$start" <<'EOF' || fail=1
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); since = int(sys.argv[2]) - 5
def seen(where):
    return c.execute(f"SELECT count(*) FROM messages WHERE topic='homelab' AND time >= ? AND {where}", (since,)).fetchone()[0]
os_ok = seen("title LIKE '%OpenSearch alert test%'")
kuma_ok = seen("message LIKE '%Uptime Kuma alert test%'")
print(f"ntfy received: opensearch={'yes' if os_ok else 'NO'} uptime-kuma={'yes' if kuma_ok else 'NO'}")
sys.exit(0 if os_ok and kuma_ok else 1)
EOF
[ $fail = 0 ] && echo "ALERT TEST OK" || echo "ALERT TEST FAILED"
exit $fail
