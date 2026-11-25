# Home Assistant automatic updates

Since 2026-11-25 the R630 keeps Home Assistant's own software updated by itself:
`scripts/ha-auto-update.py`, run from mcheli's crontab once a day at **04:15 America/New_York**.
Full behaviour is in the script's docstring and `scripts/README.md` (#20); this page is the short version.

## What it updates, and what it never touches

| Updated (after the hold rules) | Never touched |
|---|---|
| Supervisor, Core, Operating System, add-ons (`hassio` integration) | UniFi devices, ZHA/Zigbee devices, ESPHome devices, Matter devices |
| HACS integrations and cards (`hacs`, none installed yet) | Synology DSM, the Yellow's radio and board firmware, anything else |

## Hold rules

- A version installs only after it has been offered for **3 days** in a row.
- **Core X.Y.0 is never installed**; the job waits for X.Y.1 (which then soaks 3 days).
- A version **skipped in the HA UI** is never installed. That is the way to hold one by hand.
- Nothing is installed while any of these updates shows *in progress* (someone updating by hand).

## A run

1. Pre-checks: API answers, HA is RUNNING; counts unavailable entities (the baseline).
2. Installs in order Supervisor → add-ons → HACS → Core → OS, one at a time.
   Before Core or OS: `backup.create_automatic` (the automatic-backup settings decide where it goes) and a wait for it.
   `update.install` asks for its own backup where the entity supports it.
3. After each install: API answers, RUNNING, the new version shows as installed, and unavailable entities
   are not more than 25 (or 10 %) above the baseline after up to 10 minutes.
4. Any failure stops the run: high-priority ntfy push on `homelab` plus a Tasks agent item
   "Home Assistant auto-update failed: <component>". No automatic restores (Supervisor already rolls back
   a Core update that doesn't start).
5. Success with installs: one low-priority push listing the versions. Nothing to do: silent.

## Files on the server

| What | Where |
|---|---|
| Log (every run, no secrets) | `~/83rr-poweredge/logs/ha-auto-update.log` |
| First-seen state, lock | `~/.cache/ha-auto-update/` |
| Secrets | `~/83rr-poweredge/.env` (mode 600): `HA_AUTO_UPDATE_TOKEN`, `HA_AUTO_UPDATE_TASKS_API_KEY`, `NTFY_PUBLISH_TOKEN` |
| Cron | `15 8,9 * * * /home/mcheli/83rr-poweredge/scripts/ha-auto-update.py --at-hour 4 >/dev/null 2>&1` |

The server runs on UTC and its cron has no per-line time zone, so the line fires at 08:15 and 09:15 UTC and
`--at-hour 4` keeps only the one that is 04:15 in New York (summer or winter).

## Common tasks

```bash
scripts/ha-auto-update.py --dry-run          # what's pending and when each becomes due
tail -50 ~/83rr-poweredge/logs/ha-auto-update.log
crontab -l | grep ha-auto-update             # turn it off: comment that line out
```
