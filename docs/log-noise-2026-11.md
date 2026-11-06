# Log noise cleanup (2026-11): deploy notes

Covers the `ops/logq-and-log-noise` change:

- OpenSearch loggers quieted (`docker-compose.yml`)
- fluent-bit docker_events fix (`infrastructure/fluent-bit/`)
- new `scripts/logq.sh`

Run everything from `~/83rr-poweredge` on the server after `git pull`. The `logq.sh` checks also work unchanged from the Mac mini.

## What changes and why

### 1. OpenSearch self-logging: WARN for three plugin loggers

OpenSearch's own log is the largest source in the log index. Daily docs, from `logs-homelab-*`:

| day (UTC) | all containers | opensearch |
|---|---|---|
| 10-23 … 10-30 (3.2.0) | 125k–154k | ~81.8k |
| 11-01 (3.9.0 upgrade day) | 292k | 109k |
| 11-02 … 11-05 (3.9.0) | 317k–402k | ~164.8k |

A 10k-line sample from 2026-11-05 breaks down by logger like this:

- `o.o.j.t.PluginClient`: 47%
- `o.o.i.i.ManagedIndexRunner`: 31%
- `o.o.j.s.JobScheduler`: 16%
- `o.o.r.m.c.i.LocalClusterIndicesClient`: 3%
- alerting `MonitorRunnerService` and `TransportExecuteMonitorAction`: 3%
- the rest: <1%

Every line in the sample was INFO.

The fix sets three logger prefixes to WARN as `-E` node settings. The image entrypoint turns any dotted lower-case env var into `-E<key>=<value>`, and `logger.<package>` is OpenSearch's standard per-package log level setting:

```
logger.org.opensearch.jobscheduler=WARN          # PluginClient, JobScheduler, JobSweeper
logger.org.opensearch.indexmanagement=WARN       # ISM ManagedIndexRunner
logger.org.opensearch.remote.metadata=WARN       # LocalClusterIndicesClient (remote-metadata-sdk)
```

The package names were checked against the plugin jars in the running 3.9.0 container. `opensearch-remote-metadata-sdk-3.9.0.0.jar` holds `org/opensearch/remote/metadata/client/impl/LocalClusterIndicesClient`.

Expected result: about 94% fewer opensearch docs (~165k/day down to ~10k/day), and about 40% fewer docs overall.

**Why logger levels and not a fluent-bit grep exclude.** A logger level drops only INFO from those three plugins. Their WARN and ERROR still come through, and so does INFO from every other logger: node start, cluster state, alerting monitor runs, notifications. A fluent-bit `Exclude log ^\[...\]\[INFO ...` would have to match the log4j line format by regex. If that format changed (it already differs between the JSON and pattern layouts), the regex would either stop matching or match too much, and it would do so silently. The grep option also keeps the junk in the container's json-file log and costs CPU on every line. Root logger to WARN was also rejected, because it would hide startup and cluster-state INFO that deploy checks rely on.

### 2. fluent-bit docker_events: the "unknown" docs

Since at least 2026-10-08, every docker_events doc has been indexed as `container_name: unknown`, `container_id: events`, `log: "docker ? ? unknown"` (or `docker volume mount unknown`). That's 180–820 docs/day, rising since 11-02. Only a handful per day were ever parsed. There were two causes:

1. **The `add_container_name` filter matched `docker.events`.** Its `Match docker.*` and tag pattern `docker%.([a-z0-9]+)` treated `events` as a container ID. It set `container_id: events` and `container_name: unknown`, and it tried to `io.open` a nonexistent `config.v2.json` for every event, uncached. It now accepts only 64-hex tags.
2. **The docker_events input does no framing.** In Fluent Bit 5.1.5 (`plugins/in_docker_events/docker_events.c`), one `read()` of up to `Buffer_Size` (default 8k) from the `/events` stream becomes one record. Docker sends roughly 320 events/min here, mostly healthcheck `exec_*` events in bursts. A single read can therefore hold several events, or begin or end partway through one.
   - When a read began mid-event, the normalizer found no `Action`. The record went through as `docker ? ? unknown`.
   - When a read began with an `exec_*` event, the whole record was dropped, including any `die`/`stop`/`oom` behind it. That means the `container-died` monitor could miss real deaths.

The fix:

- `normalize_docker_event` now splits `message` on newlines and handles each event on its own. Lines that aren't the start of an event are dropped, and several surviving events are returned as a table of records, which the lua filter supports for splitting records.
- `Buffer_Size 256k` on the input makes cuts rare.
- Non-container, non-image events (volume mount/unmount and similar) are now tagged `container_name: docker-volume-event` (etc.) with the volume or object name in `docker_object`, following the existing `docker-image-event` convention.

Tested with 14 cases (`lua` 5.5 on the Mac mini; the code avoids anything newer than 5.1, which is what LuaJIT runs). The cases were single events, exec-only reads, exec+die+start in one read, leading and trailing fragments, image/volume/network events, empty reads, structured records, and the tag check.

Not changed, but worth knowing: the `docker-exec-into-sock-container` monitor queries `event_type: exec*`, and the normalizer drops every `exec_` event (a deliberate noise cut that predates this change). So that monitor can't fire from docker events. Fixing it would mean keeping `exec_*` for fluent-bit/watchtower/uptime-kuma only, and uptime-kuma's own healthcheck would then need excluding. That's a separate change.

## Deploy

