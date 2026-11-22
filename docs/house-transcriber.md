# house-transcriber

Transcribes speech heard by the five **indoor** UniFi cameras (Basement, Bedroom, Kitchen,
Living room, Office) into the Seafile "AI Context" library at
`05-raw/house-transcripts/YYYY/YYYY-MM-DD.md`. Code, model choice and cleanup rules:
`github.com/MCheli/house-transcriber` (private), README.

| | |
| --- | --- |
| Image | `ghcr.io/mcheli/house-transcriber:latest` (private package, watchtower-managed) |
| Compose | service `house-transcriber`, profile `transcriber` |
| Network | `infrastructure` (reaches `seafile` internally); outbound to Protect (192.168.1.108:443/7441) and HA (192.168.1.121:8123) |
| Ports / nginx | **none** (the R630 is internet-facing; this must stay outbound-only) |
| Limits | 6 CPUs, 4 GB; `HT_CPU_THREADS=6` |
| State | `house_transcriber_models` volume (Whisper weights only). No audio is ever written |
| Logs | counts, room names, errors. Never transcript text, never Seafile URLs (Fluent Bit ships them to OpenSearch) |

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
| `HOUSE_TRANSCRIBER_SEAFILE_TOKEN` | Agents / `Seafile AI Context token (house-transcriber, rw)`: files.markcheli.com → AI Context library → ⋯ → Advanced → API Token → app `house-transcriber`, permission **Read-Write** |

Optional: `HOUSE_TRANSCRIBER_HA_URL` (default `http://192.168.1.121:8123`; fall back to
`https://home.markcheli.com` only if the LAN address is unreachable from containers),
`HOUSE_TRANSCRIBER_MODEL` (default `large-v3-turbo`, see below).

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
for h, p in [('192.168.1.121', 8123), ('192.168.1.108', 443), ('192.168.1.108', 7441), ('seafile', 80)]:
    socket.create_connection((h, p), 5).close(); print('ok', h, p)"

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

Startup exits on purpose (and restarts) if the Seafile token is missing, wrong, or read-only.

5. Once it's running, update `05-raw/house-transcripts/README.md` in AI Context: it still says
   the Mac mini and MLX large-v3; make it the R630, CPU Whisper (the chosen model), and "when
   the R630 is down" under gaps.

## Verify

- **Streams:** `docker top house-transcriber | grep -c ffmpeg` → 5, and each ffmpeg command
  line names one of the five allowlisted cameras' RTSPS paths.
- **End to end:** play a short TTS phrase on one indoor camera's speaker from HA (never the
  Driveway or Front Door speaker). Within about a minute, a matching line should appear in
  today's file in Seafile. Delete the test line afterwards (edit the file in Seafile; the service
  re-reads the file before every write, so the edit sticks).
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
  `docker volume rm 83rr-poweredge_house_transcriber_models`; revoke the Seafile token and the
  Protect API key. Transcripts in AI Context stay.
