#!/usr/bin/env python3
"""
ha-auto-update.py - keep Home Assistant's own updates installed, unattended.

Runs on the R630 from cron (daily, 04:15 America/New_York) against the Home
Assistant Yellow (HA OS + Supervisor) over the LAN REST API.

Scope: only update.* entities of the `hassio` integration (Supervisor, Core,
Operating System, add-ons) and of `hacs` (HACS integrations/cards). Device
firmware (UniFi, ZHA, ESPHome, Matter, Synology DSM, the Yellow's own radio
and board firmware, anything else) is never touched.

Policy:
  - soak: install a version only after the same latest_version has been
    offered for --soak-days (3) days. First-seen times live in a small state
    file; for a version the state file hasn't seen yet, HA's own history (up
    to --history-days back) supplies when it first appeared;
  - Core X.Y.0 releases are never installed (wait for X.Y.1+);
  - a version Mark skipped in the UI (skipped_version) is never installed;
  - nothing is installed while any in-scope update is in progress (someone
    may be updating by hand); one in progress with no change for
    --stuck-hours (6) gets one alert.

Order: Supervisor, add-ons, HACS, Core, OS, one at a time. Before Core or OS
a backup is made with backup.create_automatic (Mark's automatic-backup
settings: locations, encryption, retention) and the run waits for it to
finish. update.install gets backup: true where the entity supports it, and
version: <the soaked version> where it supports picking one.

After each install, and at the end: /api/ answers, /api/config state is
RUNNING, installed_version is the target, and the number of unavailable
entities is not more than 25 (or 10%) above the pre-run count (waits up to
--settle-minutes for entities to come back after a restart). The first
failure stops the run, sends a high-priority ntfy push (topic homelab) and
files a Tasks agent item (personal list, source ha-auto-update). Supervisor
rolls back a Core update that fails to start on its own; this script never
restores backups.

Success with installs: one low-priority push listing the versions. Nothing
installed: silent. Every run appends to logs/ha-auto-update.log (no secrets).

Usage:
  scripts/ha-auto-update.py --dry-run     # print the plan, change nothing
  scripts/ha-auto-update.py               # what cron runs
  scripts/ha-auto-update.py --no-notify   # no ntfy push / Tasks item

Needs in .env (read, never sourced): HA_AUTO_UPDATE_TOKEN (long-lived token,
1Password Agents "HA agent token"), NTFY_PUBLISH_TOKEN, and
HA_AUTO_UPDATE_TASKS_API_KEY (1Password Agents "Tasks API key"). Optional:
HA_URL (default http://192.168.1.121:8123, the Yellow on the LAN, so restarts
don't go through nginx/Cloudflare). No sudo.

Cron (mcheli's crontab; the server runs on UTC, so it fires at 08:15 and
09:15 UTC and --at-hour 4 keeps only the one that is 04:xx in New York):
  15 8,9 * * * /home/mcheli/83rr-poweredge/scripts/ha-auto-update.py --at-hour 4 >/dev/null 2>&1
"""

from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = Path(os.environ.get("ENV_FILE", PROJECT_DIR / ".env"))
LOG_FILE = Path(os.environ.get("LOG_FILE", PROJECT_DIR / "logs" / "ha-auto-update.log"))
STATE_DIR = Path(os.environ.get("STATE_DIR", Path.home() / ".cache" / "ha-auto-update"))
DEFAULT_HA_URL = "http://192.168.1.121:8123"
LOCAL_TZ = ZoneInfo("America/New_York")
NTFY_TOPIC = "homelab"
NTFY_PUBLIC = "https://ntfy.markcheli.com/"
TASKS_PUBLIC = "https://tasks.markcheli.com"
USER_AGENT = "ha-auto-update/1.0"
SOURCE = "ha-auto-update"

PLATFORMS = ("hassio", "hacs")
KIND_ORDER = {"supervisor": 0, "addon": 1, "hacs": 2, "core": 3, "os": 4}
# UpdateEntityFeature bits
FEAT_INSTALL, FEAT_SPECIFIC_VERSION, FEAT_BACKUP = 1, 2, 8

INSTALL_TIMEOUT = 20 * 60      # in_progress must clear / API must come back within this
BACKUP_TIMEOUT = 30 * 60
POLL = 15
UNAVAIL_ABS, UNAVAIL_PCT = 25, 0.10


