# Server crontab

`crontab` in this directory is the **source of truth** for the user crontab of
`mcheli` on the server (`crontab -l`). It holds no secret values: jobs read their
credentials from `.env` or files outside the repo. Times are UTC (the server's
clock); the Home Assistant job converts to US Eastern itself (`--at-hour`).

Every job runs through `scripts/cron-notify.sh NAME COMMAND...`, which pushes to
ntfy when a job fails and records its result for Grafana
(`docs/OBSERVABILITY.md#cron-wrapper`). Add new jobs the same way.

| When (UTC) | Job | What |
|---|---|---|
| 02:00 | `backup` | nightly backup to the NAS (`docs/BACKUP_RESTORE.md`) |
| 03:00 | `letsencrypt-renew` | renew the `*.ops` and `status` Let's Encrypt certificates, reload nginx |
| 03:30 | `sbom-scan` | SBOMs of running containers to Dependency-Track (`docs/dependency-track.md`) |
| 04:20 | `seafile-pull-work` | copy the work-laptop raw dump (kept only in Seafile) to `/data/ai-context/work-laptop` |
| 08:00 / 08:30 | `*-demo-reseed` | restart the Tallied, Tasks and Cookbook public demos (they reseed on start) |
| 08:15 and 09:15 | `ha-auto-update` | Home Assistant updates at 04:15 US Eastern; the script runs only in the matching hour, so DST needs no edit (`docs/home-assistant-auto-update.md`) |
| hourly at :07 | `recent-ai-changes` | refresh the "Recently changed by AI" map note through basic-memory |
| every 30 min | `seafile-backup-push` | AI Context vault → Seafile backup copy (`infrastructure/ai-context/README.md`) |
| every 15 min | `ai-context-autocommit` | commit the AI Context vaults, push the notes repo |
| every 10 min | `security-telemetry` | listening ports and external DB connections to OpenSearch |
| every 5 min | `host-metrics` | host metrics to OpenSearch |
| every minute | `alert-metrics` | certificate expiry and UPS state for Grafana alerts |

## Install or change

1. Edit `infrastructure/cron/crontab` here and merge the change.
2. On the server, pull, then compare with what is installed. The diff should show
   only your change; anything else means the live crontab was edited by hand, and
   that edit belongs in the repo first:
   ```bash
   cd ~/83rr-poweredge && git pull --ff-only
   crontab -l | diff - infrastructure/cron/crontab
   ```
3. Install it (this replaces the whole crontab) and check:
   ```bash
   crontab -l > ~/crontab-backups/crontab-$(date +%F-%H%M).txt
   crontab infrastructure/cron/crontab
   crontab -l | diff - infrastructure/cron/crontab && echo identical
   ```

Roll back: `crontab ~/crontab-backups/<file>`.
