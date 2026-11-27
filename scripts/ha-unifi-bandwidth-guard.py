#!/usr/bin/env python3
"""
ha-unifi-bandwidth-guard.py - keep Home Assistant's UniFi bandwidth sensors to an allowlist.

Runs on the R630 from cron (every 10 minutes) against the Home Assistant
Yellow over the LAN websocket API.

Why: the UniFi integration's "bandwidth sensors" option (allow_bandwidth_sensors)
makes an RX and a TX sensor for EVERY client, wired or wireless, and the ones
for clients that show up later arrive enabled, so the recorder would slowly
fill with per-client rates nobody looks at. Mark wants rates for a few devices
only (R630, gaming PC, Mac mini, Quest 3, NAS). This job disables (disabled_by
"user") every enabled UniFi client RX/TX sensor (unique_id rx-<mac> / tx-<mac>)
whose MAC is not on the allowlist. It never enables anything, never touches
port RX/TX sensors (port_rx-/port_tx-, created disabled), trackers or any other
entity, and never changes integration options.

Usage:
  scripts/ha-unifi-bandwidth-guard.py --dry-run   # list what it would disable
  scripts/ha-unifi-bandwidth-guard.py             # what cron runs

Needs in .env (read, never sourced): HA_AUTO_UPDATE_TOKEN (the long-lived
token ha-auto-update.py already uses, 1Password Agents "HA agent token").
Optional: HA_URL (default http://192.168.1.121:8123), HA_BANDWIDTH_ALLOW
(comma-separated MACs, replaces the built-in allowlist). Stdlib only, no sudo.
Every run that disables something appends to logs/ha-unifi-bandwidth-guard.log
(entity ids and counts, no secrets); quiet runs log nothing.

Cron (mcheli's crontab):
  */10 * * * * /home/mcheli/83rr-poweredge/scripts/cron-notify.sh ha-unifi-bandwidth-guard /home/mcheli/83rr-poweredge/scripts/ha-unifi-bandwidth-guard.py >/dev/null 2>&1
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import re
import socket
import struct
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = Path(os.environ.get("ENV_FILE", PROJECT_DIR / ".env"))
LOG_FILE = Path(os.environ.get("LOG_FILE", PROJECT_DIR / "logs" / "ha-unifi-bandwidth-guard.log"))
LOCK_FILE = Path(os.environ.get("LOCK_FILE", "/tmp/ha-unifi-bandwidth-guard.lock"))
DEFAULT_HA_URL = "http://192.168.1.121:8123"
LOCAL_TZ = ZoneInfo("America/New_York")

# Clients that keep their RX/TX sensors (set up 2026-11-27, session af-unifi-build).
DEFAULT_ALLOW = {
    "ec:f4:bb:e6:f7:f4",  # 83rr-poweredge (R630)
    "bc:fc:e7:3c:4d:ce",  # DESKTOP-G2025 (gaming PC)
    "c8:80:6d:39:cf:d1",  # Marks-Mac-Mini (wired)
    "f2:b1:04:d3:3f:0a",  # Meta Quest 3
    "90:09:d0:0c:f4:e6",  # MarksNAS
}
CLIENT_BW_UID = re.compile(r"^(rx|tx)-([0-9a-f]{2}(?::[0-9a-f]{2}){5})$")


def log(msg: str, to_file: bool = False) -> None:
    line = f"[{datetime.now(LOCAL_TZ):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    if to_file:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as fh:
            fh.write(line + "\n")


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


def parse_allow(raw: str | None) -> set[str]:
    if not raw:
        return set(DEFAULT_ALLOW)
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def to_disable(entities: list[dict], unifi_entry_ids: set[str], allow: set[str]) -> list[dict]:
    """Enabled UniFi client RX/TX sensors whose MAC is not allowlisted."""
    out = []
    for e in entities:
        if e.get("platform") != "unifi" or e.get("config_entry_id") not in unifi_entry_ids:
            continue
        if not e.get("entity_id", "").startswith("sensor.") or e.get("disabled_by") is not None:
            continue
        m = CLIENT_BW_UID.match((e.get("unique_id") or "").lower())
        if m and m.group(2) not in allow:
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# Minimal websocket client (RFC 6455, text frames, client-side masking)
# ---------------------------------------------------------------------------

def encode_frame(payload: bytes, opcode: int = 0x1, mask: bytes | None = None) -> bytes:
    mask = mask if mask is not None else os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack("!Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WS:
    def __init__(self, base: str, token: str, timeout: float = 60):
        u = urllib.parse.urlparse(base)
        if u.scheme != "http":
            raise SystemExit("HA_URL must be http:// on the LAN")
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /api/websocket HTTP/1.1\r\nHost: {u.hostname}:{u.port or 80}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake: connection closed")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("websocket handshake refused: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.next_id = 1
        hello = self.recv()
        if hello.get("type") != "auth_required":
            raise ConnectionError(f"unexpected hello {hello.get('type')}")
        self.send({"type": "auth", "access_token": token})
        auth = self.recv()
        if auth.get("type") != "auth_ok":
            raise ConnectionError(f"auth failed ({auth.get('type')})")

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, obj: dict) -> None:
        self.sock.sendall(encode_frame(json.dumps(obj).encode()))

    def recv(self) -> dict:
        msg = b""
        while True:
            b0, b1 = self._read(2)
            opcode, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x9:                       # ping -> pong
                self.sock.sendall(encode_frame(data, opcode=0xA))
                continue
            if opcode == 0x8:
                raise ConnectionError("websocket closed by server")
            if opcode in (0x0, 0x1, 0x2):
                msg += data
                if b0 & 0x80:
                    return json.loads(msg)

    def call(self, msg: dict):
        i = self.next_id
        self.next_id += 1
        self.send(dict(msg, id=i))
        while True:
            r = self.recv()
            if r.get("id") == i and r.get("type") == "result":
                if not r.get("success"):
                    raise RuntimeError(f"{msg['type']} failed: {r.get('error')}")
                return r.get("result")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def run(args) -> int:
    env = load_env(ENV_FILE)
    token = os.environ.get("HA_AUTO_UPDATE_TOKEN") or env.get("HA_AUTO_UPDATE_TOKEN", "")
    if not token:
        log("HA_AUTO_UPDATE_TOKEN not set in .env; nothing done", to_file=True)
        return 2
    allow = parse_allow(os.environ.get("HA_BANDWIDTH_ALLOW") or env.get("HA_BANDWIDTH_ALLOW"))
    ws = WS(os.environ.get("HA_URL") or env.get("HA_URL") or DEFAULT_HA_URL, token)
    try:
        entries = ws.call({"type": "config_entries/get", "domain": "unifi"})
        entry_ids = {e["entry_id"] for e in entries}
        entities = ws.call({"type": "config/entity_registry/list"})
        victims = to_disable(entities, entry_ids, allow)
        if args.dry_run:
            for e in victims:
                log(f"would disable {e['entity_id']} ({e['unique_id']})")
            log(f"dry run: {len(victims)} sensor(s) to disable; allowlist {len(allow)} MACs")
            return 0
        done = []
        for e in victims:
            ws.call({"type": "config/entity_registry/update", "entity_id": e["entity_id"], "disabled_by": "user"})
            done.append(e["entity_id"])
        if done:
            log(f"disabled {len(done)} non-allowlisted UniFi client RX/TX sensor(s): {', '.join(done)}", to_file=True)
        return 0
    finally:
        ws.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="list what would be disabled, change nothing")
    args = p.parse_args(argv)
    with open(LOCK_FILE, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            return run(args)
        except (OSError, ConnectionError, RuntimeError, ValueError) as e:
            log(f"failed: {type(e).__name__}: {e}", to_file=True)
            return 1


if __name__ == "__main__":
    sys.exit(main())
