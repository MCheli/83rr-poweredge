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
os.environ.setdefault("NOTES_MCP_URL", "http://basic-memory.test:8000/mcp")

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
NOTES_READ_TOOLS = {"notes_search", "notes_read", "notes_list", "notes_find", "notes_context", "notes_recent"}
NOTES_WRITE_TOOLS = {"notes_write", "notes_edit"}  # since the AI Context cut-over (2026-11-23)
NOTES_TOOLS = NOTES_READ_TOOLS | NOTES_WRITE_TOOLS
IMESSAGE_TOOLS = {"imessage_recent", "imessage_search", "imessage_threads", "imessage_unanswered"}
IMESSAGE_SEND_TOOLS = {"imessage_send"}  # since 2026-11-28; limits enforced on the mini


async def test_registered_tools(tools):
    listed = {t.name: t for t in await tools.mcp.list_tools()}
    assert set(listed) == SEAFILE_TOOLS | BUS_TOOLS | NOTES_TOOLS | IMESSAGE_TOOLS | IMESSAGE_SEND_TOOLS  # never bus_config or bus_setup
    for name in SEAFILE_TOOLS | NOTES_READ_TOOLS | IMESSAGE_TOOLS | {"bus_sessions", "bus_status", "bus_logs",
                                                                       "bus_wait", "bus_doctor"}:
        assert listed[name].annotations.read_only_hint is True
    for name in ("bus_spawn", "bus_send", "bus_stop", "notes_write", "notes_edit", "imessage_send"):  # the acting tools
        assert listed[name].annotations.read_only_hint is False
        assert listed[name].annotations.destructive_hint is True
    assert "bypassPermissions" not in json.dumps(listed["bus_spawn"].parameters)
    for name in listed:  # only the notes can be written, and nothing is ever deleted or moved
        assert not any(w in name for w in ("delete", "move", "create", "bm_"))
        assert ("write" in name or "edit" in name) == (name in NOTES_WRITE_TOOLS)
    for name in NOTES_TOOLS:  # callers never pick the project
        assert not {"project", "projects", "all_projects"} & set(listed[name].parameters["properties"])
    for name in ("bus_spawn", "notes_write", "notes_edit"):
        assert "Seafile" not in (listed[name].description or "") or "backup" in listed[name].description
    assert "can't be written" not in (tools.mcp.instructions or "")
    assert "notes_write" in tools.mcp.instructions and "backup" in tools.mcp.instructions


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


# ── iMessage tools (read-only, forwarded over the same ssh link) ───────────

IMESSAGE_REPLY = {"ok": True, "result": {"count": 1, "truncated": False, "rows_examined": 3, "filtered": {"otp": 1},
                                         "messages": [{"time": "2026-11-23T15:00:00-05:00", "chat": "Alex Example",
                                                       "sender": "Alex Example", "is_from_me": False,
                                                       "is_group": False, "text": "Hey are you free Saturday?"}]}}


async def test_imessage_recent_forwards_over_the_bus_link(ssh, tools):
    ssh.reply(IMESSAGE_REPLY)
    out = await call_json(tools, "imessage_recent", {"since": "24h"})
    assert out["count"] == 1 and out["messages"][0]["text"] == "Hey are you free Saturday?"
    assert ssh.sent() == {"tool": "imessage_recent", "args": {"since": "24h", "limit": 25}, "caller": ""}
    argv = (ssh.dir / "argv").read_text().split("\n")
    assert "StrictHostKeyChecking=yes" in argv and argv[-2] == "mark@192.0.2.10"  # the pinned link, nothing else


async def test_imessage_args_clamped_and_unset_dropped(ssh, tools):
    ssh.reply(IMESSAGE_REPLY)
    await call_json(tools, "imessage_search", {"query": "dinner", "limit": 5000})
    assert ssh.sent()["args"] == {"query": "dinner", "limit": 100}
    await call_json(tools, "imessage_unanswered", {"hours": 0, "limit": -3})
    assert ssh.sent()["args"] == {"hours": 1, "limit": 1}
    await call_json(tools, "imessage_threads", {})
    assert ssh.sent()["args"] == {"limit": 25}
    await call_json(tools, "imessage_search", {"query": "x", "contact": "Sam", "since": "2026-11-20"})
    assert ssh.sent()["args"] == {"query": "x", "contact": "Sam", "since": "2026-11-20", "limit": 25}


async def test_imessage_search_requires_query(tools):
    from fastmcp.exceptions import ValidationError

    with pytest.raises(ValidationError, match="query"):  # rejected by the schema before anything is sent
        await call_json(tools, "imessage_search", {})


