#!/bin/bash
# install.sh — install/refresh the NUT (Network UPS Tools) UPS shutdown config
# on 83rr-poweredge. Idempotent: safe to run again after any change in
# infrastructure/nut/. See infrastructure/nut/README.md.
#
# Usage (on the server, from the repo checkout):
#   sudo infrastructure/nut/install.sh           # install packages + config, restart NUT
#   sudo infrastructure/nut/install.sh --check   # status only, changes nothing
#
# What it does:
#   - apt-get install nut-server nut-client
#   - copies nut.conf ups.conf upsd.conf upssched.conf into /etc/nut
#     (root:nut 640), upssched-cmd and pre-shutdown.sh (root:nut 750); the package's own
#     files are kept once as <name>.dist
#   - renders upsd.users + upsmon.conf with the upsmon password: random on
#     first install, reused from /etc/nut/upsd.users afterwards (never printed)
#   - writes /etc/nut/ntfy.env from NTFY_PUBLISH_TOKEN in the repo .env, and
#     /etc/nut/ntfy-origin.crt (the public origin cert nginx serves, pinned for
#     the local push path)
#   - enables + restarts the driver enumerator, nut-server and nut-monitor
# With the UPS USB cable not plugged in yet the driver (nut-driver@cp1500)
# simply fails to find it and systemd keeps retrying; nothing shuts down.
set -euo pipefail

NUT_DIR=/etc/nut
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SRC_DIR}/../.." && pwd)"
REPO_ENV="${REPO_DIR}/.env"
ORIGIN_CERT="${REPO_DIR}/infrastructure/nginx/certs/wildcard-markcheli.crt"
NTFY_URL="https://ntfy.markcheli.com"
NTFY_TOPIC="homelab"
PLACEHOLDER="__UPSMON_PASSWORD__"
UNITS=(nut-driver@cp1500.service nut-server.service nut-monitor.service)

CHECK_ONLY=false
case "${1:-}" in
    "") ;;
    --check) CHECK_ONLY=true ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (use --check or nothing)" >&2; exit 2 ;;
esac

status() {
    echo "== NUT status"
    if ! command -v upsc >/dev/null 2>&1; then
        echo "NUT is not installed (no upsc)."
        return 0
    fi
    local u
    for u in "${UNITS[@]}"; do
        printf '  %-28s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || true)"
    done
    printf '  %-28s %s\n' "/run/nut" "$(stat -c '%U:%G %a' /run/nut 2>/dev/null || echo missing)"
    local hook
    hook=$(ls /usr/lib/systemd/system-shutdown/nutshutdown /lib/systemd/system-shutdown/nutshutdown 2>/dev/null | head -n1 || true)
    printf '  %-28s %s\n' "kill-power shutdown hook" "${hook:-MISSING (UPS will not power-cycle the host)}"
    printf '  %-28s %s\n' "lsusb 0764 (CyberPower)" "$(lsusb -d 0764: 2>/dev/null || echo 'not found (USB cable not plugged in?)')"
    printf '  %-28s %s\n' "upsc cp1500 ups.status" "$(upsc cp1500 ups.status 2>&1 || true)"
    if [[ "$(systemctl is-active nut-driver@cp1500.service 2>/dev/null || true)" != active ]]; then
        echo "  Note: the driver is not running. Until the UPS USB cable is in, that is"
        echo "  expected and harmless: systemd retries and picks the UPS up once plugged."
    fi
}

if [[ "$CHECK_ONLY" == true ]]; then
    status
    exit 0
fi

if [[ $EUID -ne 0 ]]; then
    echo "run as root: sudo $0" >&2
    exit 1
fi

echo "== packages"
DEBIAN_FRONTEND=noninteractive apt-get install -y nut-server nut-client

getent group nut >/dev/null || { echo "group nut missing after install" >&2; exit 1; }

# put_file SRC DEST MODE: install root:nut, atomically, keeping the
# package's original once as DEST.dist
put_file() {
    local src="$1" dest="$2" mode="$3" tmp
    if [[ -e "$dest" && ! -e "${dest}.dist" ]] && ! grep -q '83rr-poweredge' "$dest"; then
        cp -p "$dest" "${dest}.dist"
    fi
    tmp=$(mktemp "${dest}.XXXXXX")
    cat "$src" > "$tmp"
    chown root:nut "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dest"
    echo "  ${dest} (${mode})"
}