class Failure(Exception):
    """A check failed: stop the run and alert."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


_log_fh = None


def log(msg: str) -> None:
    line = f"[{datetime.now(LOCAL_TZ):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def env_get(env: dict, key: str) -> str:
    return os.environ.get(key) or env.get(key, "")


def load_env(path: Path) -> dict:
    """KEY=value lines of .env, without sourcing it (values may hold shell metachars)."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def container_ip(name: str) -> str | None:
    """IP of a container on the compose "infrastructure" network (host -> bridge)."""
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f",
             '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\\n"}}{{end}}', name],
            capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.search(r"(^|_)infrastructure$", parts[0]):
            return parts[1]
    return None


# ---------------------------------------------------------------------------
# Home Assistant REST client
# ---------------------------------------------------------------------------

# Errors that mean "HA is restarting / not answering", not "the request was refused".
TRANSIENT = (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
             http.client.RemoteDisconnected, http.client.IncompleteRead)


class HA:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        self._token = token

    def request(self, method: str, path: str, body=None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._token)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None

    def get(self, path: str):
        return self.request("GET", path)

    def template(self, tpl: str):
        """Render a template that ends in `| tojson`."""
        return self.request("POST", "/api/template", {"template": tpl})

    def service(self, domain: str, service: str, data: dict, timeout: float = 60):
        return self.request("POST", f"/api/services/{domain}/{service}", data, timeout=timeout)

    def states(self) -> list[dict]:
        return self.get("/api/states")

    def state(self, entity_id: str) -> dict | None:
        try:
            return self.get(f"/api/states/{entity_id}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def platform_entities(self, platform: str) -> set[str]:
        return set(self.template(
            "{{ integration_entities('%s') | select('search', '^update[.]') | list | tojson }}" % platform))

    def history(self, entity_id: str, start: datetime) -> list[dict]:
        q = urllib.parse.urlencode({"filter_entity_id": entity_id, "significant_changes_only": "0"})
        rows = self.get(f"/api/history/period/{urllib.parse.quote(iso(start))}?{q}")
        return rows[0] if rows else []

    def healthy(self) -> tuple[bool, str]:
        """(ok, why): /api/ answers and /api/config state is RUNNING."""
        try:
            msg = (self.get("/api/") or {}).get("message", "")
            if msg != "API running.":
                return False, f"/api/ answered {msg!r}"
            st = (self.get("/api/config") or {}).get("state")
            if st != "RUNNING":
                return False, f"HA state is {st}"
            return True, "RUNNING"
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}"
        except TRANSIENT as e:
            return False, f"not answering ({type(e).__name__})"


# ---------------------------------------------------------------------------
# Planning (pure; unit-tested in scripts/test_ha_auto_update.py)
# ---------------------------------------------------------------------------

def classify(entity_id: str, title: str | None, platform: str) -> str:
    if platform == "hacs":
        return "hacs"
    t = (title or "").strip().lower()
    if t == "home assistant supervisor" or entity_id == "update.home_assistant_supervisor_update":
        return "supervisor"
    if t == "home assistant core" or entity_id == "update.home_assistant_core_update":
        return "core"
    if t == "home assistant operating system" or entity_id == "update.home_assistant_operating_system_update":
        return "os"
    return "addon"


