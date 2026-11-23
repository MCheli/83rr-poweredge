# house-transcriber

Transcribes speech heard by the five **indoor** UniFi cameras (Basement, Bedroom, Kitchen,
Living room, Office) into the AI Context RAW vault on this server at
`/data/ai-context/raw/house-transcripts/YYYY/YYYY-MM-DD.md` (bind-mounted as `/output`;
since the 2026-11-23 cut-over the vault is the main copy, and git history, Obsidian Sync and
the Seafile backup push follow it: `infrastructure/ai-context/README.md`). Until the cut-over
it wrote the same files into the Seafile library through its web API; that path is kept in the
image as the roll-back. Code, model choice and cleanup rules:
`github.com/MCheli/house-transcriber` (private), README.

| | |
| --- | --- |
| Image | `ghcr.io/mcheli/house-transcriber:latest` (private package, watchtower-managed) |
| Compose | service `house-transcriber`, profile `transcriber`, runs as `1000:1000` (the deploy user, owner of the vault) |
| Network | `infrastructure`; outbound to Protect (192.168.1.108:443/7441) and HA (192.168.1.121:8123). Seafile only in roll-back mode |
| Ports / nginx | **none** (the R630 is internet-facing; this must stay outbound-only) |
| Limits | 6 CPUs, 4 GB; `HT_CPU_THREADS=6` |
| State | `house_transcriber_models` volume (Whisper weights only) and the `/output` bind mount (transcript files). No audio is ever written |
| Logs | counts, room names, errors. Never transcript text (Fluent Bit ships them to OpenSearch) |

## Rules that must not change

- **Allowlist only.** The five indoor cameras are hard-coded by Protect id and MAC in the
  image. Driveway and the Front Door doorbell must never be captured, not even for a test
  (Massachusetts all-party consent).
- **No raw audio** on disk anywhere.
- **Fail closed:** HA toggle `input_boolean.house_transcription` off, unknown, or HA unreachable
  means every ffmpeg stops within ~3 s and queued audio is discarded.
- **No ports, no nginx route.**

## Credentials (root `.env`, values from 1Password)

| Variable | 1Password item |
| --- | --- |
| `HOUSE_TRANSCRIBER_HA_TOKEN` | Agents / `HA agent token` |
| `HOUSE_TRANSCRIBER_PROTECT_API_KEY` | Agents / `UniFi Protect API key` (Protect → Settings → Control Plane → Integrations → Create API Key) |
| `HOUSE_TRANSCRIBER_SEAFILE_TOKEN` | Agents / `Seafile AI Context token (house-transcriber, rw)`: files.markcheli.com → AI Context library → ⋯ → Advanced → API Token → app `house-transcriber`, permission **Read-Write**. Since the cut-over the service doesn't read it; the same value lives in `/data/ai-context/.secrets/seafile-rw-token` for the backup push (`scripts/ai-context/seafile-backup-push.py`), and it is the roll-back credential (below) |

Optional: `HOUSE_TRANSCRIBER_HA_URL` (default `http://192.168.1.121:8123`; fall back to
`https://home.markcheli.com` only if the LAN address is unreachable from containers),
`HOUSE_TRANSCRIBER_MODEL` (default `large-v3-turbo`, see below),
`HOUSE_TRANSCRIBER_OUTPUT_DIR` (host folder mounted at `/output`; default
`/data/ai-context/raw/house-transcripts`).

Add them to `~/83rr-poweredge/.env` on the server like the other secrets there, without echoing
values into a terminal or log. From the Mac mini, one way is
`op read --no-newline "op://Agents/HA agent token/credential" | ssh 83rr-poweredge 'cd ~/83rr-poweredge && printf "HOUSE_TRANSCRIBER_HA_TOKEN=%s\n" "$(cat)" >> .env'`
(and the same for the other two).

## Deploy