async def test_imessage_service_errors_are_tool_errors(ssh, tools):
    from fastmcp.exceptions import ToolError

    ssh.reply({"ok": False, "error": "The iMessage service isn't running on the Mac mini (launchctl list | grep imessage-service)."})
    with pytest.raises(ToolError, match="iMessage service isn't running"):
        await call_json(tools, "imessage_recent", {})


async def test_imessage_descriptions_promise_read_only_and_no_codes(tools):
    listed = {t.name: t for t in await tools.mcp.list_tools()}
    for name in IMESSAGE_TOOLS:
        desc = (listed[name].description or "").lower()
        assert "read-only" in desc and "verification code" in desc and "live" in desc, name
        assert not {"project", "task", "message_text", "send"} & set(listed[name].parameters["properties"])
    assert "imessage_unanswered" in tools.mcp.instructions and "read-only" in tools.mcp.instructions


# ── imessage_send (limits enforced on the mini; this side only pre-checks sizes) ──

SEND_REPLY = {"ok": True, "result": {"status": "sent", "chat": "Alex Example", "chat_id": "any;-;+15555550101",
                                     "is_group": False, "messages": [{"text": "On my way", "is_sent": True}]}}


async def test_imessage_send_forwards_over_the_bus_link(ssh, tools):
    ssh.reply(SEND_REPLY)
    out = await call_json(tools, "imessage_send", {"chat": "Alex Example", "text": "On my way"})
    assert out["status"] == "sent" and out["messages"][0]["text"] == "On my way"
    assert ssh.sent() == {"tool": "imessage_send", "args": {"chat": "Alex Example", "text": "On my way"}, "caller": ""}


async def test_imessage_send_with_image(ssh, tools):
    ssh.reply(SEND_REPLY)
    await call_json(tools, "imessage_send", {"chat": "any;-;+15555550101", "text": "", "image_base64": "iVBORw0KGgo=",
                                             "image_filename": "a.png"})
    assert ssh.sent()["args"] == {"chat": "any;-;+15555550101", "text": "", "image_base64": "iVBORw0KGgo=",
                                  "image_filename": "a.png"}
    await call_json(tools, "imessage_send", {"chat": "x", "text": "hi", "image_filename": "a.png"})
    assert ssh.sent()["args"] == {"chat": "x", "text": "hi"}      # a filename without an image is dropped


@pytest.mark.parametrize("args,match", [
    ({"chat": "Alex", "text": "x" * 2001}, "limit is 2000"),
    ({"chat": "  ", "text": "hi"}, "`chat` must be"),
    ({"chat": "x" * 201, "text": "hi"}, "`chat` must be"),
    ({"chat": "Alex", "text": "   "}, "Nothing to send"),
    ({"chat": "Alex", "text": "", "image_base64": "A" * (14 * 1024 * 1024 + 4)}, "larger than 10 MB"),
])
async def test_imessage_send_rejects_oversized_input_before_it_travels(ssh, tools, args, match):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match=match):
        await call_json(tools, "imessage_send", args)
    assert not (ssh.dir / "stdin").exists() or ssh.sent() is None


async def test_imessage_send_mini_refusal_is_a_tool_error(ssh, tools):
    from fastmcp.exceptions import ToolError

    ssh.reply({"ok": False, "error": "2 chats match 'Family'; nothing was sent. Call again with one chat_id ..."})
    with pytest.raises(ToolError, match="2 chats match 'Family'"):
        await call_json(tools, "imessage_send", {"chat": "Family", "text": "hi"})


async def test_imessage_send_description_and_instructions(tools):
    listed = {t.name: t for t in await tools.mcp.list_tools()}
    tool = listed["imessage_send"]
    assert set(tool.parameters["properties"]) == {"chat", "text", "image_base64", "image_filename"}
    assert set(tool.parameters["required"]) == {"chat", "text"}
    desc = tool.description or ""
    for phrase in ("already exists", "Only when Mark asked", "2,000 characters", "10 MB", "10 sends per hour",
                   "chat_id", "Never a new recipient"):
        assert phrase in desc, phrase
    assert "imessage_send" in tools.mcp.instructions and "never guess" in tools.mcp.instructions


def test_request_body_limit_is_raised_for_images():
    import server
    from fastmcp.server.http import FastMCPStreamableHTTPSessionManager

    sm = FastMCPStreamableHTTPSessionManager(app=server.mcp._mcp_server)
    assert sm.max_request_body_size == server.MAX_REQUEST_BODY == 16 * 1024 * 1024
    assert sm.asgi_app.max_body_size == 16 * 1024 * 1024