def is_core_x0(version: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.0", version or ""))


def candidates(states: list[dict], platform_sets: dict[str, set[str]]) -> list[dict]:
    """In-scope update entities, in install order."""
    out = []
    for s in states:
        eid = s["entity_id"]
        if not eid.startswith("update."):
            continue
        platform = next((p for p in PLATFORMS if eid in platform_sets.get(p, ())), None)
        if not platform:
            continue
        a = s.get("attributes", {})
        out.append({
            "entity_id": eid,
            "platform": platform,
            "kind": classify(eid, a.get("title"), platform),
            "title": a.get("title") or a.get("friendly_name") or eid,
            "state": s.get("state"),
            "installed": a.get("installed_version"),
            "latest": a.get("latest_version"),
            "skipped": a.get("skipped_version"),
            "in_progress": bool(a.get("in_progress")),
            "features": int(a.get("supported_features") or 0),
            "last_updated": s.get("last_updated"),
        })
    out.sort(key=lambda c: (KIND_ORDER[c["kind"]], c["title"].lower()))
    return out


def first_seen_from_history(rows: list[dict], version: str) -> str | None:
    """Start of the latest unbroken run of rows offering `version` (None: not offered)."""
    start = None
    for r in rows:
        if (r.get("attributes") or {}).get("latest_version") == version:
            if start is None:
                start = r.get("last_updated") or r.get("last_changed")
        else:
            start = None
    return start


def decide(c: dict, first_seen: str | None, now: datetime, soak_days: float) -> tuple[str, str]:
    """("install"|"wait"|"hold"|"none", reason) for one candidate."""
    if c["state"] == "unavailable" or not c["latest"] or not c["installed"]:
        return "none", f"state {c['state']}"
    if c["latest"] == c["installed"]:
        return "none", "up to date"
    if c["skipped"] and c["skipped"] == c["latest"]:  # HA shows a skipped version as state "off"
        return "hold", f"{c['latest']} skipped in the UI"
    if c["state"] != "on":
        return "none", f"state {c['state']}"
    if not c["features"] & FEAT_INSTALL:
        return "hold", "entity can't install"
    if c["kind"] == "core" and is_core_x0(c["latest"]):
        return "hold", f"Core {c['latest']} is an X.Y.0 release (waiting for X.Y.1+)"
    seen = parse_ts(first_seen) if first_seen else now
    due = seen + timedelta(days=soak_days)
    if now < due:
        return "wait", f"soaking: offered since {seen.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M}, eligible from {due.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M}"
    return "install", f"offered since {seen.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M}"


def unavail_limit(baseline: int) -> int:
    """Largest allowed rise in unavailable entities: more than 25 or 10% fails."""
    return min(UNAVAIL_ABS, int(baseline * UNAVAIL_PCT))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class Notifier:
    def __init__(self, env: dict, enabled: bool):
        self.enabled = enabled
        self.ntfy_token = env_get(env, "NTFY_PUBLISH_TOKEN")
        self.tasks_key = env_get(env, "HA_AUTO_UPDATE_TASKS_API_KEY")

    def _post(self, urls: list[str], headers: dict, body: dict) -> str | None:
        data = json.dumps(body).encode()
        for url in urls:
            req = urllib.request.Request(url, data=data, method="POST")
            for k, v in headers.items():
                req.add_header(k, v)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                return raw.decode() or "{}"
            except (urllib.error.HTTPError, *TRANSIENT):
                continue
        return None

    def push(self, title: str, lines: list[str], priority: int, tags: list[str]) -> None:
        if not self.enabled:
            log(f"(not sending push \"{title}\")")
            return
        if not self.ntfy_token:
            log(f"NTFY_PUBLISH_TOKEN not set; cannot send the push \"{title}\"")
            return
        ip = container_ip("ntfy")
        urls = ([f"http://{ip}/"] if ip else []) + [NTFY_PUBLIC]
        if os.environ.get("NTFY_URL"):
            urls = [os.environ["NTFY_URL"]]
        body = {"topic": NTFY_TOPIC, "title": title, "priority": priority, "tags": tags + ["home-assistant"],
                "message": "\n".join(lines) + "\nLog: ~/83rr-poweredge/logs/ha-auto-update.log"}
        ok = self._post(urls, {"Authorization": "Bearer " + self.ntfy_token,
                               "Content-Type": "application/json"}, body)
        log(f"push \"{title}\" sent to ntfy" if ok else f"could not reach ntfy to send the push \"{title}\"")

    def task(self, title: str, notes: str) -> None:
        """Tasks agent item (personal list), unless an open one with this title exists."""
        if not self.enabled:
            log(f"(not filing Tasks item \"{title}\")")
            return
        if not self.tasks_key:
            log(f"HA_AUTO_UPDATE_TASKS_API_KEY not set; cannot file Tasks item \"{title}\"")
            return
        ip = container_ip("tasks")
        bases = ([f"http://{ip}:8000"] if ip else []) + [TASKS_PUBLIC]
        hdr = {"X-API-Key": self.tasks_key, "Accept": "application/json",
               "User-Agent": USER_AGENT, "Content-Type": "application/json"}
        for base in bases:
            q = urllib.parse.urlencode({"category": "personal", "owner": "agent", "q": title[:200], "limit": 200})
            req = urllib.request.Request(f"{base}/api/tasks?{q}")
            for k, v in hdr.items():
                req.add_header(k, v)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    existing = json.loads(resp.read()).get("tasks", [])
            except (urllib.error.HTTPError, *TRANSIENT, ValueError):
                continue
            for t in existing:
                if t["title"].strip().casefold() == title.strip().casefold():
                    log(f"Tasks item #{t.get('display_id')} already open: \"{title}\"")
                    self._post([f"{base}/api/tasks/{t['id']}/notes"], hdr, {"body": notes, "author": SOURCE})
                    return
            body = {"category": "personal", "title": title, "owner": "agent", "source": SOURCE,
                    "agent_status": "open", "notes": notes}
            raw = self._post([f"{base}/api/tasks"], hdr, body)
            if raw:
                log(f"Tasks item filed: \"{title}\"")
                return
        log(f"could not file Tasks item \"{title}\"")


# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------

def wait_until(fn, timeout: float, what: str):
    """Poll fn() every POLL s until it returns a truthy value; Failure on timeout."""
    deadline = time.monotonic() + timeout
    last = None
    while True:
        try:
            res, last = fn()
        except TRANSIENT as e:
            res, last = None, f"HA not answering ({type(e).__name__})"
        except urllib.error.HTTPError as e:
            res, last = None, f"HTTP {e.code}"
        if res:
            return res
        if time.monotonic() > deadline:
            raise Failure(f"{what}: timed out after {int(timeout // 60)} min ({last})")
        time.sleep(POLL)


def make_backup(ha: HA) -> str:
    """backup.create_automatic, then wait for it; returns the finish time."""
    before = ha.state("sensor.backup_last_successful_automatic_backup")
    if before is None or ha.state("sensor.backup_backup_manager_state") is None:
        raise Failure("backup: the backup integration's sensors are missing, so the backup can't be confirmed")
    before_ts = before["state"]
    log(f"backup: creating (backup.create_automatic; last successful {before_ts})")
    started = now_utc()
    try:
        ha.service("backup", "create_automatic", {}, timeout=120)
    except urllib.error.HTTPError as e:
        raise Failure(f"backup: backup.create_automatic refused (HTTP {e.code})")
    except TRANSIENT:
        pass  # the call can outlive the timeout; the sensors tell us how it went

    def done():
        mgr = ha.state("sensor.backup_backup_manager_state") or {}
        last = ha.state("sensor.backup_last_successful_automatic_backup") or {}
        ev = ha.state("event.backup_automatic_backup") or {}
        ev_a = ev.get("attributes", {})
        ev_ts = ev.get("state")
        if (ev_a.get("event_type") == "failed" and ev_ts not in (None, "unknown", "unavailable")
                and parse_ts(ev_ts) >= started - timedelta(seconds=5)):
            raise Failure(f"backup: failed ({ev_a.get('failed_reason') or 'no reason given'})")
        if mgr.get("state") == "idle" and last.get("state") not in (None, before_ts, "unknown", "unavailable"):
            return last["state"], "done"
        return None, f"manager {mgr.get('state')}, last successful {last.get('state')}"

    finished = wait_until(done, BACKUP_TIMEOUT, "backup")
    log(f"backup: done ({finished})")
    return finished


def install(ha: HA, c: dict, target: str) -> None:
    body = {"entity_id": c["entity_id"]}
    if c["features"] & FEAT_BACKUP:
        body["backup"] = True
    if c["features"] & FEAT_SPECIFIC_VERSION:
        body["version"] = target
    opts = ", ".join(k for k in ("backup", "version") if k in body)
    log(f"install: {c['title']} {c['installed']} -> {target} (update.install{' with ' + opts if opts else ''})")
    try:
        ha.service("update", "install", body, timeout=INSTALL_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code not in (502, 503, 504):
            detail = ""
            try:
                detail = json.loads(e.read() or b"{}").get("message", "")[:200]
            except (ValueError, AttributeError):
                pass
            raise Failure(f"{c['title']}: update.install refused (HTTP {e.code}{': ' + detail if detail else ''})")
        log(f"install: call ended with HTTP {e.code} (HA restarting); waiting")
    except TRANSIENT as e:
        log(f"install: connection dropped ({type(e).__name__}, expected when HA or Supervisor restarts); waiting")

    def finished():
        ok, why = ha.healthy()
        if not ok:
            return None, why
        s = ha.state(c["entity_id"])
        if s is None:
            return None, "entity not there (yet)"
        a = s.get("attributes", {})
        if a.get("in_progress"):
            return None, f"in progress ({a.get('update_percentage')}%)"
        if a.get("installed_version") == target:
            return True, "installed"
        return None, f"installed_version {a.get('installed_version')}"

    t0 = time.monotonic()
    wait_until(finished, INSTALL_TIMEOUT, f"{c['title']} {target}")
    log(f"install: {c['title']} is on {target} ({int(time.monotonic() - t0)} s after the call returned)")


def check_health(ha: HA, baseline: int, settle: float, what: str) -> int:
    """API + RUNNING + unavailable count within the limit (waits up to `settle`)."""
    limit = unavail_limit(baseline)

    def ok():
        good, why = ha.healthy()
        if not good:
            return None, why
        n = sum(1 for s in ha.states() if s.get("state") == "unavailable")
        if n - baseline > limit:
            return None, f"{n} unavailable entities (was {baseline}, limit +{limit})"
        return n, "ok"

    try:
        n = wait_until(ok, settle, f"health check after {what}")
    except Failure as e:
        raise Failure(str(e).replace(": timed out after", ": still failing after"))
    log(f"health: ok after {what} (API running, RUNNING, {n} unavailable, was {baseline})")
    return n


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

def load_state(path: Path) -> dict:
    try:
        st = json.loads(path.read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("seen", {})
    st.setdefault("stuck_alerted", {})
    return st


def save_state(path: Path, st: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args) -> int:
    env = load_env(ENV_FILE)
    token = env_get(env, "HA_AUTO_UPDATE_TOKEN")
    notifier = Notifier(env, enabled=args.notify and not args.dry_run)
    if not token:
        log("HA_AUTO_UPDATE_TOKEN not set in .env; nothing done")
        return 1
    ha = HA(env_get(env, "HA_URL") or DEFAULT_HA_URL, token)
    state_file = STATE_DIR / "state.json"
    st = load_state(state_file)
    now = now_utc()

    ok, why = ha.healthy()
    if not ok:
        # Uptime Kuma already alerts on HA being down; just don't update today.
        log(f"HA is not healthy before the run ({why}); nothing done")
        return 1

    states = ha.states()
    platform_sets = {p: ha.platform_entities(p) for p in PLATFORMS}
    cands = candidates(states, platform_sets)
    baseline = sum(1 for s in states if s.get("state") == "unavailable")
    log(f"HA {ha.get('/api/config').get('version')} RUNNING; {len(cands)} in-scope update entities "
        f"({', '.join(f'{p}: {len(platform_sets[p])}' for p in PLATFORMS)}); "
        f"{baseline} of {len(states)} entities unavailable")

    # First-seen bookkeeping: state file, else HA's history, else now.
    seen = {}
    for c in cands:
        if not c["latest"] or c["latest"] == c["installed"]:
            continue
        prev = st["seen"].get(c["entity_id"])
        if prev and prev.get("version") == c["latest"]:
            seen[c["entity_id"]] = prev
            continue
        first = None
        try:
            rows = ha.history(c["entity_id"], now - timedelta(days=args.history_days))
            first = first_seen_from_history(rows, c["latest"])
        except (urllib.error.HTTPError, *TRANSIENT, ValueError):
            pass
        seen[c["entity_id"]] = {"version": c["latest"], "first_seen": first or iso(now),
                                "from": "history" if first else "this run"}

    plan = []
    for c in cands:
        fs = (seen.get(c["entity_id"]) or {}).get("first_seen")
        action, reason = decide(c, fs, now, args.soak_days)
        plan.append((c, action, reason))
        ver = f"{c['installed']} -> {c['latest']}" if c["latest"] != c["installed"] else (c["installed"] or "-")
        busy = " [IN PROGRESS]" if c["in_progress"] else ""
        log(f"  {c['kind']:<10} {c['title']}: {ver}{busy}: {action.upper()} ({reason})")

    if not args.dry_run:
        st["seen"] = seen
        save_state(state_file, st)

    busy = [c for c in cands if c["in_progress"]]
    if busy:
        for c in busy:
            since = parse_ts(c["last_updated"]) if c.get("last_updated") else now
            key = f"{c['entity_id']}@{c['last_updated']}"
            if now - since > timedelta(hours=args.stuck_hours) and key not in st["stuck_alerted"]:
                msg = (f"{c['title']} has shown 'in progress' with no change since "
                       f"{since.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M} ({c['installed']} -> {c['latest']}).")
                log(f"STUCK: {msg}")
                notifier.push(f"Home Assistant update stuck: {c['title']}",
                              [msg, "No updates are installed while it shows in progress. Check Settings > System > Updates."],
                              4, ["hourglass"])
                notifier.task(f"Home Assistant update stuck in progress: {c['title']}", msg)
                if not args.dry_run:
                    st["stuck_alerted"][key] = iso(now)
                    save_state(state_file, st)
        log(f"{', '.join(c['title'] for c in busy)} in progress (someone may be updating by hand); "
            f"nothing installed this run")
        return 0

    todo = [(c, r) for c, a, r in plan if a == "install"]
    if not todo:
        log("nothing to install")
        return 0
    if args.dry_run:
        for c, _ in todo:
            pre = "full backup (backup.create_automatic), then " if c["kind"] in ("core", "os") else ""
            log(f"dry run: would {pre}install {c['title']} {c['latest']}")
        log("dry run: nothing changed")
        return 0

    done_list = []
    backup_at = None
    current = None
    try:
        for c, _ in todo:
            current = c
            target = c["latest"]
            # Re-read: an earlier install (Supervisor, Core) may have changed what's offered.
            s = ha.state(c["entity_id"]) or {}
            a = s.get("attributes", {})
            if a.get("installed_version") == target:
                log(f"skip: {c['title']} is already on {target}")
                continue
            if a.get("latest_version") != target:
                log(f"skip: {c['title']} now offers {a.get('latest_version')} instead of {target}; it soaks again")
                continue
            if c["kind"] in ("core", "os"):
                backup_at = make_backup(ha)
            install(ha, c, target)
            check_health(ha, baseline, args.settle_minutes * 60, f"{c['title']} {target}")
            done_list.append(f"{c['title']}: {c['installed']} -> {target}")
        current = None
        check_health(ha, baseline, args.settle_minutes * 60, "the run")
    except Exception as e:  # Failure, or anything unexpected mid-install: same alert
        if not isinstance(e, Failure):
            e = Failure(f"{type(e).__name__}: {e}")
        comp = current["title"] if current else "final health check"
        bk = (f"A full backup was made before this step ({backup_at})." if backup_at
              else "Add-on updates make their own backup when the add-on supports it."
              if current and current["features"] & FEAT_BACKUP else "No backup was made for this step.")
        log(f"FAILED: {e}")
        lines = [str(e), bk, "Run stopped; nothing was rolled back automatically."]
        if done_list:
            lines.insert(1, "Installed before the failure: " + "; ".join(done_list))
        notifier.push(f"Home Assistant auto-update failed: {comp}", lines, 5, ["warning"])
        notifier.task(f"Home Assistant auto-update failed: {comp}", " ".join(lines))
        return 1

    if done_list:
        log("updated: " + "; ".join(done_list))
        notifier.push(f"Home Assistant: {len(done_list)} update(s) installed", done_list, 2, ["arrow_up"])
    else:
        log("nothing installed")
    return 0


def main(argv=None) -> int:
    global _log_fh
    p = argparse.ArgumentParser(description="Install Home Assistant's own updates after a soak period.")
    p.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    p.add_argument("--no-notify", dest="notify", action="store_false", help="no ntfy push / Tasks item")
    p.add_argument("--soak-days", type=float, default=3)
    p.add_argument("--history-days", type=float, default=10, help="how far back HA history is read for first-seen")
    p.add_argument("--stuck-hours", type=float, default=6)
    p.add_argument("--settle-minutes", type=float, default=10,
                   help="how long entities may stay unavailable after a restart")
    p.add_argument("--at-hour", type=int, help="exit unless it is this hour in America/New_York (cron on UTC)")
    args = p.parse_args(argv)

    if args.at_hour is not None and datetime.now(LOCAL_TZ).hour != args.at_hour:
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another ha-auto-update is running; exiting")
        return 0
    _log_fh = open(LOG_FILE, "a")
    log("==========================================")
    log(f"ha-auto-update starting{' (dry run)' if args.dry_run else ''}")
    try:
        return run(args)
    except Failure as e:
        log(f"FAILED: {e}")
        return 1
    except Exception as e:  # never let a traceback leak request details into cron mail
        log(f"ERROR: {type(e).__name__}: {e}")
        # A job that breaks quietly lets updates pile up again: say so (no install was under way).
        Notifier(load_env(ENV_FILE), enabled=args.notify and not args.dry_run).push(
            "Home Assistant auto-update: script error", [f"{type(e).__name__}: {e}", "Nothing was installed."],
            3, ["warning"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
