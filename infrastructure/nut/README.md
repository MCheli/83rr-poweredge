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
3. **Still on battery after 5 minutes** → `upssched-cmd` calls the Home Assistant
   power-restore webhook (see [Power restore (Home Assistant)](#power-restore-home-assistant);
   5 s cap, a failure is logged and ignored), sends "On battery 5 min:
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
6. **Coming back:**
   - Outage **shorter than the battery**: the UPS never loses output, so the R630 sees no
     AC loss and would stay off (the NAS too: DSM's "restart when power supply issue is
     fixed" only covers a real AC loss). Home Assistant, which stays up on the UPS,
     wakes both with Wake-on-LAN once mains has been back for 2 minutes
     ([Power restore (Home Assistant)](#power-restore-home-assistant)). If that fails:
     the R630's power button (iDRAC has no login available) and the NAS's button.
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
  3493 is in `ALLOWED_PORTS` of `scripts/emit_security_telemetry.sh`, so the
  `security-unexpected-listen-port` monitor treats it as expected.
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

The cost is that after an outage shorter than the battery the R630 and the NAS stay
off, since they never see AC come back. Mark chose (2026-11-25) to have Home Assistant
power them back on: [Power restore (Home Assistant)](#power-restore-home-assistant).
The alternative, turning kill-power back on (uncomment `POWERDOWNFLAG /etc/killpower`,
drop the guard in install.sh, re-run it), would bring everything back by itself, but
the router and Home Assistant would lose power ~7 min into every outage that long.

## Power restore (Home Assistant)

Built 2026-11-25. Home Assistant (192.168.1.121, on the UPS) wakes the R630 and the NAS
with Wake-on-LAN after a short outage.

1. **Webhook:** just before the shutdown (5 min on battery), `upssched-cmd` POSTs
   `{"source":"r630-nut"}` to `HA_WEBHOOK_URL` from **`/etc/nut/ha.env`** on the R630
   (root:nut 640, **not in git**; the webhook id `r630_ups_shutdown_<32 hex>` is the
   secret, also in the HA automation's trigger). curl reads the URL on stdin, so the id is
   not in `ps` or the logs. install.sh never overwrites ha.env; on a fresh host it writes an
   empty placeholder and `--check` shows "placeholder". The LAN URL is used because
   home.markcheli.com is proxied by the R630 and goes down with it.
2. **HA automation** `r630_ups_power_restore` ("UPS: power R630 and NAS back on after
   outage", `automation.ups_power_r630_and_nas_back_on_after_outage`, mode single, created
   through the REST API; there is no YAML for it): webhook trigger (POST, local only) →
   wait 5 min (both halt) → wait until **house mains** is back: at least 2 of the five
   ESPHome minisplit heads (`climate.*_head`) and the Kasa `switch.bedroom_tv` are not
   unavailable/unknown, for 2 min (they are on mains, not the UPS, and drop within a
   minute of a cut); gives up after 24 h → presses **`button.wake_r630`** and
   **`button.wake_nas`** 3 times, 2 min apart → persistent notification and a push to
   `notify.mobile_app_iphone`.
3. **Wake on LAN** integration entries (UI: Settings → Devices → Wake on LAN), broadcast
   192.168.1.255:9: "Wake R630" = eno1 `ec:f4:bb:e6:f7:f4`, "Wake NAS" = `90:09:d0:0c:f4:e6`
   (WoL enabled in DSM).
4. **R630 NIC:** eno1 (igb) supports `Wake-on: pumbg`; Ubuntu leaves it at `d`. install.sh
   installs `10-83rr-eno1-wol.link` to `/etc/systemd/network/` (matches the permanent MAC,
   `WakeOnLan=magic`, naming lines copied from `99-default.link` so the name stays eno1;
   applied at every boot) and runs `ethtool -s eno1 wol g` for the running boot. Not
   confirmable from Linux: the BIOS/iDRAC side (System Setup → Device Settings → NIC
   port 1 → Wake On LAN, and that the board keeps standby power to the NIC in S5). Without
   iDRAC access only a real test shows it.

Set up / replace the webhook id (one time; keep the HA trigger and ha.env in step):

```bash
# on the R630, as root; <id> = r630_ups_shutdown_ + 32 hex chars
sudo install -o root -g nut -m 640 /dev/null /etc/nut/ha.env
sudoedit /etc/nut/ha.env     # HA_WEBHOOK_URL=http://192.168.1.121:8123/api/webhook/<id>
sudo infrastructure/nut/install.sh --check    # ha.env webhook: set, root:nut 640
```

Safe test (no shutdown): POST the webhook from the R630 as `nut` using ha.env (not via
`upssched-cmd`, whose `onbatt-shutdown` branch would really shut down), check the
automation's `last_triggered` / trace, then cancel the run with `automation.turn_off` +
`automation.turn_on`. Pressing "Wake NAS" while the NAS runs is harmless. An end-to-end
test needs a planned shutdown ([Real test](#real-test-needs-marks-yes-cuts-mains)).

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
| `upssched-cmd` | `/etc/nut/upssched-cmd` (750) | logger + ntfy; at 5 min the HA webhook, `sudo -n pre-shutdown.sh`, then `upsmon -c fsd` |
| `10-83rr-eno1-wol.link` | `/etc/systemd/network/10-83rr-eno1-wol.link` (644, root:root) | Wake-on-LAN (magic) on eno1 at every boot |
| (by hand, not in git) | `/etc/nut/ha.env` | `HA_WEBHOOK_URL` (Home Assistant power-restore webhook); install.sh keeps it, or writes an empty placeholder |
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

**Done 2026-11-25:** the driver sees the UPS (`device.model` CP1500PFCRM2U; lsusb calls it
PR1500LCDRT2U), `ups.status` `OL`, `ups.load` 28 % of 1000 W (≈ 280 W, close to Home
Assistant's "Server Wattage" plug at ≈ 296 W), `battery.runtime` 1500 s at that load.

**The 72 "Failed to start nut-driver@cp1500" lines** in the weekly report of 2026-11-28
come from that install and nothing later. Between 14:37:53 and 14:55:27 UTC on 2026-11-25 the
driver (then still named `cp1500`) was enabled while the UPS had no USB link, and systemd
restarted it every ~15 s ("No matching HID UPS found"). The extra "insufficient permissions
on everything" line refers to the Dell hubs and the iDRAC virtual NIC, not to the UPS. The
kernel first saw `idVendor=0764` at 14:55:21 when the cable went in (one reconnect at
14:55:28). Checked 2026-11-28: no driver errors and no USB disconnects since the 15:56 boot,
`upsc` OL at 100 %, NAS still a client. The lines drop out of the 7-day window on
2026-12-02. If driver failures show up again, check
`journalctl -k | grep -E 'idVendor=0764|USB disconnect'` first: a 0764 disconnect means the
cable or port.

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
5. Plug mains back in. About 2 min after the minisplit heads reconnect (and at least
   5 min after the webhook), Home Assistant presses "Wake R630" and "Wake NAS" (3 times,
   2 min apart) and notifies. Expect both to boot; if not, use their power buttons and
   check the NIC's Wake-on-LAN in the R630 BIOS. Then run `docs/POST_REBOOT_CHECKLIST.md`.

Quicker alternative for step 4 (still a real shutdown of the R630 **and the NAS**, mains
stays in): `sudo upsmon -c fsd`.

## Roll back

```bash
sudo systemctl disable --now nut-monitor nut-server nut-driver-enumerator.path nut-driver.target
sudo rm /etc/sudoers.d/nut-pre-shutdown /etc/systemd/system/nut-server.service.d/83rr-network-online.conf
sudo ufw delete allow proto tcp from 192.168.1.201 to any port 3493
sudo apt-get remove nut-server nut-client      # /etc/nut stays; *.dist are the package originals
```