def test_nginx_allows_16m_on_the_mcp_path():
    conf = (APP.parent.parent / "nginx" / "conf.d" / "production.conf").read_text()
    block = conf[conf.index("server_name mcp.markcheli.com;"):]
    block = block[:block.index("\n}\n")]
    loc = block[block.index("location ~ ^/((mcp|"):]
    assert "client_max_body_size 16m;" in loc[:loc.index("}")]


def test_no_imessage_tools_without_the_bus():
    from fastmcp import FastMCP
    from imessage import register_imessage_tools

    assert register_imessage_tools(FastMCP("bare"), None) == []


async def call_json(server, name, args) -> dict:
    res = await server.mcp.call_tool(name, args)
    return json.loads("".join(getattr(b, "text", "") for b in res.content))


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


# ── notes via basic-memory (fake in-memory server) ────────────────────────

BM_WRITE_TOOLS = ("bm_write", "bm_edit")  # forwarded as notes_write / notes_edit
BM_BLOCKED_TOOLS = ("bm_delete", "bm_move")  # upstream has them; never reachable


def make_fake_basic_memory(calls: list):
    """A FastMCP that looks like basic-memory 1.0.0: read tools, write tools, bm_project."""
    from fastmcp import FastMCP
    from fastmcp.exceptions import ToolError

    fake = FastMCP("fake-basic-memory")

    def read_tool(tool_name):
        # Every default is None so that only the arguments actually sent are recorded.
        async def fn(project: str, query: str | None = None, mode: str | None = None, path: str | None = None,
                     since: str | None = None, lines: int | None = None, max_matches: int | None = None,
                     filters: dict | None = None, note_types: list[str] | None = None,
                     identifier: str | None = None, compact: bool | None = None, page: int | None = None,
                     page_size: int | None = None, output_format: str | None = None, section: str | None = None,
                     start_line: int | None = None, end_line: int | None = None, max_tokens: int | None = None,
                     include_frontmatter: bool | None = None, include_content: bool | None = None,
                     glob: str | None = None, sort: str | None = None, name: str | None = None,
                     fields: list[str] | None = None, depth: int | None = None, max_related: int | None = None,
                     items: list[str] | None = None, command: str | None = None) -> str:
            received = dict(locals())  # the parameters, plus the closure's own names
            calls.append((tool_name, {k: v for k, v in received.items()
                                      if v is not None and k not in ("tool_name", "calls", "ToolError")}))
            if identifier == "missing.md":
                raise ToolError("Note not found: missing.md")
            return f"{tool_name} in {project}: " + (query or identifier or path or command or "")
        fake.tool(fn, name=tool_name)

    for tool_name in ("bm_search", "bm_read", "bm_list", "bm_find", "bm_context", "bm_project"):
        read_tool(tool_name)

    def write_tool(tool_name):
        async def fn(project: str, identifier: str | None = None, content: str | None = None,
                     command: str | None = None, title: str | None = None, directory: str | None = None,
                     note_type: str | None = None, tags: list[str] | str | None = None, metadata: dict | None = None,
                     overwrite: bool | None = None, expected_checksum: str | None = None, section: str | None = None,
                     find_text: str | None = None, expected_replacements: int | None = None,
                     replace_subsections: bool | None = None, output_format: str | None = None) -> str:
            received = dict(locals())
            calls.append((tool_name, {k: v for k, v in received.items()
                                      if v is not None and k not in ("tool_name", "calls", "ToolError")}))
            return f"{tool_name} in {project}: {identifier or title}"
        fake.tool(fn, name=tool_name)

    for tool_name in BM_WRITE_TOOLS + BM_BLOCKED_TOOLS:
        write_tool(tool_name)
    return fake


@pytest.fixture
def notes(tools, monkeypatch):
    calls: list = []
    fake = make_fake_basic_memory(calls)
    monkeypatch.setattr(tools.notes_bridge, "target", fake)
    return type("N", (), {"calls": calls, "fake": fake, "bridge": tools.notes_bridge})


def one_call(n):
    assert len(n.calls) == 1, n.calls
    return n.calls[0]


async def call(server, name, args):
    """Call a registered tool the way the MCP layer does (schema validation included), minus transport/auth."""
    res = await server.mcp.call_tool(name, args)
    return "\n".join(getattr(b, "text", "") for b in res.content)