# render TEMPLATE DEST: put_file with the placeholder replaced in memory
render() {
    local src="$1" dest="$2" content tmp
    content=$(<"$src")
    content="${content//"$PLACEHOLDER"/$UPSMON_PASSWORD}"
    tmp=$(mktemp)
    printf '%s\n' "$content" > "$tmp"
    put_file "$tmp" "$dest" 640
    rm -f "$tmp"
}

echo "== config -> ${NUT_DIR}"
umask 077
for f in nut.conf ups.conf upsd.conf upssched.conf; do
    put_file "${SRC_DIR}/${f}" "${NUT_DIR}/${f}" 640
done
put_file "${SRC_DIR}/upssched-cmd" "${NUT_DIR}/upssched-cmd" 750
put_file "${SRC_DIR}/pre-shutdown.sh" "${NUT_DIR}/pre-shutdown.sh" 750

# Reuse the password only from a upsd.users this script wrote.
UPSMON_PASSWORD=""
if [[ -f "${NUT_DIR}/upsd.users" ]] && grep -q '83rr-poweredge' "${NUT_DIR}/upsd.users"; then
    UPSMON_PASSWORD=$(awk '/^[[:space:]]*password[[:space:]]*=/ {sub(/^[^=]*=[[:space:]]*/, ""); print; exit}' "${NUT_DIR}/upsd.users")
fi
if [[ -z "$UPSMON_PASSWORD" || "$UPSMON_PASSWORD" == "$PLACEHOLDER" ]]; then
    UPSMON_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 || true)
    echo "  generated a new upsmon password (not shown)"
else
    echo "  kept the existing upsmon password (not shown)"
fi
render "${SRC_DIR}/upsd.users.template" "${NUT_DIR}/upsd.users"
render "${SRC_DIR}/upsmon.conf" "${NUT_DIR}/upsmon.conf"

echo "== ntfy settings"
NTFY_TOKEN=""
if [[ -r "$REPO_ENV" ]]; then
    NTFY_TOKEN=$(awk -F= '/^NTFY_PUBLISH_TOKEN=/ {sub(/^[^=]*=/, ""); gsub(/^["'\'']|["'\'']$/, ""); print; exit}' "$REPO_ENV")
fi
[[ -n "$NTFY_TOKEN" ]] || echo "  WARNING: NTFY_PUBLISH_TOKEN not found in ${REPO_ENV}; pushes will be skipped (syslog only)"
CACERT_LINE=""
if [[ -r "$ORIGIN_CERT" ]]; then
    install -o root -g root -m 644 "$ORIGIN_CERT" "${NUT_DIR}/ntfy-origin.crt"
    CACERT_LINE="${NUT_DIR}/ntfy-origin.crt"
    echo "  ${NUT_DIR}/ntfy-origin.crt (644)"
else
    echo "  WARNING: ${ORIGIN_CERT} missing; pushes use the public URL only"
fi
tmp=$(mktemp)
{
    echo "# written by 83rr-poweredge infrastructure/nut/install.sh; read by upssched-cmd"
    echo "NTFY_URL=${NTFY_URL}"
    echo "NTFY_TOPIC=${NTFY_TOPIC}"
    printf 'NTFY_TOKEN=%q\n' "$NTFY_TOKEN"
    echo "NTFY_CACERT=${CACERT_LINE}"
} > "$tmp"
put_file "$tmp" "${NUT_DIR}/ntfy.env" 640
rm -f "$tmp"
unset NTFY_TOKEN UPSMON_PASSWORD
umask 022

echo "== /run/nut"
if [[ ! -d /run/nut ]]; then
    systemd-tmpfiles --create 2>/dev/null || true
fi
if [[ ! -d /run/nut ]]; then
    install -d -o root -g nut -m 770 /run/nut
fi
echo "  $(stat -c '%U:%G %a' /run/nut)"

echo "== services"
systemctl daemon-reload
systemctl enable nut-driver-enumerator.path nut-driver-enumerator.service \
    nut-server.service nut-monitor.service nut.target nut-driver.target >/dev/null 2>&1 || true
# The enumerator turns ups.conf sections into nut-driver@<name> units.
systemctl restart nut-driver-enumerator.service || echo "  nut-driver-enumerator restart failed (see journalctl -u nut-driver-enumerator)"
systemctl restart nut-driver@cp1500.service 2>/dev/null || echo "  nut-driver@cp1500 did not start (expected while the UPS USB cable is not plugged in)"
systemctl restart nut-server.service || echo "  nut-server restart failed (see journalctl -u nut-server)"
systemctl restart nut-monitor.service || echo "  nut-monitor restart failed (see journalctl -u nut-monitor)"
sleep 3

status
