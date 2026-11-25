#!/bin/bash
# /etc/nut/pre-shutdown.sh — managed by 83rr-poweredge infrastructure/nut/install.sh
# Runs as root before the R630 halts for a power cut, from two places:
#   - upssched-cmd at 5 minutes on battery (as `sudo -n`, rule in
#     /etc/sudoers.d/nut-pre-shutdown), BEFORE `upsmon -c fsd`: FSD sends the
#     Synology NAS into safe mode at once, so /mnt/nas has to go first;
#   - upsmon's SHUTDOWNCMD, just before `/sbin/shutdown -h +0` (the low-battery
#     path goes straight to FSD without the 5-minute handler).
# Safe to run twice: a second run within STAMP_FRESH seconds of a finished one
# skips the world saves, and the unmount is a no-op once /mnt/nas is gone.
# Concurrent runs wait for each other (flock).
#
# Steps:
#   /mnt/nas   CIFS share on the NAS (fstab, soft,nofail). umount (20 s), then
#              lazy umount as the fallback; never blocks. Unmounted first, while
#              the NAS is still up. Mount state is read from /proc/mounts, which
#              never touches the (maybe dead) share.
#   asa        ARK ignores SIGTERM under Proton, so the shutdown's docker stop
#              ends in SIGKILL (docker.service gives up after 90 s, asa's grace
#              is 120 s). RCON Broadcast + SaveWorld first, then wait until
#              the .ark file is rewritten (about 4 s on 2026-11-25).
#   minecraft  RCON say + `save-all flush` (synchronous). Docker's SIGTERM at
#              shutdown then stops it the normal way.
# The containers are NOT stopped here: a manual `docker stop` marks an
# unless-stopped container as stopped by hand, so Docker would not start it
# again when the R630 boots after the outage.
#
# Hard cap: DEADLINE seconds for the whole script (both callers also wrap it
# in `timeout 120`). Every step is best effort: a missing container, docker,
# RCON or umount error is logged and skipped, and the script always exits 0
# so the shutdown goes ahead.
#
# Install (with the rest of infrastructure/nut/):
#   sudo infrastructure/nut/install.sh
set -u

DEADLINE=110
TAG=nut-pre-shutdown
NAS_MOUNT=/mnt/nas
UMOUNT_WAIT=20
LOCK=/run/lock/nut-pre-shutdown.lock
STAMP=/run/nut-pre-shutdown.done
STAMP_FRESH=600
ARK_SAVE=/home/gameserver/server-files/ShooterGame/Saved/SavedArks/TheIsland_WP/TheIsland_WP.ark
ARK_SAVE_WAIT=60
MSG="Power outage: the server is shutting down now. World saved."
START=$SECONDS

log() { logger -t "$TAG" -- "$*" 2>/dev/null || true; }

# left [CAP]: seconds left before DEADLINE, at most CAP and at least 1
# (`timeout 0` would mean no timeout at all)
left() {
    local rest=$(( DEADLINE - (SECONDS - START) ))
    (( rest < 1 )) && rest=1
    if [[ -n "${1:-}" ]] && (( rest > $1 )); then rest=$1; fi
    echo "$rest"
}

running() {
    [[ "$(timeout "$(left 10)" docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == true ]]
}

nas_mounted() {
    awk -v m="$NAS_MOUNT" '$2 == m { found = 1 } END { exit !found }' /proc/mounts
}

unmount_nas() {
    if ! nas_mounted; then log "${NAS_MOUNT}: not mounted, skipped"; return; fi
    if timeout "$(left "$UMOUNT_WAIT")" umount "$NAS_MOUNT" 2>/dev/null; then
        log "${NAS_MOUNT}: unmounted"
        return
    fi
    if nas_mounted && timeout "$(left 5)" umount -l "$NAS_MOUNT" 2>/dev/null; then
        log "${NAS_MOUNT}: busy or unreachable, lazily unmounted"
    elif nas_mounted; then
        log "${NAS_MOUNT}: unmount failed, left mounted"
    else
        log "${NAS_MOUNT}: unmounted"
    fi
}

save_ark() {
    local before after t
    if ! running asa; then log "asa: not running, skipped"; return; fi
    before=$(timeout "$(left 10)" docker exec asa stat -c %Y "$ARK_SAVE" 2>/dev/null || echo 0)
    timeout "$(left 10)" docker exec asa asa-ctrl rcon --exec "Broadcast $MSG" >/dev/null 2>&1 || true
    if ! timeout "$(left 30)" docker exec asa asa-ctrl rcon --exec SaveWorld >/dev/null 2>&1; then
        log "asa: SaveWorld failed or timed out"
        return
    fi
    t=$SECONDS
    while (( SECONDS - t < ARK_SAVE_WAIT )) && (( SECONDS - START < DEADLINE )); do
        after=$(timeout "$(left 5)" docker exec asa stat -c %Y "$ARK_SAVE" 2>/dev/null || echo 0)
        if [[ "$after" != 0 && "$after" != "$before" ]]; then
            log "asa: world saved ($(( SECONDS - t )) s after SaveWorld)"
            return
        fi
        sleep 2
    done
    log "asa: SaveWorld sent but the save file did not change within ${ARK_SAVE_WAIT} s"
}

save_minecraft() {
    if ! running minecraft; then log "minecraft: not running, skipped"; return; fi
    timeout "$(left 10)" docker exec minecraft rcon-cli say "$MSG" >/dev/null 2>&1 || true
    if timeout "$(left 45)" docker exec minecraft rcon-cli save-all flush >/dev/null 2>&1; then
        log "minecraft: world saved (save-all flush)"
    else
        log "minecraft: save-all flush failed or timed out"
    fi
}

# Wait for a run already in progress (if any), but never past the deadline.
if { exec 9>"$LOCK"; } 2>/dev/null; then
    flock -w "$(left)" 9 2>/dev/null || log "lock wait timed out, going ahead"
fi

log "UPS shutdown: unmounting ${NAS_MOUNT} and saving game worlds before halting (cap ${DEADLINE} s)"
unmount_nas
if [[ -e "$STAMP" ]] &&
   (( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) < STAMP_FRESH )); then
    log "worlds already saved by an earlier run, skipped"
elif command -v docker >/dev/null 2>&1; then
    save_ark
    save_minecraft
    touch "$STAMP" 2>/dev/null || true
else
    log "docker not found, nothing to save"
fi
log "done in $(( SECONDS - START )) s, handing over to shutdown"
exit 0
