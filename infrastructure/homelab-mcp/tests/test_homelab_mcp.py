"""Tests for homelab-mcp against a fake Seafile (no network, no Google).

Run from infrastructure/homelab-mcp:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest -q
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
import sys
from pathlib import Path

import httpx2
import pytest

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))

os.environ.setdefault("ALLOWED_EMAILS", "mark@example.com")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "https://mcp.example.com")
os.environ.setdefault("JWT_SIGNING_KEY", "test-signing-key-test-signing-key")
os.environ.setdefault("SEAFILE_REPO_TOKEN", "test-token")
FAKE_KEY = b"-----BEGIN OPENSSH PRIVATE KEY-----\nZmFrZQ==\n-----END OPENSSH PRIVATE KEY-----\n"
os.environ.setdefault("BUS_SSH_TARGET", "mark@192.0.2.10")
os.environ.setdefault("BUS_SSH_KEY_B64", base64.b64encode(FAKE_KEY).decode())
os.environ.setdefault("BUS_SSH_HOST_KEY", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeHostKeyFakeHostKeyFakeHostKey mini")

from seafile import SeafileError, SeafileLibrary, normalize_path  # noqa: E402

TOKEN = "test-token"

FILES = {
    "/README.md": b"# AI Context\nStart here.\n",
    "/03-diary/2026-11-09.md": b"# Nov 9\nWorked on the ARK server.\n",
    "/03-diary/2026-11-10.md": "# Nov 10\nCafé with Christina; ARK fixed.\n".encode(),
    "/05-raw/photo.jpg": b"\xff\xd8\xff\x00\x00binary",
}
DIRS = {"/": ["03-diary", "05-raw"], "/03-diary": [], "/05-raw": []}
MTIMES = {
    "/README.md": "2026-10-25T10:00:00-04:00",
    "/03-diary/2026-11-09.md": "2026-11-09T23:00:00-05:00",
    "/03-diary/2026-11-10.md": "2026-11-10T23:00:00-05:00",
    "/05-raw/photo.jpg": "2026-11-01T08:00:00-04:00",
}


def fake_seafile(perm: str = "r", calls: list | None = None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if calls is not None:
            calls.append((request.method, request.url.path))
        assert request.method == "GET", "connector must only issue GETs"
        if request.headers.get("authorization") != f"Token {TOKEN}":
            return httpx2.Response(401, json={"detail": "bad token"})
        assert request.headers.get("host") == "files.example.com"
        path = request.url.path
        q = dict(request.url.params)
        if path == "/api/v2.1/via-repo-token/repo-info/":
            return httpx2.Response(200, json={"repo_id": "x", "repo_name": "AI Context", "size": 123,
                                              "file_count": len(FILES), "last_modified": "2026-11-10T23:00:00-05:00"})
        if path == "/api/v2.1/via-repo-token/dir/":
            d = q.get("path", "/").rstrip("/") or "/"
            if d not in DIRS:
                return httpx2.Response(404, json={"error_msg": "Folder not found."})
            if q.get("recursive") == "1":
                items = []
                for f, m in MTIMES.items():
                    if f.startswith(d if d.endswith("/") else d + "/"):
                        parent, name = f.rsplit("/", 1)
                        items.append({"type": "file", "name": name, "parent_dir": parent or "/",
                                      "size": len(FILES[f]), "mtime": m})
                for sub in DIRS:
                    if sub != "/" and sub.startswith(d if d.endswith("/") else d + "/"):
                        parent, name = sub.rsplit("/", 1)
                        items.append({"type": "dir", "name": name, "parent_dir": parent or "/", "mtime": ""})
                return httpx2.Response(200, json={"dirent_list": items})
            items = [{"type": "dir", "name": n, "mtime": ""} for n in DIRS[d]]
            prefix = "" if d == "/" else d
            items += [{"type": "file", "name": f.rsplit("/", 1)[1], "size": len(FILES[f]), "mtime": MTIMES[f]}
                      for f in FILES if f.rsplit("/", 1)[0] == prefix]
            return httpx2.Response(200, json={"user_perm": perm, "repo_name": "AI Context", "dirent_list": items})
        if path == "/api/v2.1/via-repo-token/download-link/":
            f = q.get("path")
            if f not in FILES:
                return httpx2.Response(404, json={"error_msg": "File not found"})
            return httpx2.Response(200, content=json.dumps(f"https://files.example.com/seafhttp/files/tok{f}"))
        if path.startswith("/seafhttp/files/tok/"):
            f = path[len("/seafhttp/files/tok"):]
            return httpx2.Response(200, content=FILES[f])
        return httpx2.Response(404)

    return httpx2.MockTransport(handler)


def make_lib(perm="r", calls=None) -> SeafileLibrary:
    return SeafileLibrary(base_url="http://seafile", public_url="https://files.example.com",
                          host_header="files.example.com", token=TOKEN, transport=fake_seafile(perm, calls))


# ── seafile client ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,clean", [("", "/"), ("03-diary/", "/03-diary"), ("/a//b/./c", "/a/b/c")])
def test_normalize_path(raw, clean):
    assert normalize_path(raw) == clean


@pytest.mark.parametrize("bad", ["../etc", "/03-diary/../../x", "a\x00b"])
def test_normalize_path_rejects_traversal(bad):
    with pytest.raises(SeafileError):
        normalize_path(bad)


async def test_read_only_token_accepted():
    lib = make_lib("r")
    assert await lib.check_read_only() == "r"


async def test_read_write_token_refused():
    lib = make_lib("rw")
    with pytest.raises(SeafileError, match="read-only"):
        await lib.check_read_only()


async def test_download_url_rewritten_to_internal_host():
    calls = []
    lib = make_lib(calls=calls)
    data, truncated = await lib.read_bytes("/README.md", 1024)
    assert data.startswith(b"# AI Context") and not truncated
    assert ("GET", "/seafhttp/files/tok/README.md") in calls


async def test_read_truncates():
    lib = make_lib()
    data, truncated = await lib.read_bytes("/README.md", 5)
    assert data == b"# AI " and truncated


async def test_unexpected_download_host_refused():
    lib = make_lib()
    with pytest.raises(SeafileError):
        lib._internal_download_url("https://evil.example.net/steal")


# ── tools ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tools(monkeypatch):
    import server

    monkeypatch.setattr(server, "library", make_lib())
    return server


async def test_list_directory(tools):
    out = await tools.list_directory("/")
    names = {e["name"]: e["type"] for e in out["entries"]}
    assert names == {"03-diary": "dir", "05-raw": "dir", "README.md": "file"}


async def test_find_recent_diary_entries(tools):
    out = await tools.find_files("/03-diary", modified_since="2026-11-10")
    assert [f["path"] for f in out["files"]] == ["/03-diary/2026-11-10.md"]


async def test_find_by_glob_newest_first(tools):
    out = await tools.find_files("/", name_glob="2026-11-*.md")
    assert [f["name"] for f in out["files"]] == ["2026-11-10.md", "2026-11-09.md"]


async def test_read_file_paged(tools):
    first = await tools.read_file("/03-diary/2026-11-10.md", max_chars=1000)
    assert "Café" in first["content"] and first["next_offset"] is None


async def test_read_binary_reported(tools):
    out = await tools.read_file("/05-raw/photo.jpg")
    assert out["binary"] is True and "content" not in out


async def test_search_text(tools):
    out = await tools.search_text("ark")
    assert {m["path"] for m in out["matches"]} == {"/03-diary/2026-11-09.md", "/03-diary/2026-11-10.md"}


async def test_missing_file_is_a_tool_error(tools):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await tools.read_file("/nope.md")


SEAFILE_TOOLS = {"library_info", "list_directory", "find_files", "read_file", "search_text"}
BUS_TOOLS = {"bus_doctor", "bus_spawn", "bus_sessions", "bus_status", "bus_logs", "bus_send", "bus_wait", "bus_stop"}


async def test_registered_tools(tools):
    listed = {t.name: t for t in await tools.mcp.list_tools()}
    assert set(listed) == SEAFILE_TOOLS | BUS_TOOLS  # never bus_config or bus_setup
    for name in SEAFILE_TOOLS | {"bus_sessions", "bus_status", "bus_logs", "bus_wait", "bus_doctor"}:
        assert listed[name].annotations.read_only_hint is True
    for name in ("bus_spawn", "bus_send", "bus_stop"):
        assert listed[name].annotations.destructive_hint is True
    assert "bypassPermissions" not in json.dumps(listed["bus_spawn"].parameters)


# ── auth ───────────────────────────────────────────────────────────────────


async def test_allowlist_rejects_other_accounts(tools, monkeypatch):
    from fastmcp.server.auth.auth import AccessToken
    from fastmcp.server.auth.providers.google import GoogleProvider

    auth = tools.mcp.auth
    claims = {}

    async def fake_super(self, token):
        return AccessToken(token=token, client_id="c", scopes=[], claims=dict(claims))

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_super)

    claims.update(email="Mark@Example.com", email_verified="true")
    assert await auth.load_access_token("t") is not None
    claims.update(email="someone@else.com")
    assert await auth.load_access_token("t") is None
    claims.update(email="mark@example.com", email_verified=False)
    assert await auth.load_access_token("t") is None


def test_empty_allowlist_refuses_to_start(tools):
    with pytest.raises(ValueError):
        tools.AllowlistGoogleProvider(
            allowed_emails=frozenset(), client_id="x", client_secret="y",
            base_url="https://mcp.example.com", jwt_signing_key="k" * 32,
        )


async def test_mcp_endpoint_requires_auth(tools):
    app = tools.mcp.http_app(path="/mcp")
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="https://mcp.example.com") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 401
        assert "resource_metadata" in r.headers.get("www-authenticate", "")
        meta = await c.get("/.well-known/oauth-authorization-server")
        assert meta.status_code == 200
        assert meta.json()["registration_endpoint"] == "https://mcp.example.com/register"


# ── session bus over ssh ───────────────────────────────────────────────────

FAKE_SSH = """#!/bin/sh
# records argv and stdin, answers like bus-gateway
printf '%s\\n' "$@" > "$FAKE_SSH_DIR/argv"
cat > "$FAKE_SSH_DIR/stdin"
cat "$FAKE_SSH_DIR/reply"
"""


@pytest.fixture
def ssh(tools, monkeypatch, tmp_path):
    import bus

    script = tmp_path / "ssh"
    script.write_text(FAKE_SSH)
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_SSH_DIR", str(tmp_path))
    mini = bus.MiniBus(target="mark@192.0.2.10", private_key_b64=os.environ["BUS_SSH_KEY_B64"],
                       host_key=os.environ["BUS_SSH_HOST_KEY"], ssh_bin=str(script), workdir=str(tmp_path / "k"))
    monkeypatch.setattr(tools, "mini_bus", mini)
    # the fake only sees PATH and HOME, so give it the dir through argv instead
    real = mini.command
    monkeypatch.setattr(mini, "command", lambda: ["/usr/bin/env", f"FAKE_SSH_DIR={tmp_path}"] + real())

    def reply(obj):
        (tmp_path / "reply").write_text(json.dumps(obj) + "\n")

    def sent():
        return json.loads((tmp_path / "stdin").read_text())

    reply({"ok": True, "result": {"session_bus": []}})
    return type("S", (), {"reply": staticmethod(reply), "sent": staticmethod(sent), "dir": tmp_path, "mini": mini})


async def test_bus_call_sends_one_request_and_pins_host(ssh, tools):
    out = await tools.bus_sessions()
    assert out == {"session_bus": []}
    assert ssh.sent() == {"tool": "bus_sessions", "args": {"all": False, "limit": 30}, "caller": ""}
    argv = (ssh.dir / "argv").read_text().split("\n")
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv and argv[-2] == "mark@192.0.2.10"
    assert (ssh.mini.known_hosts.read_text().split()[0]) == "192.0.2.10"
    assert stat.S_IMODE(ssh.mini.key_path.stat().st_mode) == 0o600


async def test_spawn_drops_unset_args(ssh, tools):
    ssh.reply({"ok": True, "result": {"name": "x", "state": "running"}})
    await tools.bus_spawn(task="Check ARK", name="ark-check", repo="83rr-poweredge")
    assert ssh.sent()["args"] == {"task": "Check ARK", "name": "ark-check", "repo": "83rr-poweredge",
                                  "parent": "claude.ai"}


async def test_spawn_schema_requires_name_and_has_no_clone(tools):
    listed = {t.name: t for t in await tools.mcp.list_tools()}
    params = listed["bus_spawn"].parameters
    assert "name" in params["required"] and "task" in params["required"]
    assert "clone_if_missing" not in params["properties"]


async def test_gateway_refusal_is_a_tool_error(ssh, tools):
    from fastmcp.exceptions import ToolError

    ssh.reply({"ok": False, "error": "3 sessions are already running"})
    with pytest.raises(ToolError, match="already running"):
        await tools.bus_spawn(task="x", name="x", repo="83rr-poweredge")


async def test_unreachable_mini_is_explained(ssh, tools):
    from fastmcp.exceptions import ToolError

    (ssh.dir / "reply").write_text("")
    with pytest.raises(ToolError, match="Couldn't reach the Mac mini"):
        await tools.bus_status("x")


SLOW_SSH = """#!/bin/sh
echo $$ > "$1"
exec sleep 30
"""


@pytest.fixture
def slow_mini(tmp_path):
    import bus

    script = tmp_path / "ssh"
    script.write_text(SLOW_SSH)
    script.chmod(0o755)
    pidfile = tmp_path / "pid"
    mini = bus.MiniBus(target="mark@192.0.2.10", private_key_b64=os.environ["BUS_SSH_KEY_B64"],
                       host_key=os.environ["BUS_SSH_HOST_KEY"], ssh_bin=str(script), workdir=str(tmp_path / "k"),
                       timeout=1.0)
    mini.command = lambda: [str(script), str(pidfile)]
    return mini, pidfile


def _gone(pidfile):
    pid = int(pidfile.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_default_timeout_fits_cloudflare():
    import bus
    import inspect

    assert inspect.signature(bus.MiniBus).parameters["timeout"].default < 100


async def test_timeout_kills_ssh(slow_mini):
    import bus

    mini, pidfile = slow_mini
    with pytest.raises(bus.BusError, match="didn't answer"):
        await mini.call("bus_sessions", {})
    assert _gone(pidfile)


async def test_cancel_kills_ssh(slow_mini):
    mini, pidfile = slow_mini
    mini.timeout = 30
    task = asyncio.ensure_future(mini.call("bus_sessions", {}))
    for _ in range(50):
        await asyncio.sleep(0.05)
        if pidfile.exists() and pidfile.read_text().strip():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _gone(pidfile)


@pytest.mark.parametrize("kwargs,match", [
    ({"target": "mini"}, "user@"),
    ({"target": "a@b; rm -rf /"}, "user@"),
    ({"host_key": "not a key"}, "host key"),
    ({"private_key_b64": "%%%"}, "base64"),
    ({"private_key_b64": base64.b64encode(b"hello").decode()}, "private key"),
])
def test_bus_config_validation(tmp_path, kwargs, match):
    import bus

    base = dict(target="mark@192.0.2.10", private_key_b64=os.environ["BUS_SSH_KEY_B64"],
                host_key=os.environ["BUS_SSH_HOST_KEY"], workdir=str(tmp_path))
    with pytest.raises(ValueError, match=match):
        bus.MiniBus(**{**base, **kwargs})


# ── deploy helpers ─────────────────────────────────────────────────────────

ENV_SET = Path(__file__).resolve().parent.parent / "scripts" / "env_set.py"


def run_env_set(tmp_path, stdin, *args):
    import subprocess

    return subprocess.run([sys.executable, "-I", str(ENV_SET), "--file", str(tmp_path / ".env"), *args],
                          input=stdin, capture_output=True, text=True)


def test_env_set_replaces_appends_and_never_prints_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nHOMELAB_MCP_X=old\n# c\nHOMELAB_MCP_X=dup\n")
    env_file.chmod(0o600)
    r = run_env_set(tmp_path, "HOMELAB_MCP_X=s3cret-value\nHOMELAB_MCP_KEY=ssh-ed25519 AAAAC3\n")
    assert r.returncode == 0, r.stderr
    assert "s3cret" not in r.stdout + r.stderr and "AAAAC3" not in r.stdout
    assert env_file.read_text() == "A=1\nHOMELAB_MCP_X=s3cret-value\n# c\nHOMELAB_MCP_KEY='ssh-ed25519 AAAAC3'\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    (backup,) = tmp_path.glob(".env.bak-*")
    assert "old" in backup.read_text() and stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_env_set_if_missing_keeps_existing(tmp_path):
    (tmp_path / ".env").write_text("K=keep\nE=\n")
    r = run_env_set(tmp_path, "K=new\nE=filled\n", "--if-missing")
    assert r.returncode == 0 and (tmp_path / ".env").read_text() == "K=keep\nE=filled\n"
    assert "K: kept" in r.stdout


@pytest.mark.parametrize("stdin", ["lower=x\n", "K=\n", "K=it's\n", "nonsense\n", ""])
def test_env_set_refuses_bad_input(tmp_path, stdin):
    (tmp_path / ".env").write_text("A=1\n")
    r = run_env_set(tmp_path, stdin)
    assert r.returncode == 2 and (tmp_path / ".env").read_text() == "A=1\n"
    assert not list(tmp_path.glob(".env.bak-*"))
