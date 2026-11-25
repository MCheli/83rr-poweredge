# fail2ban on 83rr-poweredge

Host fail2ban (Ubuntu package, 1.0.2) with two jails:

| Jail | Watches | Ban |
|---|---|---|
| `sshd` | journald (Debian default, `jail.d/defaults-debian.conf`) | not managed here |
| `postgresql-tallied` | `/var/log/pg-auth/tallied-db.log` | tcp 5432 in Docker's `DOCKER-USER` chain |

This directory holds the `postgresql-tallied` jail (added 2026-11-25).

## Why 5432 is public and what the jail does

Tallied hands each household Postgres roles named `tld_*` (32-character random
password, scram-sha-256, `hostssl` only, `CONNECTION LIMIT 5`, optional
`VALID UNTIL`; see the tallied repo, `backend/app/services/db_credentials.py`)
so people can connect psql, DBeaver or Excel from anywhere. So port 5432 stays
open to the internet on purpose. `pg_hba.conf` (`docker/postgres/pg_hba.conf`)
already rejects the superuser and `tallied_app` from outside Docker.

What was missing was a limit on retries and any visibility. Now:

1. **tallied-db logs the client.** `log_connections=on` and
   `log_line_prefix='%m [%p] host=%h user=%u db=%d '` (docker-compose.yml).
   `auth_delay` is deliberately not used: each delayed failure holds a backend
   slot, so a flood could use up `max_connections` (100) and lock the app out.
2. **Fluent Bit writes a stable log for fail2ban.** The docker json log path
   changes whenever tallied-db is recreated, so Fluent Bit copies the tallied-db
   auth failure lines (rewrite_tag + grep, `infrastructure/fluent-bit/fluent-bit.conf`)
   to `/var/log/pg-auth/tallied-db.log`, log text only. The copies don't go to
   OpenSearch (the originals do). logrotate: `logrotate-pg-auth` (daily,
   14 kept, 20 MB cap, copytruncate).
