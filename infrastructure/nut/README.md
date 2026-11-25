# NUT: clean UPS shutdown for 83rr-poweredge

Host-level config (not a container) for [Network UPS Tools](https://networkupstools.org/)
2.8.1 from the Ubuntu 24.04 archive, so the R630 shuts down cleanly when its UPS
runs on battery.

**Why:** in the 2026-11-17 outage the UPS (CyberPower CP1500PFCRM2U) carried the
server for about 14 minutes and then it died hard. Nothing on the host knew the
power was out. Hard power losses have bitten before (the 2026-05-17 hard reboot left
Seafile crash-looping, see `infrastructure/systemd/docker-wait-storage.conf`), and the
databases and the `/storage` RAID array are better off with a clean shutdown.

## Behaviour

1. **Mains lost** → UPS goes on battery (`ONBATT`). ntfy push (high), wall + syslog,
   and a 5-minute timer starts (`upssched`, timer `onbatt-shutdown`).
2. **Mains back within 5 minutes** → timer cancelled, ntfy push "back on mains". Nothing else happens.
3. **Still on battery after 5 minutes** → `upssched-cmd` sends "On battery 5 min:
   shutting the R630 down now" and runs `upsmon -c fsd`. upsmon sets forced shutdown
   (FSD), writes `/etc/killpower` and runs `SHUTDOWNCMD`: first
   `/etc/nut/pre-shutdown.sh` (capped at 120 s), then `/sbin/shutdown -h +0`. Docker
   stops the containers in the normal way.
   - **Game worlds first:** `pre-shutdown.sh` saves ARK (`asa`: RCON `Broadcast`, then
     `SaveWorld`, then waits until the `.ark` file has been rewritten; about 4 s) and
     Minecraft (RCON `say`, then `save-all flush`). ARK ignores SIGTERM under Proton,
     so the shutdown's `docker stop` always ends in SIGKILL (docker.service stops
     after 90 s). Without the save, everything since the last autosave (every ~2 h 15 min)
     would be lost. Minecraft stops cleanly on SIGTERM; the flush just makes sure
     nothing depends on its 10 s stop timeout.
   - It saves but does **not** `docker stop` them: a manual stop marks an
     `unless-stopped` container as stopped by hand, and Docker would then leave it off
     when the R630 boots after the outage.
   - Every step is best effort (a missing container or an RCON failure is logged under
     `nut-pre-shutdown` and skipped) and the script always exits 0, so the shutdown
     goes ahead regardless.
   - Budget: the shutdown starts at 5 min on battery, the save takes well under a
     minute (120 s at most), and the halt about 1.5 min. On 2026-11-17 the UPS
     lasted ~14 min.
4. **Backstop:** if the UPS reports low battery (`OB LB`) before the 5 minutes are up
   (old battery, high load), upsmon shuts down straight away without waiting for the timer.
   If the UPS stops answering while on battery, upsmon treats it as low battery after
   `DEADTIME` (25 s) and shuts down too.
5. **After the host halts**, the systemd shutdown hook from the nut package
   (`/usr/lib/systemd/system-shutdown/nutshutdown`) sees `/etc/killpower` and runs
   `upsdrvctl shutdown`: the UPS cuts its output 60 s later (`offdelay`) and switches
   it back on 120 s after mains returns (`ondelay`). This power cycle happens even when
   power came back during the shutdown, so the server never stays halted with power present.
