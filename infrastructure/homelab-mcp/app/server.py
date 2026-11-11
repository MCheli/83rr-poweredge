"""homelab-mcp: Mark's claude.ai connector for his homelab.

It always offers read-only tools for the Seafile "AI Context" library. When
BUS_SSH_TARGET is set it also offers session-bus tools that start and manage
Claude Code sessions on the Mac mini, reached over the LAN by ssh (see bus.py);
the mini itself is never exposed to the internet.

Auth: claude.ai talks OAuth 2.1 (dynamic client registration + PKCE) to this
server. FastMCP's GoogleProvider proxies the actual sign-in to Google, and
AllowlistGoogleProvider below then rejects every token whose verified Google
email isn't in ALLOWED_EMAILS, so the only person who can use it is Mark.

Seafile tools are read-only: list, find, read and grep files in one library.
The Seafile token itself must be a read-only library token (checked at startup).
"""

from __future__ import annotations

import fnmatch
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse

from bus import BusError, MiniBus
from seafile import SeafileError, SeafileLibrary, normalize_path

log = logging.getLogger("homelab-mcp")

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
# Starting, messaging or stopping a session changes things; claude.ai asks before these by default.
ACTS = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"homelab-mcp: {name} must be set")
    return value or ""


def parse_allowlist(raw: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


class AllowlistGoogleProvider(GoogleProvider):
    """GoogleProvider that only accepts verified emails on an allowlist."""

    def __init__(self, *, allowed_emails: frozenset[str], **kwargs):
        if not allowed_emails:
            raise ValueError("ALLOWED_EMAILS is empty; refusing to start an open server")
        super().__init__(**kwargs)
        self._allowed_emails = allowed_emails

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = await super().load_access_token(token)
        if access is None:
            return None
        claims = access.claims or {}
        email = (claims.get("email") or "").lower()
        verified = claims.get("email_verified") in (True, "true")
        if not (verified and email in self._allowed_emails):
            log.warning("Rejected token for a Google account that isn't on the allowlist")
            return None
        return access


def build_auth() -> AllowlistGoogleProvider:
    return AllowlistGoogleProvider(
        allowed_emails=parse_allowlist(env("ALLOWED_EMAILS", required=True)),
        client_id=env("GOOGLE_CLIENT_ID", required=True),
        client_secret=env("GOOGLE_CLIENT_SECRET", required=True),
        base_url=env("PUBLIC_BASE_URL", required=True),
        required_scopes=["openid", "email"],
        jwt_signing_key=env("JWT_SIGNING_KEY", required=True),
        # Only claude.ai may receive authorization codes.
        allowed_client_redirect_uris=[
            u.strip()
            for u in env(
                "ALLOWED_CLIENT_REDIRECT_URIS",
                "https://claude.ai/api/mcp/auth_callback,https://claude.com/api/mcp/auth_callback",
            ).split(",")
            if u.strip()
        ],
        # Pick the Google account each time instead of silently reusing one.
        extra_authorize_params={"access_type": "offline", "prompt": "consent select_account"},
        cache_ttl_seconds=300,
    )


MAX_READ_BYTES = int(env("MAX_READ_BYTES", str(2 * 1024 * 1024)))
SEARCH_MAX_FILES = int(env("SEARCH_MAX_FILES", "400"))
SEARCH_MAX_FILE_BYTES = int(env("SEARCH_MAX_FILE_BYTES", str(512 * 1024)))
# Dates without an offset ("2026-11-10") are read in Mark's time zone.
LOCAL_TZ = ZoneInfo(env("TZ_NAME", "America/New_York"))
TEXT_SUFFIXES = (".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv", ".log", ".html", ".xml", ".toml", ".ini")

library: SeafileLibrary | None = None


def lib() -> SeafileLibrary:
    if library is None:
        raise ToolError("The Seafile library isn't connected yet.")
    return library


@asynccontextmanager
async def lifespan(_server):
    global library
    library = SeafileLibrary(
        base_url=env("SEAFILE_URL", "http://seafile"),
        public_url=env("SEAFILE_PUBLIC_URL", "https://files.markcheli.com"),
        host_header=env("SEAFILE_HOST_HEADER", "files.markcheli.com"),
        token=env("SEAFILE_REPO_TOKEN", required=True),
    )
    try:
        await library.check_read_only()
        info = await library.info()
        log.info("Connected to Seafile library %r (%s files)", info["name"], info["file_count"])
    except SeafileError as e:
        await library.aclose()
        raise RuntimeError(f"homelab-mcp: {e}") from e
    try:
        yield
    finally:
        await library.aclose()


def decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        # A multi-byte character cut at a truncation boundary is still text.
        if e.start >= len(data) - 4:
            return data[: e.start].decode("utf-8")
        return None


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as e:
        raise ToolError("modified_since must be an ISO date like 2026-11-01") from e
    return dt if dt.tzinfo else dt.replace(tzinfo=LOCAL_TZ)


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def entry_time(mtime: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(mtime)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def newest_first(entries):
    return sorted(entries, key=lambda e: entry_time(e.mtime) or EPOCH, reverse=True)


INSTRUCTIONS = """\
Read-only access to Mark's "AI Context" library in his self-hosted Seafile: \
an extended-memory folder about him (01-about-me), his systems and tools \
(02-systems), his daily diary (03-diary, one Markdown file per day), and raw \
nightly dumps (05-raw). Start with read_file("/README.md") to learn the layout. \
Use find_files to locate files by name or date, search_text to grep contents, \
and read_file to read one. Nothing here can change, move or share files.\
"""

BUS_INSTRUCTIONS = """\
 The bus_* tools start and manage Claude Code sessions on Mark's Mac mini, which \
is on his home network and works in his repos (~/repos, already cloned there). \
Use them when a task needs something local. Give bus_spawn a unique name and \
complete, standalone instructions (the session sees only your task text), then \
poll bus_wait (30 s per call) or bus_status for its report, and use bus_send for \
follow-ups. If a call times out, check bus_sessions before retrying. Sessions ask \
Mark (in the Claude app, Code tab) before edits or commands his rules don't \
allow, never bypass permission checks, at most three run at once, and they must \
not merge, deploy or delete unless Mark agreed to it in this chat.\
"""


def build_bus() -> MiniBus | None:
    target = env("BUS_SSH_TARGET")
    if not target:
        return None
    try:
        return MiniBus(target=target, private_key_b64=env("BUS_SSH_KEY_B64", required=True),
                       host_key=env("BUS_SSH_HOST_KEY", required=True), port=int(env("BUS_SSH_PORT", "22")))
    except ValueError as e:
        sys.exit(f"homelab-mcp: {e}")


mini_bus = build_bus()

mcp = FastMCP("homelab", instructions=INSTRUCTIONS + (BUS_INSTRUCTIONS if mini_bus else ""),
              auth=build_auth(), lifespan=lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool(annotations=READ_ONLY)
async def library_info() -> dict:
    """Name, size, file count and last-modified time of the AI Context library."""
    try:
        return await lib().info()
    except SeafileError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=READ_ONLY)
async def list_directory(path: str = "/") -> dict:
    """List one folder of the AI Context library (not recursive). Paths start at "/"."""
    try:
        entries = await lib().list_dir(path)
    except SeafileError as e:
        raise ToolError(str(e)) from e
    return {"path": normalize_path(path), "entries": [e.as_dict() for e in entries]}


@mcp.tool(annotations=READ_ONLY)
async def find_files(
    path: str = "/",
    name_glob: str | None = None,
    modified_since: str | None = None,
    limit: int = 200,
) -> dict:
    """Find files under a folder, newest first.

    name_glob matches the file name, case-insensitively (e.g. "2026-11-*.md").
    modified_since is an ISO date or datetime (US Eastern unless it has an
    offset); only files changed at or after it are returned. Use this to find recent diary entries, e.g.
    find_files("/03-diary", modified_since="2026-11-01").
    """
    since = parse_since(modified_since)
    limit = max(1, min(limit, 1000))
    try:
        entries = await lib().walk(path)
    except SeafileError as e:
        raise ToolError(str(e)) from e
    files = []
    for e in entries:
        if e.type != "file":
            continue
        if name_glob and not fnmatch.fnmatch(e.name.lower(), name_glob.lower()):
            continue
        if since:
            t = entry_time(e.mtime)
            if t is None or t < since:
                continue
        files.append(e)
    files = newest_first(files)
    return {"count": len(files), "truncated": len(files) > limit, "files": [e.as_dict() for e in files[:limit]]}


@mcp.tool(annotations=READ_ONLY)
async def read_file(path: str, offset: int = 0, max_chars: int = 60000) -> dict:
    """Read a text file from the library.

    Long files come back in pages: pass the returned next_offset as offset to
    continue. Binary files (images, PDFs) are reported, not returned.
    """
    max_chars = max(1000, min(max_chars, 200_000))
    offset = max(0, offset)
    try:
        data, truncated = await lib().read_bytes(path, MAX_READ_BYTES)
    except SeafileError as e:
        raise ToolError(str(e)) from e
    text = decode_text(data)
    if text is None:
        return {"path": normalize_path(path), "binary": True, "size_read": len(data),
                "note": "Binary file; only text files can be read."}
    page = text[offset : offset + max_chars]
    end = offset + len(page)
    more = end < len(text)
    return {
        "path": normalize_path(path),
        "offset": offset,
        "content": page,
        "next_offset": end if more else None,
        "file_truncated_at_bytes": MAX_READ_BYTES if truncated else None,
    }


@mcp.tool(annotations=READ_ONLY)
async def search_text(query: str, path: str = "/", case_sensitive: bool = False, max_matches: int = 100) -> dict:
    """Search the contents of text files under a folder for a phrase.

    Returns matching lines with file paths and line numbers, newest files first.
    Only text-like files (.md, .txt, .json, .yaml, .csv, ...) up to a size cap
    are searched; skipped counts are reported.
    """
    if not query.strip():
        raise ToolError("query is empty")
    max_matches = max(1, min(max_matches, 500))
    needle = query if case_sensitive else query.lower()
    try:
        entries = await lib().walk(path)
    except SeafileError as e:
        raise ToolError(str(e)) from e
    candidates = [e for e in entries if e.type == "file" and e.name.lower().endswith(TEXT_SUFFIXES)]
    candidates = newest_first(candidates)
    skipped_large = [e for e in candidates if (e.size or 0) > SEARCH_MAX_FILE_BYTES]
    candidates = [e for e in candidates if (e.size or 0) <= SEARCH_MAX_FILE_BYTES]
    skipped_over_limit = max(0, len(candidates) - SEARCH_MAX_FILES)
    matches: list[dict] = []
    searched = 0
    for e in candidates[:SEARCH_MAX_FILES]:
        try:
            data, _ = await lib().read_bytes(e.path, SEARCH_MAX_FILE_BYTES)
        except SeafileError:
            continue
        searched += 1
        text = decode_text(data)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if needle in (line if case_sensitive else line.lower()):
                matches.append({"path": e.path, "line": n, "text": line[:500]})
                if len(matches) >= max_matches:
                    break
        if len(matches) >= max_matches:
            break
    return {
        "query": query,
        "files_searched": searched,
        "files_skipped_too_large": len(skipped_large),
        "files_skipped_over_limit": skipped_over_limit,
        "match_limit_reached": len(matches) >= max_matches,
        "matches": matches,
    }


# ── session bus on the Mac mini (only when BUS_SSH_TARGET is set) ─────────


def caller_email() -> str:
    tok = get_access_token()
    return str(((tok.claims or {}).get("email") if tok else "") or "")


async def bus_call(tool: str, args: dict):
    if mini_bus is None:
        raise ToolError("The Mac mini session bus isn't configured on this server.")
    try:
        return await mini_bus.call(tool, {k: v for k, v in args.items() if v is not None}, caller_email())
    except BusError as e:
        raise ToolError(str(e)) from e


async def bus_doctor(repo: str | None = None) -> dict:
    """Check the session bus on the Mac mini: Claude Code version and sign-in, repos, settings.

    Pass `repo` (a repo name under ~/repos) to check that folder's workspace
    trust. Run this first if a spawn fails.
    """
    return await bus_call("bus_doctor", {"repo": repo})


async def bus_spawn(
    task: str,
    name: str,
    repo: str | None = None,
    cwd: str | None = None,
    mode: Literal["background", "remote"] | None = None,
    permission_mode: Literal["default", "plan", "dontAsk", "acceptEdits", "auto", "manual"] | None = None,
    model: str | None = None,
    isolation: Literal["worktree", "none"] | None = None,
    base: str | None = None,
) -> dict:
    """Start a Claude Code session on the Mac mini to carry out a task.

    task: complete, standalone instructions (the session sees nothing else).
    name: required, unique, lowercase letters, digits and hyphens (max 40). A
    retry with the same name can't start a second session.
    Give one of repo (a repo already cloned under ~/repos, such as
    "83rr-poweredge") or cwd (a folder inside one).
    mode: "background" (default; shows in the Claude app) or "remote" (tmux).
    permission_mode defaults to "default", which asks Mark before anything his
    rules don't allow. The Mac mini only accepts default, plan and dontAsk unless
    Mark enabled more; bypassing permissions isn't possible. At most three
    sessions run at once.
    """
    return await bus_call("bus_spawn", {
        "task": task, "repo": repo, "cwd": cwd, "name": name, "mode": mode, "permission_mode": permission_mode,
        "model": model, "isolation": isolation, "base": base, "parent": "claude.ai"})


async def bus_sessions(all: bool = False, limit: int = 30) -> dict:
    """List sessions started through the session bus in ~/repos on the Mac mini, with state
    and report status. all=true includes stopped ones."""
    return await bus_call("bus_sessions", {"all": all, "limit": limit})


async def bus_status(target: str) -> dict:
    """One session's state and, once written, its final report. target: session name or task id."""
    return await bus_call("bus_status", {"target": target})


async def bus_logs(target: str, lines: int = 40) -> dict:
    """The recent output of a session on the Mac mini (up to 300 lines)."""
    return await bus_call("bus_logs", {"target": target, "lines": lines})


async def bus_send(target: str, message: str, wait_seconds: int = 20) -> dict:
    """Send a follow-up message to a session. A background session continues the same
    conversation once it's idle (waits up to 20 s); a stopped one is resumed, which
    counts toward the three-session limit. Then call bus_wait with newer_than
    set to the time you sent it, to collect the updated report."""
    return await bus_call("bus_send", {"target": target, "message": message, "wait_seconds": wait_seconds})


async def bus_wait(target: str, timeout_seconds: int = 30, newer_than: str | None = None) -> dict:
    """Wait up to 30 s for a session's report (or for it to stop). Call again to keep waiting.
    newer_than: an ISO time; only a report written after it counts."""
    return await bus_call("bus_wait", {"target": target, "timeout_seconds": timeout_seconds,
                                       "newer_than": newer_than})


async def bus_stop(target: str, remove: bool = False) -> dict:
    """Stop a session on the Mac mini. Its branch and commits are kept; remove=true also
    drops it from Claude Code's agent list."""
    return await bus_call("bus_stop", {"target": target, "remove": remove})


BUS_TOOLS = {bus_doctor: READ_ONLY, bus_spawn: ACTS, bus_sessions: READ_ONLY, bus_status: READ_ONLY,
             bus_logs: READ_ONLY, bus_send: ACTS, bus_wait: READ_ONLY, bus_stop: ACTS}
if mini_bus is not None:
    for fn, hints in BUS_TOOLS.items():
        mcp.tool(fn, annotations=hints)


def main() -> None:
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx2 logs every request URL at INFO, and Seafile download URLs carry a
    # one-time fileserver token. Keep them out of the shipped logs.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    mcp.run(transport="http", host="0.0.0.0", port=int(env("PORT", "8000")), path="/mcp", show_banner=False)


if __name__ == "__main__":
    main()