3. **The jail bans the address on 5432 only.** Docker-published ports never
   pass ufw's INPUT chain, so the ban is `iptables-multiport` with
   `chain=DOCKER-USER`, `blocktype=DROP` (Docker 29 here uses iptables-nft;
   fail2ban's iptables actions write to the same nf_tables `ip filter` table).
   After DNAT the destination port is the container's, also 5432.
4. **OpenSearch sees everything.** Fluent Bit also tails `/var/log/fail2ban.log`
   (`container_name: fail2ban`, every jail), and the ingest pipeline sets
   `event_type` (`pg_auth_failure`, `pg_connection_authorized`, `fail2ban_ban`,
   `fail2ban_unban`, `fail2ban_restore`, `fail2ban_found`, `fail2ban_ignore`),
   `client_ip`, `pg_user`, `pg_db`, `f2b_jail`. Alerts: see
   `infrastructure/opensearch/config/alerting/README.md` ("Postgres and fail2ban").

## Thresholds and why

Measured from OpenSearch before choosing (2026-11-18 to 11-25, tallied-db, 7 days):

- 185 `no pg_hba.conf entry` lines from 28 addresses, 2 to 7 distinct addresses a day;
  1 `password authentication failed` line. No `pg_hba.conf rejects` lines.
- 26 addresses tried once, 1 twice, and one address sent 157 attempts in 38 s
  (about 4 a second, all as user `postgres`).
- Users tried: `postgres` 171, `root` 9, `test` 3, two odd ones. **No `tld_`
  name ever appeared.** 4 `tld_` roles are active.
- Almost every scanner connects without TLS, so it fails on `hostssl` with
  "no pg_hba.conf entry" before any password check.

So: `maxretry = 10` lines in `findtime = 10m`. A scanner logs one line per
try; a person with a wrong password and libpq's default `sslmode=prefer` logs
two (the TLS try fails the password, the plain retry has no hba entry), so 10
lines is 5 to 10 tries. The one-shot probes are never banned (they aren't
guessing); the burst scanner would be. `bantime = 1h` growing with
`bantime.increment` (factor 1: 1h, 2h, 4h, …) up to `bantime.maxtime = 1w`;
`fail2ban.d/83rr.local` raises `dbpurgeage` to 8 days so the earlier bans are
still in the database when an address comes back.

`ignoreip = 127.0.0.0/8 ::1 192.168.1.0/24 172.16.0.0/12 10.0.0.0/8`: Mark's
LAN and every Docker network (tallied and tallied-scheduler connect from
172.x). The filter's `ignoreregex` lists the same ranges, so `fail2ban-regex`
shows them as ignored too.

Ban latency: Fluent Bit flushes every 5 s and fail2ban polls the file every
second, so at 4 tries a second roughly 20 to 40 lines get through before the
ban lands. The "ban not working" monitor's single-address line (50 in 10 min)
sits above that.

The failregex is anchored on the prefix (`[pid] host=<HOST>`), because a
client chooses its own user and database names: an unanchored match could be
steered onto another address. `fail2ban-regex` on test lines with a forged
`host=` inside the user and database names keys on the real address.

## Files

| File | Installed as |
|---|---|
| `filter.d/postgresql-tallied.conf` | `/etc/fail2ban/filter.d/postgresql-tallied.conf` |
| `jail.d/postgresql-tallied.local` | `/etc/fail2ban/jail.d/postgresql-tallied.local` |
| `fail2ban.d/83rr.local` | `/etc/fail2ban/fail2ban.d/83rr.local` (`dbpurgeage = 8d`) |
| `fail2ban.service.d/after-docker.conf` | `/etc/systemd/system/fail2ban.service.d/after-docker.conf` (start after docker: the jail writes into `DOCKER-USER`) |
| `logrotate-pg-auth` | `/etc/logrotate.d/pg-auth` |
| `sudoers-fail2ban-status` | `/etc/sudoers.d/fail2ban-status` (440, `visudo -cf` first): passwordless `fail2ban-client status`, `status sshd`, `status postgresql-tallied` for mcheli, nothing else |

## Install / update

```bash
# on the server, from the repo checkout
sudo infrastructure/fail2ban/install.sh           # install + fail2ban-client -t + restart fail2ban
sudo infrastructure/fail2ban/install.sh --check   # status only
```

Order on a fresh host: run install.sh (creates `/var/log/pg-auth`), then
recreate Fluent Bit (`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps fluent-bit`),
which mounts that directory.

## Everyday commands

```bash
sudo fail2ban-client status postgresql-tallied    # passwordless for mcheli
sudo iptables -S DOCKER-USER                      # the jump into f2b-postgresql-tallied
sudo iptables -S f2b-postgresql-tallied           # one DROP line per banned address
sudo fail2ban-client set postgresql-tallied unbanip <ip>   # let someone back in
sudo fail2ban-regex /var/log/pg-auth/tallied-db.log /etc/fail2ban/filter.d/postgresql-tallied.conf
```

A household locked out after mistyping (from outside the LAN): unban the
address as above; a fresh ban after that starts at 1h again only once the
earlier bans age out of the database (8 days).

## Tests run at install (2026-11-25)

- **LAN login**: a temporary role `tld_f2btest_<hex>` (random password,
  `VALID UNTIL` +1 h, no grants) logged in with `sslmode=require` (TLSv1.3).
  The client was psql in a `--network host` scratch container on the server
  connecting to 192.168.1.179 (the Mac mini's psql is not on its dontAsk
  allow list), so Postgres saw `host=192.168.1.179`, a LAN address. The
  `connection authorized` line reached OpenSearch with `event_type
  pg_connection_authorized`, `client_ip 192.168.1.179`, `pg_user`. Role dropped.
- **LAN not banned**: 6 wrong passwords (`sslmode=prefer`, 12 lines) from the
  same address were logged, written to `/var/log/pg-auth/tallied-db.log`, and
  reached OpenSearch as `pg_auth_failure`. `fail2ban-regex` on the real file:
  12 lines, 12 ignored, 0 matched. No ban. (The test used a non-`tld_` name so
  `pg-auth-tld-user` wouldn't page for a test.)
- **Ban path**: `fail2ban-client set postgresql-tallied banip 203.0.113.77`
  added `-A DOCKER-USER -p tcp -m multiport --dports 5432 -j f2b-postgresql-tallied`
  and `-A f2b-postgresql-tallied -s 203.0.113.77/32 -j DROP`; the ban reached
  OpenSearch (`fail2ban_ban`, `f2b_jail`, `client_ip`) and `fail2ban-bans`
  pushed "[homelab] fail2ban: 1 ban(s) in the last 6 h" at ntfy priority 2.
  `unbanip` removed the DROP line (the jump and the empty chain stay, as
  fail2ban leaves them until it stops).
- Passwordless `sudo -n fail2ban-client status postgresql-tallied` works for mcheli.

The DOCKER-USER jump is added at the first ban, not at jail start.

Fluent Bit's file output writes the Docker `log` field as is, which ends in a
newline, so the file has a blank line after each entry. fail2ban skips them.

## Weekly homelab check

`~/.claude/skills/homelab-weekly-check/remote-collect.sh` only runs its
fail2ban block when `sudo -n true` works, which it never does here, so it
still prints "needs sudo; skipped" even though `sudo -n fail2ban-client status`
is now allowed. To collect jail status the skill needs its fail2ban block gated
on `sudo -n /usr/bin/fail2ban-client status >/dev/null 2>&1` instead of
`SUDO_OK`, plus `status postgresql-tallied` next to `status sshd` (use the full
path `/usr/bin/fail2ban-client`: sudoers matches the exact command). Bans of
every jail are in OpenSearch either way (`container_name:fail2ban and
event_type:fail2ban_ban`).