6. **The R630 boots by itself** when the UPS output comes back, **only if** its
   power-restore policy is "always on" (see [Power restore policy](#power-restore-policy-r630)).

Every event (ONLINE, ONBATT, LOWBATT, FSD, COMMOK, COMMBAD, SHUTDOWN, REPLBATT, NOCOMM)
also goes to syslog, wall and ntfy topic `homelab`:

| Event | ntfy priority |
|---|---|
| on battery, connection lost (COMMBAD), UPS unreachable (NOCOMM, at most hourly), 5-min shutdown | high |
| low battery, FSD, host halting | urgent |
| back on mains, battery needs replacing | default |
| connection (re)established (COMMOK) | low |

Pushes go first to the local nginx (`--resolve ntfy.markcheli.com:443:127.0.0.1`, pinned to
the Cloudflare origin cert), so they get into ntfy even when the internet is down
(phones fetch them once it's back). If that fails it tries the public URL. A failed push
never blocks the shutdown, and the token is never on a command line or in a log.

## Files

| Repo file | Installed as | Notes |
|---|---|---|
| `nut.conf` | `/etc/nut/nut.conf` | `MODE=standalone` |
| `ups.conf` | `/etc/nut/ups.conf` | UPS `cp1500`, `usbhid-ups`, vendor id 0764, offdelay 60 / ondelay 120 |
| `upsd.conf` | `/etc/nut/upsd.conf` | listens on 127.0.0.1 and ::1 only |
| `upsd.users.template` | `/etc/nut/upsd.users` | user `upsmon` (primary); password filled in at install |
| `upsmon.conf` | `/etc/nut/upsmon.conf` | same password placeholder; shutdown + notify settings |
| `upssched.conf` | `/etc/nut/upssched.conf` | 5-min timer + notices |
| `upssched-cmd` | `/etc/nut/upssched-cmd` (750) | logger + ntfy + `upsmon -c fsd` |
| `pre-shutdown.sh` | `/etc/nut/pre-shutdown.sh` (750) | run by `SHUTDOWNCMD` as root: saves the ARK + Minecraft worlds, ≤ 120 s, never fails |
| (generated) | `/etc/nut/ntfy.env` | `NTFY_URL`, `NTFY_TOPIC`, `NTFY_TOKEN` (from the repo `.env`), `NTFY_CACERT` |
| `../nginx/certs/wildcard-markcheli.crt` | `/etc/nut/ntfy-origin.crt` (644) | public cert, pinned for the local push |

All of `/etc/nut` is `root:nut`, mode 640 unless noted. The package's own copies are kept
once as `<file>.dist`. The upsmon password is random (32 chars), made on first install,
reused on later runs, and never printed or committed.

## Physical step (Mark)

Plug a USB cable from the UPS's **USB-B port** (back panel) into **any USB port on the
R630**. Nothing else: the udev rule in the nut package gives the `nut` group access to the
device and systemd retries the driver, so it picks the UPS up within a few seconds.
Installing before the cable is in is fine.

## Install

On the server, from the repo checkout:

```bash
cd ~/83rr-poweredge
git pull
sudo infrastructure/nut/install.sh            # installs packages + config, restarts NUT, prints status
sudo infrastructure/nut/install.sh --check    # status only, changes nothing (sudo not needed)
```

Re-run it after any change in this folder. Without the UPS plugged in, the driver
(`nut-driver@cp1500`) shows `failed`/`activating`: that's expected and harmless.
upsmon will then send one "UPS unreachable" push (at most hourly) until the cable is in.

## Verify (read-only, safe for agents)

```bash
lsusb -d 0764:                                 # the CyberPower shows up (product 0601)
upsc cp1500                                    # all variables; ups.status should be "OL" (or "OL CHRG")
upsc cp1500 ups.status
upsc cp1500 battery.runtime                    # seconds of runtime at the current load
systemctl is-active nut-driver@cp1500 nut-server nut-monitor
journalctl -u nut-monitor -u nut-driver@cp1500 --since today
journalctl -t upssched-cmd --since today       # what the notify script did
journalctl -t nut-pre-shutdown                 # world saves before the last UPS shutdown
sudo infrastructure/nut/install.sh --check
```

Expected: the three units `active`, `ups.status` `OL`, and `upsmon` logging
"Communications with UPS cp1500@localhost established".

## Power restore policy (R630)

After the UPS power-cycles its output, the R630 has to power on by itself when AC comes
back. Dell's default ("last state") would keep it **off**, because it was off when power
went away. Check it and set it to "always on" (needs `ipmitool`, not installed yet, and sudo):

```bash
sudo apt-get install -y ipmitool
sudo ipmitool chassis status | grep -i 'power restore'    # want: Power Restore Policy : always-on
sudo ipmitool chassis policy always-on                    # set it
```

The same setting is "AC Power Recovery" in the BIOS (System Setup → System BIOS →
System Security) and in iDRAC. Agents: check only, don't change it without Mark's yes.
Set to `always-on` on 2026-11-25 (it was `previous`); undo with `sudo ipmitool chassis policy previous`.

## Real test (needs Mark's yes; cuts mains)

**Not run by agents.** This really shuts the server down and power-cycles it. Pick a quiet
time, confirm a recent backup, and be next to the rack.

1. `sudo infrastructure/nut/install.sh --check` — all green, `ups.status` = `OL`.
2. Pull the UPS's mains plug from the wall. Expect within seconds: ntfy "UPS on battery",
   `wall` message, `upsc cp1500 ups.status` = `OB DISCHRG`.
3. Short test: plug mains back in after ~1 minute. Expect "UPS back on mains", no shutdown
   (`journalctl -t upssched-cmd` shows the timer was cancelled).
4. Full test: unplug again and wait. At 5 minutes: "R630 shutting down", FSD, "R630 halting".
   The host halts; ~60 s later the UPS output switches off.
5. Plug mains back in. ~120 s later the UPS output comes back and the R630 boots.
   Then run `docs/POST_REBOOT_CHECKLIST.md`.

Quicker alternative for step 4 (still a real shutdown and power cycle, mains stays in):
`sudo upsmon -c fsd`.

## Roll back

```bash
sudo systemctl disable --now nut-monitor nut-server nut-driver-enumerator.path nut-driver.target
sudo apt-get remove nut-server nut-client      # /etc/nut stays; *.dist are the package originals
```
