#!/bin/bash
# /etc/nut/pre-shutdown.sh — managed by 83rr-poweredge infrastructure/nut/install.sh
# Runs from upsmon's SHUTDOWNCMD (as root, via sh -c) just before
# `/sbin/shutdown -h +0`: saves the game worlds so the host shutdown loses
# nothing.
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
# Hard cap: DEADLINE seconds for the whole script (SHUTDOWNCMD also wraps it in
# `timeout 120`). Every step is best effort: a missing container, docker or
# RCON error is logged and skipped, and the script always exits 0 so the
# shutdown goes ahead.
#
# Install (with the rest of infrastructure/nut/):
#   sudo infrastructure/nut/install.sh
set -u

DEADLINE=110
TAG=nut-pre-shutdown
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

log "UPS shutdown: saving game worlds before halting (cap ${DEADLINE} s)"
if command -v docker >/dev/null 2>&1; then
    save_ark
    save_minecraft
else
    log "docker not found, nothing to save"
fi
log "done in $(( SECONDS - START )) s, handing over to shutdown"
exit 0
