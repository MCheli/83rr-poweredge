"""Reach the session bus on Mark's Mac mini over the LAN, by ssh.

The mini runs bus-gateway (in the private mac-mini-collector repo). This
server's dedicated key is pinned there in authorized_keys with
`from="<this server's LAN IP>",restrict,command="... relay.py"`, so the only
thing an ssh connection with it can do is hand one JSON request to the
gateway, which checks it again on the mini (allowed tools, no bypass
permissions, ~/repos only, at most 3 sessions running, kill switch).

The mini's host key is pinned too (StrictHostKeyChecking=yes against a
known_hosts file written from BUS_SSH_HOST_KEY), so a spoofed host on the LAN
can't receive the requests. The private key comes from the environment
(base64) and is written to the container's tmpfs with mode 0600.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import tempfile
from pathlib import Path

TARGET_RE = re.compile(r"^[a-z_][a-z0-9_.-]{0,31}@[A-Za-z0-9.-]{1,253}$")
HOST_KEY_RE = re.compile(r"^(ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|ssh-rsa) [A-Za-z0-9+/=]+$")


class BusError(Exception):
    """The Mac mini couldn't be reached, or its gateway refused the request."""


class MiniBus:
    def __init__(self, *, target: str, private_key_b64: str, host_key: str, port: int = 22,
                 timeout: float = 420.0, ssh_bin: str = "ssh", workdir: str | None = None):
        if not TARGET_RE.match(target):
            raise ValueError("BUS_SSH_TARGET must look like user@192.168.1.20")
        host_key = " ".join(host_key.split()[:2])  # drop a trailing comment
        if not HOST_KEY_RE.match(host_key):
            raise ValueError("BUS_SSH_HOST_KEY must be the mini's public host key, e.g. 'ssh-ed25519 AAAA...'")
        try:
            key = base64.b64decode(private_key_b64.strip(), validate=True)
        except ValueError as e:
            raise ValueError("BUS_SSH_KEY_B64 isn't valid base64") from e
        if b"PRIVATE KEY" not in key:
            raise ValueError("BUS_SSH_KEY_B64 doesn't decode to an ssh private key")
        self.target = target
        self.port = int(port)
        self.timeout = timeout
        self.ssh_bin = ssh_bin
        d = Path(workdir or tempfile.mkdtemp(prefix="bus-ssh-", dir="/tmp"))
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        d.chmod(0o700)
        self.key_path = d / "id"
        self.known_hosts = d / "known_hosts"
        fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key if key.endswith(b"\n") else key + b"\n")
        host = target.split("@", 1)[1]
        entry = host if self.port == 22 else f"[{host}]:{self.port}"
        self.known_hosts.write_text(f"{entry} {host_key}\n")

    def command(self) -> list[str]:
        return [
            self.ssh_bin, "-T", "-p", str(self.port), "-i", str(self.key_path),
            "-F", "/dev/null",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-o", "GlobalKnownHostsFile=/dev/null", "-o", "UpdateHostKeys=no",
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30", "-o", "LogLevel=ERROR",
            "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-o", "ClearAllForwardings=yes",
            self.target,
        ]

    async def call(self, tool: str, args: dict, caller: str = ""):
        """Send one request; return the gateway's result or raise BusError with its message."""
        req = json.dumps({"tool": tool, "args": args, "caller": caller}) + "\n"
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
            )
        except FileNotFoundError as e:
            raise BusError("ssh isn't installed in this container") from e
        try:
            out, err = await asyncio.wait_for(proc.communicate(req.encode()), self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise BusError(f"The Mac mini didn't answer within {int(self.timeout)} s.")
        line = out.decode(errors="replace").strip().splitlines()[-1:] if out else []
        if not line:
            hint = err.decode(errors="replace").strip().splitlines()[-1:] or [f"ssh exit {proc.returncode}"]
            raise BusError(f"Couldn't reach the Mac mini over the LAN ({hint[0][:200]}). It may be asleep, "
                           "logged out, or Remote Login may be off.")
        try:
            resp = json.loads(line[0])
        except ValueError as e:
            raise BusError("The Mac mini sent an answer that isn't JSON.") from e
        if not resp.get("ok"):
            raise BusError(resp.get("error") or "The Mac mini's gateway refused the request.")
        return resp.get("result")
