"""Read-only client for one Seafile library, via a library-scoped API token.

Seafile 13 "repo API tokens" (library > Settings > API Token) are bound to a
single library and carry their own permission (r or rw). This client only ever
issues GET requests, and refuses to start if the token is not read-only, so a
mis-issued rw token can't turn the connector into a writer.

Endpoints used (all GET, all under /api/v2.1/via-repo-token/):
  repo-info/       library name, size, file count, last modified
  dir/             directory listing (optionally recursive)
  download-link/   one-time fileserver URL for a file's bytes
"""

from __future__ import annotations

import posixpath
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx2


class SeafileError(Exception):
    """A Seafile request failed in a way the caller should report."""


def normalize_path(path: str | None) -> str:
    """Return a clean absolute library path, rejecting traversal."""
    raw = (path or "/").strip()
    if "\x00" in raw:
        raise SeafileError("Path contains a null byte.")
    if not raw.startswith("/"):
        raw = "/" + raw
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise SeafileError("Path may not contain '..'.")
    return "/" + "/".join(parts)


@dataclass(frozen=True)
class Entry:
    path: str
    name: str
    type: str  # "file" or "dir"
    size: int | None
    mtime: str

    def as_dict(self) -> dict:
        d = {"path": self.path, "name": self.name, "type": self.type, "modified": self.mtime}
        if self.type == "file":
            d["size"] = self.size
        return d


class SeafileLibrary:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        public_url: str | None = None,
        host_header: str | None = None,
        timeout: float = 30.0,
        tree_cache_seconds: float = 60.0,
        transport: httpx2.AsyncBaseTransport | None = None,
    ):
        if not token:
            raise ValueError("SEAFILE_REPO_TOKEN is empty")
        self.base_url = base_url.rstrip("/")
        self.public_url = (public_url or "").rstrip("/")
        headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
        if host_header:
            # Seahub builds URLs and checks ALLOWED_HOSTS from Host; talk to the
            # container directly but present the public name, like the edge does.
            headers["Host"] = host_header
            headers["X-Forwarded-Proto"] = "https"
        self._client = httpx2.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self._tree_cache_seconds = tree_cache_seconds
        self._tree_cache: tuple[float, str, list[Entry]] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── low level ──────────────────────────────────────────────────────────

    async def _get_json(self, endpoint: str, params: dict | None = None):
        url = f"/api/v2.1/via-repo-token/{endpoint}"
        try:
            resp = await self._client.get(url, params=params)
        except httpx2.RequestError as e:
            raise SeafileError(f"Seafile is unreachable: {type(e).__name__}") from e
        if resp.status_code == 404:
            raise SeafileError("Not found.")
        if resp.status_code in (401, 403):
            raise SeafileError("Seafile refused the library token (revoked or wrong library?).")
        if resp.status_code >= 400:
            raise SeafileError(f"Seafile returned HTTP {resp.status_code}.")
        return resp.json()

    def _internal_download_url(self, url: str) -> str:
        """Point a fileserver URL Seafile built for the public host at the container."""
        if self.public_url and url.startswith(self.public_url + "/"):
            return self.base_url + url[len(self.public_url):]
        parts = urlsplit(url)
        if parts.path.startswith("/seafhttp/"):
            return self.base_url + parts.path + (f"?{parts.query}" if parts.query else "")
        raise SeafileError("Seafile returned an unexpected download URL.")

    # ── library operations ─────────────────────────────────────────────────

    async def info(self) -> dict:
        data = await self._get_json("repo-info/")
        return {
            "name": data.get("repo_name"),
            "size_bytes": data.get("size"),
            "file_count": data.get("file_count"),
            "last_modified": data.get("last_modified"),
        }

    async def check_read_only(self) -> str:
        """Return the token's permission; raise unless it is read-only."""
        data = await self._get_json("dir/", {"path": "/"})
        perm = data.get("user_perm")
        if perm != "r":
            raise SeafileError(
                f"The library token has permission {perm!r}; this connector only runs "
                "with a read-only ('r') token. Issue a new token with Read-Only permission."
            )
        return perm

    async def list_dir(self, path: str = "/") -> list[Entry]:
        path = normalize_path(path)
        data = await self._get_json("dir/", {"path": path})
        out = []
        for item in data.get("dirent_list", []):
            name = item.get("name", "")
            out.append(
                Entry(
                    path=posixpath.join(path, name),
                    name=name,
                    type="dir" if item.get("type") == "dir" else "file",
                    size=item.get("size"),
                    mtime=item.get("mtime", ""),
                )
            )
        return out

    async def walk(self, path: str = "/") -> list[Entry]:
        """Every entry under path (recursive), cached briefly."""
        path = normalize_path(path)
        now = time.monotonic()
        cached = self._tree_cache
        if cached and cached[1] == path and now - cached[0] < self._tree_cache_seconds:
            return cached[2]
        data = await self._get_json("dir/", {"path": path, "recursive": "1"})
        out = []
        for item in data.get("dirent_list", []):
            name = item.get("name", "")
            parent = normalize_path(item.get("parent_dir") or path)
            out.append(
                Entry(
                    path=posixpath.join(parent, name),
                    name=name,
                    type="dir" if item.get("type") == "dir" else "file",
                    size=item.get("size"),
                    mtime=item.get("mtime", ""),
                )
            )
        self._tree_cache = (now, path, out)
        return out

    async def read_bytes(self, path: str, max_bytes: int) -> tuple[bytes, bool]:
        """Return up to max_bytes of the file and whether it was truncated."""
        path = normalize_path(path)
        if path == "/":
            raise SeafileError("That's the library root, not a file.")
        link = await self._get_json("download-link/", {"path": path})
        if not isinstance(link, str):
            raise SeafileError("Seafile returned an unexpected download link.")
        url = self._internal_download_url(link)
        try:
            async with self._client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise SeafileError(f"Download failed with HTTP {resp.status_code}.")
                buf = bytearray()
                truncated = False
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        truncated = True
                        del buf[max_bytes:]
                        break
                return bytes(buf), truncated
        except httpx2.RequestError as e:
            raise SeafileError(f"Download failed: {type(e).__name__}") from e