| service | action | why |
|---|---|---|
| opensearch | **recreate** | env changed. A ~1 min blip in log ingestion; fluent-bit retries (`Retry_Limit 5`) and replays its buffer. |
| fluent-bit | **recreate** | Bind-mounted `fluent-bit.conf` and `docker_metadata.lua` changed. The compose definition didn't change, so a plain `up -d` would do nothing. Tail offsets live in the `fluent_bit_data` volume, so nothing is re-shipped. |
| everything else | no change | |

Optional pre-check of the Lua in the real Fluent Bit runtime (throwaway container, `--network none`, prints to stdout, ships nothing):

```bash
MSG=$(printf '%s\n' \
  'tail-of-a-cut-event","scope":"local"}' \
  '{"Type":"container","Action":"exec_start: curl -f x","Actor":{"ID":"aa","Attributes":{"name":"grafana"}}}' \
  '{"Type":"container","Action":"die","Actor":{"ID":"0123456789abcdef","Attributes":{"name":"tasks"}}}' \
  '{"Type":"volume","Action":"mount","Actor":{"ID":"opensearch_data","Attributes":{"driver":"local"}}}')
DUMMY=$(jq -cn --arg m "$MSG" '{message: $m}')
timeout 15 docker run --rm --name flb-luatest --network none \
  -v "$PWD/infrastructure/fluent-bit/docker_metadata.lua:/t.lua:ro" \
  fluent/fluent-bit:5.1.5 \
  -i dummy -t docker.events -p samples=1 -p "dummy=$DUMMY" \
  -F lua -m '*' -p script=/t.lua -p call=normalize_docker_event \
  -o stdout -m '*'
docker rm -f flb-luatest 2>/dev/null
# expect exactly two records: log "docker container die tasks" (level ERROR)
# and "docker volume mount docker-volume-event"; no fragment, no exec_start.
```

Baseline (note the numbers):

```bash
scripts/logq.sh 'container_name:opensearch' 1          # ~6.9k/h before
scripts/logq.sh 'container_name:unknown' 1             # ~35/h before
```

Deploy (use the prod invocation for opensearch so the `opensearch_data` volume is used):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps opensearch
docker ps --filter name=^opensearch$ --format '{{.Status}}'      # wait for (healthy)
docker exec opensearch curl -s 'localhost:9200/_nodes/_local/settings?filter_path=**.logger&pretty'
#   -> jobscheduler / indexmanagement / remote.metadata: "WARN"

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --force-recreate fluent-bit
docker logs --since 2m fluent-bit 2>&1 | grep -iE 'error|lua' || echo "fluent-bit clean"
```

Rollback: `git revert` the commit and run the same two commands.

## Verify (after ~30 min, and again the next day)

```bash
# 1. Volume drop: opensearch was ~6.9k docs/h; expect a few hundred at most
scripts/logq.sh 'container_name:opensearch' 1
#   whole-day view, compare with the table above (UTC day):
docker exec opensearch curl -s 'localhost:9200/_cat/count/logs-homelab-*?v'   # or the histogram in logs.ops

# 2. No more "unknown": expect "hits: 0" and exit 0
scripts/logq.sh 'container_name:unknown' 1; echo "exit=$?"

# 3. Docker events now parse (any container restart/pull shows up by name)
scripts/logq.sh 'event_scope:(container OR image OR volume)' 24
#   force one if it's quiet: docker compose restart cookbook, then re-run;
#   expect "docker container die cookbook" (ERROR), stop, start

# 4. WARN/ERROR still arrive from OpenSearch: the restart itself logs a few
#    WARN lines (SLF4J / health-check warnings), and the 7-day baseline was
#    ~31 WARN/ERROR lines/day
scripts/logq.sh 'container_name:opensearch AND log:(WARN OR ERROR)' 1
#   and errors from everyone else are unaffected:
scripts/logq.sh errors 1
```

Success looks like this: (1) dropped by ~94%, (2) is 0 hits, (3) shows named events, and (4) shows a non-zero WARN count with the same per-day rate as before.

## Optional: turn the cluster green (one-off settings write, NOT done)

The cluster is yellow only because 36 replica shards of system indices (`.opendistro-ism-managed-index-history-*` ×29, `.opendistro-alerting-*` ×4, `.opendistro-ism-config`, `.opendistro-job-scheduler-lock`, `.opensearch-alerting-config-lock`) can never be assigned on a single node. `logs-homelab-*` is already at 0 replicas through its template. To fix it:

```bash
# a) New indices default to 0 replicas (cluster default is 1), and ISM's
#    daily history index too
docker exec -i opensearch curl -s -XPUT -H 'Content-Type: application/json' \
  localhost:9200/_cluster/settings --data-binary @- <<'EOF'
{"persistent": {
  "cluster.default_number_of_replicas": 0,
  "plugins.index_state_management.history.number_of_replicas": 0
}}
EOF

# b) Existing system indices: auto_expand 0-1 resolves to 0 replicas on one
#    node (and would go back to 1 if a second node ever joined)
docker exec opensearch curl -s -XPUT -H 'Content-Type: application/json' \
  'localhost:9200/.opendistro-*,.opensearch-*/_settings?expand_wildcards=all' \
  -d '{"index":{"auto_expand_replicas":"0-1"}}'

docker exec opensearch curl -s localhost:9200/_cluster/health | jq '{status, unassigned_shards}'
#   -> "green", 0
```

Persistent cluster settings live in the `opensearch_data` volume, so they survive restarts and recreates. If a call refuses with a system-index error, drop that index from the list. The ISM history indices are most of the 36, and they age out after 30 days anyway once (a) is in place.
