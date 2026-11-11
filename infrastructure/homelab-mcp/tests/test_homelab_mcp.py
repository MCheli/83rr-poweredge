"""Tests for homelab-mcp against a fake Seafile (no network, no Google).

Run from infrastructure/homelab-mcp:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest -q
"""

from __future__ import annotations

import json
import os
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


async def test_only_read_only_tools_registered(tools):
    listed = await tools.mcp.list_tools()
    names = {t.name for t in listed}
    assert names == {"library_info", "list_directory", "find_files", "read_file", "search_text"}
    for t in listed:
        assert t.annotations.read_only_hint is True


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
        assert meta.json()["registration_endpoint"].startswith("https://mcp.example.com")
