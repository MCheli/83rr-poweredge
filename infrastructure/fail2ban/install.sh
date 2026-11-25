#!/bin/bash
# install.sh — install/refresh the fail2ban jail for the public tallied-db
# port (postgresql-tallied) on 83rr-poweredge. Idempotent: safe to run again
# after any change in infrastructure/fail2ban/. See README.md here.
#
# Usage (on the server, from the repo checkout):
#   sudo infrastructure/fail2ban/install.sh           # install + reload fail2ban
#   sudo infrastructure/fail2ban/install.sh --check   # status only, changes nothing
#
# What it does:
#   - /var/log/pg-auth (root 750) and an empty tallied-db.log, so the jail
#     starts before Fluent Bit has written anything
#   - filter.d/postgresql-tallied.conf, jail.d/postgresql-tallied.local,
#     fail2ban.d/83rr.local -> /etc/fail2ban (root 644)
#   - fail2ban.service.d/after-docker.conf -> /etc/systemd/system (start after docker)
#   - logrotate-pg-auth -> /etc/logrotate.d/pg-auth
#   - sudoers-fail2ban-status -> /etc/sudoers.d/fail2ban-status (440), only
#     after visudo -cf accepts it
#   - checks the config with fail2ban-client -t, then restarts fail2ban
#     (a restart, not a reload: fail2ban.d settings are read at start; bans
#     are restored from its database)
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAIL=postgresql-tallied
LOG_DIR=/var/log/pg-auth

CHECK_ONLY=false
case "${1:-}" in
    "") ;;
    --check) CHECK_ONLY=true ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (use --check or nothing)" >&2; exit 2 ;;
esac

status() {
    echo "== fail2ban status"
    printf '  %-28s %s\n' "fail2ban.service" "$(systemctl is-active fail2ban 2>/dev/null || true)"
    printf '  %-28s %s\n' "${LOG_DIR}/tallied-db.log" "$(stat -c '%s bytes, %y' "${LOG_DIR}/tallied-db.log" 2>/dev/null || echo missing)"
    if [[ $EUID -eq 0 ]]; then
        fail2ban-client status "$JAIL" 2>&1 | sed 's/^/  /' || true
        echo "  DOCKER-USER:"
        iptables -S DOCKER-USER 2>&1 | sed 's/^/    /' || true
        iptables -S "f2b-${JAIL}" 2>/dev/null | sed 's/^/    /' || true
    else
        echo "  (run with sudo for jail status and the DOCKER-USER rules)"
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

command -v fail2ban-client >/dev/null || { echo "fail2ban is not installed" >&2; exit 1; }

# put_file SRC DEST MODE: install root:root, atomically
put_file() {
    local src="$1" dest="$2" mode="$3" tmp
    install -d -o root -g root -m 755 "$(dirname "$dest")"
    tmp=$(mktemp "${dest}.XXXXXX")
    cat "$src" > "$tmp"
    chown root:root "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dest"
    echo "  ${dest} (${mode})"
}

echo "== log directory"
install -d -o root -g root -m 750 "$LOG_DIR"
[[ -e "${LOG_DIR}/tallied-db.log" ]] || install -o root -g root -m 640 /dev/null "${LOG_DIR}/tallied-db.log"
echo "  ${LOG_DIR} ($(stat -c '%U:%G %a' "$LOG_DIR"))"

echo "== config"
put_file "${SRC_DIR}/filter.d/${JAIL}.conf" "/etc/fail2ban/filter.d/${JAIL}.conf" 644
put_file "${SRC_DIR}/jail.d/${JAIL}.local" "/etc/fail2ban/jail.d/${JAIL}.local" 644
put_file "${SRC_DIR}/fail2ban.d/83rr.local" /etc/fail2ban/fail2ban.d/83rr.local 644
put_file "${SRC_DIR}/fail2ban.service.d/after-docker.conf" /etc/systemd/system/fail2ban.service.d/after-docker.conf 644
put_file "${SRC_DIR}/logrotate-pg-auth" /etc/logrotate.d/pg-auth 644

echo "== sudoers"
if visudo -cf "${SRC_DIR}/sudoers-fail2ban-status" >/dev/null; then
    put_file "${SRC_DIR}/sudoers-fail2ban-status" /etc/sudoers.d/fail2ban-status 440
    visudo -c >/dev/null && echo "  visudo -c: ok"
else
    echo "  sudoers-fail2ban-status failed visudo -cf; not installed" >&2
fi

echo "== checks"
logrotate --debug /etc/logrotate.d/pg-auth >/dev/null 2>&1 && echo "  logrotate --debug: ok" || echo "  logrotate --debug: FAILED" >&2
fail2ban-client -t >/dev/null && echo "  fail2ban-client -t: ok"

echo "== restart"
systemctl daemon-reload
systemctl restart fail2ban
for _ in 1 2 3 4 5 6 7 8 9 10; do
    fail2ban-client ping >/dev/null 2>&1 && break
    sleep 1
done

status
