# NUT: clean UPS shutdown for 83rr-poweredge

Host-level config (not a container) for [Network UPS Tools](https://networkupstools.org/)
2.8.1 from the Ubuntu 24.04 archive, so the R630 shuts down cleanly when its UPS
runs on battery.

**Why:** in the 2026-11-17 outage the UPS (CyberPower CP1500PFCRM2U) carried the
server for about 14 minutes and then it died hard. Nothing on the host knew the
power was out. Hard power losses have bitten before (the 2026-05-17 hard reboot left
Seafile crash-looping, see `infrastructure/systemd/docker-wait-storage.conf`), and the
databases and the `/storage` RAID array are better off with a clean shutdown.

**Goal (Mark, 2026-11-25):** the R630 and the Synology NAS (MarksNAS) go off fairly
quickly, and the battery then keeps the **router** (most important), Home Assistant
and the rest of the network running as long as it can. So the R630 shuts down after
5 minutes on battery, the NAS follows it as a NUT network client, and the UPS does
**not** cut its outlets afterwards (kill-power is off).

The UPS is named **`ups`** (it was `cp1500` until 2026-11-25) because DSM's
"Synology UPS server" mode only looks for a UPS of that name.

## Behaviour

1. **Mains lost** → UPS goes on battery (`ONBATT`). ntfy push (high), wall + syslog,
   and a 5-minute timer starts (`upssched`, timer `onbatt-shutdown`).
2. **Mains back within 5 minutes** → timer cancelled, ntfy push "back on mains". Nothing else happens.
3. **Still on battery after 5 minutes** → `upssched-cmd` sends "On battery 5 min:
   shutting the R630 and the NAS down now", then:
   1. runs `/etc/nut/pre-shutdown.sh` **as root** (`sudo -n`, the one rule in
      `/etc/sudoers.d/nut-pre-shutdown`; capped at 120 s): unmounts `/mnt/nas` and saves
      the game worlds. This has to happen **before** FSD, because the moment the
      primary declares FSD, DSM starts going into safe mode, before `SHUTDOWNCMD` runs.
   2. runs `upsmon -c fsd`. upsmon sets forced shutdown (FSD) on upsd, the NAS (a
      secondary) sees it and goes into safe mode, upsmon waits for it to log off
      (`HOSTSYNC`, 15 s by default) and runs `SHUTDOWNCMD`: `pre-shutdown.sh` again
      (a no-op by then, see below), then `/sbin/shutdown -h +0`. Docker stops the
      containers in the normal way.
   - **NAS share first:** `/mnt/nas` (CIFS `//MarksNAS/Performance`, fstab, `soft,nofail`)
     is unmounted with a plain `umount` (20 s), then a lazy `umount -l` as the
     fallback, so a busy or dead share never blocks the shutdown. The mount state comes
     from `/proc/mounts`, which never touches the share.
   - **Safe to run twice:** a second run within 10 minutes of a finished one skips the
     world saves (stamp `/run/nut-pre-shutdown.done`), the unmount is a no-op once the
     share is gone, and concurrent runs wait for each other (`flock`).
   - **Game worlds:** `pre-shutdown.sh` saves ARK (`asa`: RCON `Broadcast`, then
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
   - Budget: the shutdown starts at 5 min on battery, the unmount + saves take well
     under a minute (about 2 min at most), and the halt about 1.5 min. On 2026-11-17 the
     UPS lasted ~14 min with the R630 on it; with the R630 and the NAS off, the rest
     runs much longer.
4. **Backstop:** if the UPS reports low battery (`OB LB`) before the 5 minutes are up
   (old battery, high load), upsmon declares FSD straight away without waiting for the
   timer; `SHUTDOWNCMD` then runs `pre-shutdown.sh` (here the NAS may already be on its
   way into safe mode, so the unmount may end lazily). If the UPS stops answering while
   on battery, upsmon treats it as low battery after `DEADTIME` (25 s) and shuts down too.
5. **After the host halts**, the UPS keeps all its outlets on (kill-power is off, see
   [Kill-power (off)](#kill-power-off)). The systemd shutdown hook
   (`/usr/lib/systemd/system-shutdown/nutshutdown`) finds no `/etc/killpower` and skips
   the UPS command ("Not in FSD (killpower) mode").
6. **Coming back** (see [Kill-power (off)](#kill-power-off) for the open decision):
   - Outage **shorter than the battery**: the UPS never loses output, so the R630 sees no
     AC loss and **stays off** until someone powers it on (iDRAC, or the front power
     button). The NAS likewise stays off (DSM's "restart when power supply issue is
     fixed" only covers a real AC loss), so it needs its power button or Wake-on-LAN.
   - Outage **longer than the battery**: the UPS runs flat and its outlets go dark; when
     mains returns the UPS powers them up and the R630 boots by itself because its
     power-restore policy is "always on" (see [Power restore policy](#power-restore-policy-r630));
     the NAS does too if "Restart automatically when power supply issue is fixed" is on.

## Synology NAS (MarksNAS) as a NUT client

The NAS (`MarksNAS`, **192.168.1.201**, the address the R630 mounts `/mnt/nas` from;
Synology MAC prefix 90:09:d0) watches the same UPS over the network and goes into safe
mode (DSM's clean shutdown) when the R630 declares FSD.

- **DSM:** Control Panel → Hardware & Power → UPS: enable UPS support, network UPS
  type **Synology UPS server**, server IP **192.168.1.179**. Time before safe mode: a
  little longer than the R630's 5 minutes (7 if DSM allows it, else the nearest option
  ≥ 5), so the NAS still goes by itself if the R630 is gone. Hardware & Power →
  General: "Restart automatically when power supply issue is fixed" ON.
- **Login:** DSM's Synology UPS server mode logs in as `monuser` / `secret` and asks for
  UPS `ups`. Both are fixed by DSM and publicly documented, so they are in
  `upsd.users.template` as-is: `upsmon secondary` (it can read and follow FSD, not set it).
- **Listen:** `upsd.conf` adds `LISTEN 192.168.1.179 3493` next to loopback. A nut-server
  drop-in (`/etc/systemd/system/nut-server.service.d/83rr-network-online.conf`) starts
  upsd after `network-online.target`, since upsd skips an address that is not up yet
  (the R630's LAN address comes from DHCP).
- **Firewall:** install.sh adds `ufw allow proto tcp from 192.168.1.201 to any port 3493`.
  No other host can reach upsd. If the NAS's address ever changes, update `NAS_IP` in
  install.sh and the ufw rule (`sudo ufw status numbered`, delete the old one).
- `nut.conf` is `MODE=netserver` (was `standalone`) to match.

## Kill-power (off)

`POWERDOWNFLAG` is commented out in `upsmon.conf` (2026-11-25), and install.sh refuses
a config that sets it. NUT 2.8.1 has no built-in default for it, so upsmon never writes
`/etc/killpower` and the UPS is never told to cut its output.

**Why:** with kill-power, the UPS cuts **all** its outlets about a minute after the R630
halts (`offdelay` 60 s), which would take the router and Home Assistant down about 7
minutes into an outage: the opposite of what Mark wants.

**Open decision for Mark:** the cost is that after an outage shorter than the battery
the R630 (and the NAS) stay off until powered on by hand (iDRAC at the R630's iDRAC
address, or the power button). Options:
- **Keep it this way** (current): the network stays up longest; power the R630 on from
  iDRAC after the outage (and the NAS from its button or Wake-on-LAN).
- **Turn kill-power back on:** uncomment `POWERDOWNFLAG /etc/killpower`, drop the guard
  in install.sh, re-run it. Everything comes back by itself, but the router and Home
  Assistant lose power ~7 min into every outage that lasts that long.
- **Later, automate the power-on:** e.g. Home Assistant (which stays up on the UPS)
  powers the R630 on through iDRAC/IPMI and wakes the NAS once mains has been back for a
  few minutes. Not built.

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
| `nut.conf` | `/etc/nut/nut.conf` | `MODE=netserver` |
| `ups.conf` | `/etc/nut/ups.conf` | UPS `ups`, `usbhid-ups`, vendor id 0764, offdelay 60 / ondelay 120 (unused while kill-power is off) |
| `upsd.conf` | `/etc/nut/upsd.conf` | listens on 127.0.0.1, ::1 and 192.168.1.179 (for the NAS) |
| `upsd.users.template` | `/etc/nut/upsd.users` | `upsmon` (primary; password filled in at install), `monuser` (secondary, DSM's fixed login) |
| `upsmon.conf` | `/etc/nut/upsmon.conf` | same password placeholder; shutdown + notify settings; no `POWERDOWNFLAG` |
| `upssched.conf` | `/etc/nut/upssched.conf` | 5-min timer + notices |
| `upssched-cmd` | `/etc/nut/upssched-cmd` (750) | logger + ntfy; at 5 min `sudo -n pre-shutdown.sh`, then `upsmon -c fsd` |
| `pre-shutdown.sh` | `/etc/nut/pre-shutdown.sh` (750) | as root, from upssched-cmd and `SHUTDOWNCMD`: unmounts `/mnt/nas`, saves the ARK + Minecraft worlds, ≤ 120 s, never fails, safe twice |
| `sudoers-nut-pre-shutdown` | `/etc/sudoers.d/nut-pre-shutdown` (440, root:root) | user `nut` may run exactly `/etc/nut/pre-shutdown.sh` (no arguments) as root; checked with `visudo -c` |
| `nut-server-network-online.conf` | `/etc/systemd/system/nut-server.service.d/83rr-network-online.conf` (644) | upsd starts after `network-online.target` |
| (install.sh) | ufw rule | TCP 3493 from 192.168.1.201 (the NAS) only |
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
(`nut-driver@ups`) shows `failed`/`activating`: that's expected and harmless.
upsmon will then send one "UPS unreachable" push (at most hourly) until the cable is in.

## Verify (read-only, safe for agents)

```bash
lsusb -d 0764:                                 # the CyberPower shows up (product 0601)
upsc -l localhost                              # lists: ups
upsc ups@localhost                             # all variables; ups.status should be "OL" (or "OL CHRG")
upsc ups@localhost ups.status
upsc ups@localhost battery.runtime             # seconds of runtime at the current load
upsc -c ups@localhost                          # clients: 127.0.0.1 (upsmon) and 192.168.1.201 (the NAS)
ss -ltn 'sport = :3493'                        # 127.0.0.1, [::1] and 192.168.1.179
sudo ufw status | grep 3493                    # ALLOW from 192.168.1.201 only
systemctl is-active nut-driver@ups nut-server nut-monitor
journalctl -u nut-monitor -u nut-driver@ups --since today
journalctl -t upssched-cmd --since today       # what the notify script did
journalctl -t nut-pre-shutdown                 # unmount + world saves before the last UPS shutdown
sudo -u nut sudo -n -l /etc/nut/pre-shutdown.sh   # prints the path: the sudo rule works (does not run it)
sudo infrastructure/nut/install.sh --check
```

Expected: the three units `active`, `ups.status` `OL`, `upsmon` logging
"Communications with UPS ups@localhost established", kill-power off and no `/etc/killpower`.

## Power restore policy (R630)

When the UPS output comes back after the battery ran out (with kill-power off, that is
the only case where the R630 sees AC come back), the R630 has to power on by itself.
Dell's default ("last state") would keep it **off**, because it was off when power
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
   `wall` message, `upsc ups@localhost ups.status` = `OB DISCHRG`, and DSM's UPS page
   showing "on battery".
3. Short test: plug mains back in after ~1 minute. Expect "UPS back on mains", no shutdown
   (`journalctl -t upssched-cmd` shows the timer was cancelled).
4. Full test: unplug again and wait. At 5 minutes: "R630 shutting down", `/mnt/nas`
   unmounted (`journalctl -t nut-pre-shutdown`), FSD, the NAS goes into safe mode,
   "R630 halting". The host halts; the UPS output (router, Home Assistant) stays on.
5. Plug mains back in. Nothing powers on by itself (kill-power is off): power the R630
   on from iDRAC or its button, and the NAS from its button. Then run
   `docs/POST_REBOOT_CHECKLIST.md`.

Quicker alternative for step 4 (still a real shutdown of the R630 **and the NAS**, mains
stays in): `sudo upsmon -c fsd`.

## Roll back

```bash
sudo systemctl disable --now nut-monitor nut-server nut-driver-enumerator.path nut-driver.target
sudo rm /etc/sudoers.d/nut-pre-shutdown /etc/systemd/system/nut-server.service.d/83rr-network-online.conf
sudo ufw delete allow proto tcp from 192.168.1.201 to any port 3493
sudo apt-get remove nut-server nut-client      # /etc/nut stays; *.dist are the package originals
```
