#!/usr/bin/env python3
"""Push the AI Context vaults on this server into the Seafile library, as a backup.

The reverse of seafile-pull.py, for after the 2026-11-23 cut-over: the folders
under /data/ai-context are the main copy, and the Seafile "AI Context" library
is a backup that only ever receives. Designed for a cron job: it lists the
library once, uploads only the local files that changed since the last run
(or that Seafile lacks), and

- never deletes or moves anything in Seafile (there is no delete call here);
- never touches the work folders: anything that would land under /04-work or
  /05-raw/work-laptop is refused, whatever the config says (NEVER_PUSH);
- skips every dot-path (.git, .obsidian, .trash, ...) and every file the
  vault's .gitignore ignores (that is where the secret-flagged raw files are
  listed), plus the bare file names in exclude_names;
- needs a *library API token* with Read-Write permission (the vault's own
  token file, mode 600); it refuses a read-only one;
- guards against something still writing into Seafile (guard_prefixes, default
  /03-diary, where the old diary skill wrote): before uploading, every Seafile
  file under a guarded prefix that is missing on this server, or that Seafile
  holds in a version this script did not upload and with a newer mtime than the
  local copy, is logged as "DIVERGED <path>", is never overwritten, and is not
  imported. Someone has to look at it and resolve it by hand.

Config is a JSON file (kept outside the repo, e.g. /data/ai-context/push-config.json):

{
  "seafile_url": "https://files.example.com",
  "token_file": "/data/ai-context/.secrets/seafile-rw-token",
  "state_dir": "/data/ai-context/state/seafile-push",
  "max_file_mb": 90,
  "guard_prefixes": ["/03-diary"],
  "exclude_names": ["some-file.md"],
  "targets": [
    {"name": "notes", "src": "/data/ai-context/notes", "remote_root": "/"},
    {"name": "raw",   "src": "/data/ai-context/raw",   "remote_root": "/05-raw"}
  ]
}

Change detection: the state file (one per target) remembers size, mtime and
SHA-256 of every file as last uploaded or seen in sync. A file whose size and
mtime are unchanged is skipped without hashing; otherwise it is hashed and
uploaded when the hash differs. A file not in the state yet (first run, new
file) is compared with Seafile's listing: same size and a Seafile mtime at
least as new as the local one counts as in sync (seafile-pull.py set local
mtimes from Seafile), anything else is uploaded. So the first run after the
cut-over uploads only what changed locally since the last pull. After each
upload the Seafile file id comes back and is kept as remote_id, which is how
the guard tells "our own upload" (newer mtime, same id) from a foreign write.

Usage: seafile-backup-push.py --config /data/ai-context/push-config.json [--dry-run]
       [--target notes] [--max-files N] [--adopt-remote]

--adopt-remote (run once, by hand, when you know Seafile holds nothing but this
script's own uploads): records the current Seafile file id as remote_id for
every state entry that lacks one and whose local file is unchanged, so the
guard does not flag the files uploaded before the guard existed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API = "/api/v2.1/via-repo-token/"
# Remote path prefixes that are never written, whatever the config says.
NEVER_PUSH = ("/04-work", "/05-raw/work-laptop")


class Seafile:
    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        # Cloudflare's WAF answers 403 to urllib's default User-Agent
        self.headers = {"Authorization": f"Token {token}", "Accept": "application/json",
                        "User-Agent": "seafile-backup-push/1.0 (+homelab cron)"}
        self.timeout = timeout
        self.known_dirs: set[str] = {"/"}

    def _request(self, url: str, data: bytes | None = None, method: str | None = None,
                 headers: dict | None = None, retries: int = 3) -> bytes:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, method=method,
                                             headers={**self.headers, **(headers or {})})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise RuntimeError(f"Seafile refused the token (HTTP {e.code})") from e
                if e.code == 404:
                    raise FileNotFoundError(url) from e
                last = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
            time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"request failed after {retries} tries: {type(last).__name__}: {last}")

    def api(self, endpoint: str, params: dict, method: str = "GET", form: dict | None = None):
        url = f"{self.base}{API}{endpoint}?{urllib.parse.urlencode(params)}"
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"} if data else None
        return json.loads(self._request(url, data, method, hdrs) or b"null")

    def permission(self) -> str | None:
        return self.api("dir/", {"path": "/"}).get("user_perm")

    def listing(self) -> dict[str, dict]:
        """Every file in the library: full path -> {id, mtime, size}."""
        data = self.api("dir/", {"path": "/", "recursive": "1"})
        files: dict[str, dict] = {}
        for item in data.get("dirent_list", []):
            parent = norm(item.get("parent_dir") or "/")
            full = posixpath.join(parent, item.get("name", ""))
            if item.get("type") == "dir":
                self.known_dirs.add(full)
            elif item.get("type") == "file":
                files[full] = dict(id=item.get("id"), mtime=item.get("mtime", ""), size=item.get("size"))
                self.known_dirs.add(parent)
        return files

    def _internal(self, link) -> str:
        if not isinstance(link, str):
            raise RuntimeError("unexpected link response")
        parts = urllib.parse.urlsplit(link)
        if not parts.path.startswith("/seafhttp/"):
            raise RuntimeError("unexpected fileserver link")
        # Rewrite to our base URL in case Seafile built the link for another host
        return self.base + parts.path + (f"?{parts.query}" if parts.query else "")

    def ensure_dir(self, path: str) -> None:
        if path in self.known_dirs:
            return
        self.ensure_dir(posixpath.dirname(path))
        try:
            self.api("dir/", {"path": path})
        except FileNotFoundError:
            self.api("dir/", {"path": path}, "POST", {"operation": "mkdir"})
        self.known_dirs.add(path)

    def upload(self, parent: str, name: str, content: bytes) -> str | None:
        """Create or replace parent/name with content (replace=1: no "(1)" copies).
        Returns the new Seafile file id when the server reports it."""
        link = self._internal(self.api("upload-link/", {"path": parent}))
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (("parent_dir", parent), ("replace", "1")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                     "Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        raw = self._request(link + "?ret-json=1", b"".join(parts), "POST",
                            {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            for item in json.loads(raw or b"[]"):
                if isinstance(item, dict) and item.get("name") == name and item.get("id"):
                    return str(item["id"])
        except ValueError:
            pass
        return None


def norm(p: str) -> str:
    p = "/" + p.strip("/")
    return p if p != "//" else "/"


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def parse_mtime(s: str) -> float:
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    print(f"{ts} {msg}", flush=True)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            log(f"WARN state file {path} unreadable, starting fresh")
    return {}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_files(src: Path, exclude_names: set[str]) -> list[str]:
    """Relative paths of the files to consider: tracked + untracked-not-ignored (git decides
    what is secret-flagged), no dot-paths, no excluded names, no symlinks."""
    out = subprocess.run(["git", "-C", str(src), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         check=True, capture_output=True).stdout
    files = []
    for rel in out.decode("utf-8", "surrogateescape").split("\0"):
        if not rel:
            continue
        parts = rel.split("/")
        if any(p.startswith(".") for p in parts) or parts[-1] in exclude_names or ".." in parts:
            continue
        p = src / rel
        if p.is_symlink() or not p.is_file():
            continue
        files.append(rel)
    return files


def rel_of(full: str, root: str) -> str:
    return full[len(root):].lstrip("/") if root != "/" else full.lstrip("/")


def find_diverged(remote: dict[str, dict], root: str, src: Path, state: dict, guard_prefixes: list[str]) -> dict[str, str]:
    """Seafile files under a guarded prefix that this server did not produce: rel path -> reason.

    Missing locally, or Seafile's version is not the one we uploaded (remote id
    unknown or different) and is newer than the local copy.
    """
    out: dict[str, str] = {}
    for full, r in remote.items():
        if not any(under(full, norm(g)) for g in guard_prefixes):
            continue
        if root != "/" and not under(full, root):
            continue
        rel = rel_of(full, root)
        if not rel or ".." in rel.split("/"):
            continue
        local = src / rel
        if not local.exists():
            out[rel] = "missing on this server"
            continue
        prev = state.get(rel) or {}
        if prev.get("remote_id") and prev["remote_id"] == r.get("id"):
            continue  # exactly the version we uploaded
        try:
            local_mtime = local.stat().st_mtime
        except OSError:
            continue
        if parse_mtime(r.get("mtime", "")) > local_mtime + 1:
            out[rel] = "Seafile copy is newer and not ours"
    return out


def run_target(sf: Seafile, remote: dict[str, dict], target: dict, state_dir: Path, exclude_names: set[str],
               *, dry_run: bool, max_files: int | None, max_bytes: int, guard_prefixes: list[str],
               adopt_remote: bool = False) -> dict:
    name, src, root = target["name"], Path(target["src"]), norm(target["remote_root"])
    if any(under(root, bad) for bad in NEVER_PUSH):
        raise RuntimeError(f"remote_root {root} is inside a never-push folder")
    state_path = state_dir / f"{name}.json"
    state = load_state(state_path)
    files = local_files(src, exclude_names)

    if adopt_remote and not dry_run:
        adopted = 0
        for rel, prev in state.items():
            r = remote.get(posixpath.join(root, rel))
            if not r or prev.get("remote_id") or not r.get("id"):
                continue
            p = src / rel
            try:
                st = p.stat()
            except OSError:
                continue
            if prev.get("size") == st.st_size and abs(prev.get("mtime", 0) - st.st_mtime) < 1e-6:
                prev["remote_id"] = r["id"]
                adopted += 1
        save_state(state_path, state)
        log(f"[{name}] adopted the current Seafile version of {adopted} unchanged file(s) as our own")

    diverged = find_diverged(remote, root, src, state, guard_prefixes)
    for rel, why in sorted(diverged.items()):
        log(f"[{name}] DIVERGED {posixpath.join(root, rel)} ({why}); not overwritten, not imported")

    todo, in_sync, skipped_big, refused = [], 0, 0, 0
    for rel in files:
        full = posixpath.join(root, rel)
        if any(under(full, bad) for bad in NEVER_PUSH):
            refused += 1
            log(f"[{name}] REFUSED (never-push folder): {rel}")
            continue
        p = src / rel
        st = p.stat()
        if st.st_size > max_bytes:
            skipped_big += 1
            log(f"[{name}] SKIP too large ({st.st_size} bytes): {rel}")
            continue
        if rel in diverged:
            continue  # never overwrite a DIVERGED file; it was logged above
        prev = state.get(rel)
        if prev and prev.get("size") == st.st_size and abs(prev.get("mtime", 0) - st.st_mtime) < 1e-6:
            in_sync += 1  # unchanged since last run, no hashing needed
            continue
        digest = sha256(p)
        entry = dict(size=st.st_size, mtime=st.st_mtime, sha256=digest)
        if prev and prev.get("sha256") == digest:
            state[rel] = {**prev, **entry}  # touched, not changed (keep remote_id)
            in_sync += 1
            continue
        if prev is None:
            # First time we see this file: trust Seafile when it looks the same (seafile-pull.py set
            # the local mtime from Seafile's, so a local edit is newer and/or a different size).
            r = remote.get(full)
            if r and r.get("size") == st.st_size and parse_mtime(r.get("mtime", "")) + 1 >= st.st_mtime:
                state[rel] = dict(entry, remote_id=r.get("id")) if r.get("id") else entry
                in_sync += 1
                continue
        todo.append((rel, full, entry))
    if max_files is not None:
        todo = todo[:max_files]

    suffix = " (dry run)" if dry_run else ""
    log(f"[{name}] local files: {len(files)}, in sync: {in_sync}, to upload: {len(todo)}, "
        f"diverged: {len(diverged)}, refused: {refused}, too large: {skipped_big}{suffix}")
    uploaded = failed = 0
    t0 = time.time()
    for i, (rel, full, entry) in enumerate(todo, 1):
        if dry_run:
            log(f"[{name}] would upload {rel}")
            continue
        try:
            sf.ensure_dir(posixpath.dirname(full))
            new_id = sf.upload(posixpath.dirname(full), posixpath.basename(full), (src / rel).read_bytes())
            state[rel] = dict(entry, remote_id=new_id) if new_id else entry
            uploaded += 1
            log(f"[{name}] uploaded {rel}")
        except Exception as e:
            failed += 1
            log(f"[{name}] FAIL {rel}: {type(e).__name__}: {e}")
        if i % 100 == 0:
            save_state(state_path, state)
    if not dry_run:
        save_state(state_path, state)
        if todo:
            log(f"[{name}] uploaded {uploaded}, failed {failed}, {round(time.time() - t0)}s")
    return dict(target=name, files=len(files), in_sync=in_sync, uploaded=uploaded, failed=failed,
                refused=refused, too_large=skipped_big, diverged=len(diverged))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target", help="only this target name")
    ap.add_argument("--max-files", type=int)
    ap.add_argument("--adopt-remote", action="store_true",
                    help="once, by hand: record Seafile's current file ids as our own for unchanged files")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    token_file = Path(cfg["token_file"])
    if token_file.stat().st_mode & 0o077:
        log(f"ERROR {token_file} must be mode 600")
        return 2
    token = token_file.read_text().strip()
    if not token:
        log("ERROR empty token file")
        return 2
    sf = Seafile(cfg["seafile_url"], token)
    perm = sf.permission()
    if perm != "rw":
        log(f"ERROR token permission is {perm!r}, need read-write 'rw'")
        return 2
    state_dir = Path(cfg.get("state_dir", "/var/tmp/seafile-push"))
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / "lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0
        if age < 6 * 3600:
            log("another run holds the lock, exiting")
            return 0
        log("stale lock (>6h), taking over")
        fd = os.open(lock, os.O_CREAT | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    rc = 0
    try:
        remote = sf.listing()
        exclude_names = set(cfg.get("exclude_names", []))
        max_bytes = int(float(cfg.get("max_file_mb", 90)) * 1024 * 1024)
        guard_prefixes = [norm(p) for p in cfg.get("guard_prefixes", ["/03-diary"])]
        for target in cfg["targets"]:
            if args.target and target["name"] != args.target:
                continue
            try:
                res = run_target(sf, remote, target, state_dir, exclude_names, dry_run=args.dry_run,
                                 max_files=args.max_files, max_bytes=max_bytes, guard_prefixes=guard_prefixes,
                                 adopt_remote=args.adopt_remote)
                if res["failed"]:
                    rc = 1
            except Exception as e:
                log(f"[{target['name']}] ERROR {type(e).__name__}: {e}")
                rc = 1
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    log(f"done rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