async def test_notes_search_forwards_with_project_pinned(notes, tools):
    out = await call(tools, "notes_search", {"query": "Mac mini", "lines": 2, "path": "02-systems"})
    assert out == "bm_search in main: Mac mini"
    tool, sent = one_call(notes)
    assert tool == "bm_search"
    assert sent == {"project": "main", "query": "Mac mini", "lines": 2, "path": "02-systems",
                    "max_matches": 10, "compact": False, "page": 1, "page_size": 10, "output_format": "text"}


async def test_notes_read_and_recent_pin_project_and_command(notes, tools):
    await call(tools, "notes_read", {"identifier": "02-systems/mac-mini.md", "section": "Agents"})
    await call(tools, "notes_recent", {"since": "3d"})
    assert [t for t, _ in notes.calls] == ["bm_read", "bm_project"]
    assert notes.calls[0][1]["project"] == "main" and notes.calls[0][1]["section"] == "Agents"
    assert notes.calls[1][1]["command"] == "recent" and notes.calls[1][1]["project"] == "main"


@pytest.mark.parametrize("tool", BM_BLOCKED_TOOLS + ("bm_man", "bm_schema", "nope"))
async def test_bridge_refuses_tools_off_the_allowlist(notes, tool):
    from notes import NotesError

    with pytest.raises(NotesError, match="isn't available"):
        await notes.bridge.call(tool, {"content": "x", "identifier": "y"})
    assert notes.calls == []  # nothing reached basic-memory


async def test_notes_write_forwards_with_project_pinned(notes, tools):
    out = await call(tools, "notes_write", {"content": "---\ntitle: T\n---\n# T\n", "identifier": "00-x/t.md",
                                            "tags": ["a"]})
    assert out == "bm_write in main: 00-x/t.md"
    tool, sent = one_call(notes)
    assert tool == "bm_write"
    assert sent == {"project": "main", "content": "---\ntitle: T\n---\n# T\n", "identifier": "00-x/t.md",
                    "note_type": "note", "tags": ["a"], "output_format": "text"}  # overwrite unset -> upstream default
    # a project passed to the bridge itself is replaced, never forwarded
    assert notes.bridge.prepare("bm_write", {"content": "x", "identifier": "y.md", "project": "other",
                                             "workspace": "w"}) == {"content": "x", "identifier": "y.md",
                                                                    "project": "main"}


async def test_notes_edit_keeps_its_command_and_pins_project(notes, tools):
    out = await call(tools, "notes_edit", {"identifier": "02-systems/mac-mini.md", "command": "append",
                                           "content": "- more\n", "expected_checksum": "abc"})
    assert out == "bm_edit in main: 02-systems/mac-mini.md"
    tool, sent = one_call(notes)
    assert tool == "bm_edit"
    assert sent == {"project": "main", "identifier": "02-systems/mac-mini.md", "command": "append",
                    "content": "- more\n", "expected_checksum": "abc", "expected_replacements": 1,
                    "replace_subsections": True, "output_format": "text"}
    with pytest.raises(Exception):  # the edit kind is validated by the schema, not forwarded blindly
        await call(tools, "notes_edit", {"identifier": "x.md", "command": "delete_everything"})
    assert len(notes.calls) == 1


@pytest.mark.parametrize("args", [
    {"identifier": "../etc/passwd"},
    {"identifier": "/notes/x.md"},
    {"identifier": "02-systems/../../x.md"},
    {"identifier": "templates/daily.md"},
    {"title": "daily", "directory": "templates"},
    {"title": "x", "directory": "/templates/"},
    {"identifier": "file:///etc/hosts"},
])
async def test_writes_stay_inside_the_vault_and_out_of_templates(notes, tools, args):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="vault|templates"):
        await call(tools, "notes_write", {"content": "x", **args})
    if "identifier" in args:
        with pytest.raises(ToolError, match="vault|templates"):
            await call(tools, "notes_edit", {"identifier": args["identifier"], "command": "append", "content": "x"})
    assert notes.calls == []  # refused before anything reached basic-memory
    # reads are not restricted the same way (permalinks, titles, memory:// URLs all work)
    await call(tools, "notes_read", {"identifier": "memory://main/02-systems/mac-mini"})
    assert len(notes.calls) == 1


async def test_bridge_overrides_scope_and_command_arguments(notes):
    sent = notes.bridge.prepare("bm_search", {"query": "x", "project": "other", "projects": ["a"],
                                              "all_projects": True, "workspace": "w", "page": None})
    assert sent == {"query": "x", "project": "main"}
    sent = notes.bridge.prepare("bm_project", {"command": "create", "name": "evil", "path": "/tmp"})
    assert sent["command"] == "recent" and sent["project"] == "main"
    await notes.bridge.call("bm_project", {"command": "create", "name": "evil"})
    assert one_call(notes)[1]["command"] == "recent"