```bash
ssh 83rr-poweredge
cd ~/83rr-poweredge && git pull

# 1. Image access: the package is private. Works if the server's docker is already logged in
#    to ghcr.io (watchtower reads ~/.docker/config.json). If this fails with "denied",
#    `docker login ghcr.io -u MCheli` with a classic PAT that has only read:packages.
docker pull ghcr.io/mcheli/house-transcriber:latest

# 2. Reachability from a container on the infrastructure network (expect 200/401 for HA,
#    a TLS answer from Protect):
docker run --rm --network 83rr-poweredge_infrastructure --entrypoint python \
  ghcr.io/mcheli/house-transcriber:latest -c "
import socket
for h, p in [('192.168.1.121', 8123), ('192.168.1.108', 443), ('192.168.1.108', 7441)]:
    socket.create_connection((h, p), 5).close(); print('ok', h, p)"

# 2b. (once, done at the 2026-11-23 cut-over) the container runs as 1000:1000 so its files
#     belong to the vault; the Whisper cache volume was created by the image's uid 10002:
docker run --rm -v 83rr-poweredge_house_transcriber_models:/m alpine chown -R 1000:1000 /m
#     and the output folder must exist and belong to the deploy user:
ls -ld /data/ai-context/raw/house-transcripts

# 3. Benchmark on this CPU (no cameras involved; synthetic clip in the image). Takes a few
#    minutes and downloads each model into the volume once.
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile transcriber \
  run --rm --no-deps -e HT_BENCH_BEAMS=1 house-transcriber \
  python -m house_transcriber.bench medium.en large-v3-turbo large-v3
```

**Pick the model:** the most accurate of large-v3 → large-v3-turbo → medium.en whose
"rooms" (packed) figure is **≥ 2** and whose per-call time is **< 8 s**. Set
`HOUSE_TRANSCRIBER_MODEL` in `.env` if it isn't large-v3-turbo. If even medium.en misses,
raise `HT_CPU_THREADS` and the `cpus` limit together (no further than 8; the box also runs
Plex transcodes, Seafile and OpenSearch).

```bash
# 4. Turn it on: add "transcriber" to COMPOSE_PROFILES in .env (e.g. COMPOSE_PROFILES=mcp,transcriber)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d house-transcriber
docker compose logs -f house-transcriber
#   expect: loading <model> ... / transcription ON / streams resolved: Basement, Bedroom,
#   Kitchen, Living room, Office / <room>: stream open  (x5)
```

Startup exits on purpose (and restarts) if `/output` is missing or not writable (log:
`output folder missing` / `not writable`); the first thing a healthy start logs about output is
`transcripts go to the local folder (bind mount)`.

5. Once it's running, update `house-transcripts/README.md` in the RAW vault if the model or the
   host changed (it describes the R630, CPU Whisper and the gaps).

**Roll-back to the Seafile web API** (the pre-cut-over path, still in the image): in
`docker-compose.yml` drop `HT_OUTPUT_DIR` and the `/output` volume, put back
`SEAFILE_REPO_TOKEN=${HOUSE_TRANSCRIBER_SEAFILE_TOKEN:-}`, `SEAFILE_URL=http://seafile`,
`SEAFILE_HOST_HEADER=files.markcheli.com` and `depends_on: [seafile]`, then
`docker compose up -d house-transcriber`. The log then says `transcripts go to Seafile through
its web API (roll-back mode)`.

## Verify

- **Streams:** `docker top house-transcriber | grep -c ffmpeg` → 5, and each ffmpeg command
  line names one of the five allowlisted cameras' RTSPS paths.
- **End to end:** play a short TTS phrase on one indoor camera's speaker from HA (never the
  Driveway or Front Door speaker). Within about a minute, a matching line should appear in
  today's file, `/data/ai-context/raw/house-transcripts/YYYY/YYYY-MM-DD.md` on the server
  (`tail -3`), and in Seafile only after the next backup push (every 30 min). Delete the test
  line afterwards (edit the file on the server or in Obsidian; the service appends to the file
  as it is, so the edit sticks).
- **Ownership:** `ls -l` of today's file shows `mcheli mcheli` (uid 1000), never 10002.
- **Toggle:** turn **House transcription** off in HA (Room Control → Home, the microphone
  button at the bottom). Within ~3 s the log says `transcription OFF` / `all camera streams
  closed` and `docker top` shows no ffmpeg. Turn it on and the five streams reopen.
- **Load:** `docker stats --no-stream house-transcriber` while people talk; the stats line in
  the log every 10 min gives `cpu_busy` vs wall time.

## Pause, stop, remove

- **Pause:** the HA toggle (fail-closed; no restart needed).
- **Stop:** `docker compose stop house-transcriber`. It stays stopped across `up -d` runs only if
  `transcriber` is also removed from `COMPOSE_PROFILES`.
- **Remove:** drop it from `COMPOSE_PROFILES`, `docker compose rm -sf house-transcriber`,
  `docker volume rm 83rr-poweredge_house_transcriber_models`; revoke the Protect API key (the
  Seafile rw token is also the backup push's, keep it while that runs). Transcripts in the
  AI Context RAW vault stay.