async def test_delete_and_move_absent_even_though_upstream_has_them(notes, tools):
    from fastmcp import Client
    from fastmcp.exceptions import NotFoundError

    async with Client(notes.fake) as c:  # the fake really does offer them
        assert set(t.name for t in await c.list_tools()) >= set(BM_BLOCKED_TOOLS + BM_WRITE_TOOLS)
    names = {t.name for t in await tools.mcp.list_tools()}
    assert not {n for n in names if n.startswith("bm_")}  # bm_* names never surface, write/edit included
    assert not {n for n in names if "delete" in n or "move" in n}
    for name in BM_BLOCKED_TOOLS + BM_WRITE_TOOLS:
        with pytest.raises(NotFoundError, match="Unknown tool"):  # unknown at the MCP layer
            await tools.mcp.call_tool(name, {"project": "main", "content": "x", "identifier": "x.md"})
    assert notes.calls == []


async def test_upstream_tool_error_is_passed_on(notes, tools):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="Note not found"):
        await call(tools, "notes_read", {"identifier": "missing.md"})


async def test_basic_memory_down_is_a_tool_error_and_seafile_still_works(tools, monkeypatch):
    from fastmcp.exceptions import ToolError

    monkeypatch.setattr(tools.notes_bridge, "target", "http://127.0.0.1:9/mcp")
    monkeypatch.setattr(tools.notes_bridge, "timeout", 3.0)
    with pytest.raises(ToolError, match="isn't reachable"):
        await call(tools, "notes_search", {"query": "anything"})
    out = await tools.list_directory("/")
    assert {e["name"] for e in out["entries"]} == {"03-diary", "05-raw", "README.md"}


async def test_startup_probe_never_raises(tools, monkeypatch):
    from notes import NotesError

    monkeypatch.setattr(tools.notes_bridge, "target", "http://127.0.0.1:9/mcp")
    with pytest.raises(NotesError, match="isn't reachable"):
        await tools.notes_bridge.probe()
    calls: list = []
    monkeypatch.setattr(tools.notes_bridge, "target", make_fake_basic_memory(calls))
    assert set(await tools.notes_bridge.probe()) >= set(tools.UPSTREAM_TOOLS)


async def test_no_notes_tools_without_url(tools, monkeypatch):
    from fastmcp import FastMCP
    from notes import register_notes_tools

    monkeypatch.delenv("NOTES_MCP_URL", raising=False)
    assert tools.build_notes() is None
    bare = FastMCP("bare")
    assert register_notes_tools(bare, None) == []
    assert await bare.list_tools() == []
    assert set(register_notes_tools(FastMCP("x"), tools.notes_bridge)) == NOTES_TOOLS


@pytest.mark.parametrize("kwargs,match", [
    ({"target": "basic-memory:8000"}, "http"),
    ({"timeout": 100}, "Cloudflare"),
    ({"project": " "}, "PROJECT"),
])
def test_notes_config_validation(kwargs, match):
    from notes import NotesBridge

    with pytest.raises(ValueError, match=match):
        NotesBridge(**{"target": "http://basic-memory:8000/mcp", **kwargs})


def test_notes_default_timeout_fits_cloudflare():
    import inspect

    from notes import NotesBridge

    assert inspect.signature(NotesBridge).parameters["timeout"].default <= 30


def test_render_skips_binary_blocks():
    from notes import render

    class Img:
        type = "image"

    class Txt:
        type = "text"
        text = "hello"

    assert render([Txt(), Img()]) == "hello\n[image content omitted]"


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
    (backup,) = tmp_path.glob(".env.bak*")
    assert backup.name == ".env.bak"
    assert "old" in backup.read_text() and stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_env_set_keeps_one_backup_overwritten_each_run(tmp_path):
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.bak").write_text("STALE=1\n")
    (tmp_path / ".env.bak").chmod(0o644)
    assert run_env_set(tmp_path, "A=2\n").returncode == 0
    assert run_env_set(tmp_path, "A=3\n").returncode == 0
    (backup,) = tmp_path.glob(".env.bak*")
    assert backup.read_text() == "A=2\n" and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert (tmp_path / ".env").read_text() == "A=3\n"


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
    assert not list(tmp_path.glob(".env.bak*"))
