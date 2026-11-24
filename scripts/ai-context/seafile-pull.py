#!/usr/bin/env python3
"""Pull a Seafile library (or parts of it) into local folders, read-only.

One-way mirror from Seafile to disk using a *library API token* with Read-Only
permission (Seafile 11+: library > Settings > API Token). Designed for a cron
job: it lists the library once, downloads only files whose Seafile file id
changed since the last run, never deletes anything locally, and never writes
to Seafile (GET requests only; it refuses to run with an rw token).

Config is a JSON file (see scripts/ai-context/README.md):

{
  "seafile_url": "https://files.example.com",
  "token_file": "/data/ai-context/.secrets/seafile-token",
  "state_dir": "/data/ai-context/state",
  "workers": 6,
  "exclude_names": ["some-file.md"],
  "targets": [
    {"name": "notes", "dest": "/data/ai-context/notes", "remote_root": "/",
     "include": ["README.md", "01-about-me"], "exclude": ["04-work"]},
    {"name": "raw", "dest": "/data/ai-context/raw", "remote_root": "/05-raw",
     "include": ["*"], "exclude": ["work-laptop"]}
  ]
}

- include: top-level entries under remote_root to mirror ("*" = everything)
- exclude: paths relative to remote_root that are never listed or fetched
- exclude_names: bare file names that are never fetched, anywhere
- redact_names (per target, optional): true keeps file names out of every log
  line of that target (FAIL/CONFLICT lines say "<redacted>"); counts only
- dir_mode (per target, optional): octal string such as "775", applied to
  dest and every folder under it after each run (cron's umask is often 022)
- A local file is only replaced when Seafile's copy changed (by file id).
  If it was edited locally as well, Seafile still wins during the trial and a
  CONFLICT line is logged; git history keeps the local edit recoverable.
- Nothing is ever deleted locally.

Usage: seafile-pull.py --config /data/ai-context/pull-config.json [--dry-run]
       [--target notes] [--max-files N]
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

API = "/api/v2.1/via-repo-token/"


class Seafile:
    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        # Cloudflare's WAF answers 403 to urllib's default User-Agent
        self.headers = dict(Authorization=f"Token {token}", Accept="application/json")
        self.headers["User-Agent"] = "seafile-pull/1.0 (+homelab cron)"
        self.timeout = timeout

    def _get(self, url: str, with_auth: bool = True, retries: int = 4):
        last = None
        for attempt in range(retries):
            try:
                hdrs = dict(self.headers)
                if not with_auth:
                    del hdrs["Authorization"]
                req = urllib.request.Request(url, headers=hdrs)
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
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"GET failed after {retries} tries: {type(last).__name__}: {last}")

    def api(self, endpoint: str, **params):
        q = urllib.parse.urlencode(params)
        return json.loads(self._get(f"{self.base}{API}{endpoint}?{q}"))

    def download(self, path: str) -> bytes:
        link = self.api("download-link/", path=path)
        if not isinstance(link, str):
            raise RuntimeError("unexpected download-link response")
        parts = urllib.parse.urlsplit(link)
        # Rewrite to our base URL in case Seafile built the link for another host
        url = self.base + parts.path + (f"?{parts.query}" if parts.query else "")
        return self._get(url, with_auth=False)


def parse_mtime(s: str) -> float:
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time()


def norm(p: str) -> str:
    p = "/" + p.strip("/")
    return p if p != "//" else "/"


def under(path: str, prefix: str) -> bool:
    return prefix != "/" and (path == prefix or path.startswith(prefix + "/"))


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    print(f"{ts} {msg}", flush=True)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            log(f"WARN state file {path} unreadable, starting fresh")
    return dict()


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    os.replace(tmp, path)


def plan_target(sf: Seafile, target: dict, exclude_names: set[str]) -> list[dict]:
    root = norm(target["remote_root"])
    include = target.get("include") or ["*"]
    excludes = [norm(posixpath.join(root, e)) for e in target.get("exclude", [])]
    data = sf.api("dir/", path=root, recursive="1")
    wanted = []
    for item in data.get("dirent_list", []):
        if item.get("type") != "file":
            continue
        name = item.get("name", "")
        parent = norm(item.get("parent_dir") or root)
        full = posixpath.join(parent, name)
        rel = full[len(root):].lstrip("/") if root != "/" else full.lstrip("/")
        top = rel.split("/", 1)[0]
        if "*" not in include and top not in include:
            continue
        if any(under(full, ex) for ex in excludes):
            continue
        if name in exclude_names:
            continue
        if ".." in rel.split("/") or not rel:
            continue
        wanted.append(dict(remote=full, rel=rel, id=item.get("id"), mtime=item.get("mtime", ""),
                           size=item.get("size")))
    return wanted


def fetch_one(sf: Seafile, dest: Path, f: dict) -> tuple[str, str]:
    local = dest / f["rel"]
    local.parent.mkdir(parents=True, exist_ok=True)
    data = sf.download(f["remote"])
    fd, tmpname = tempfile.mkstemp(prefix=".pull-", dir=str(local.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        mt = parse_mtime(f["mtime"])
        os.utime(tmpname, (mt, mt))
        os.chmod(tmpname, 0o644)
        os.replace(tmpname, local)
    except Exception:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise
    return f["rel"], f["id"]


def run_target(sf: Seafile, target: dict, state_dir: Path, exclude_names: set[str], *,
               dry_run: bool, workers: int, max_files: int | None) -> dict:
    name = target["name"]
    dest = Path(target["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{name}.json"
    state = load_state(state_path)
    wanted = plan_target(sf, target, exclude_names)
    shown = (lambda rel: "<redacted>") if target.get("redact_names") else (lambda rel: rel)

    todo, unchanged = [], 0
    for f in wanted:
        prev = state.get(f["rel"])
        local = dest / f["rel"]
        if prev and prev.get("id") == f["id"] and local.exists():
            unchanged += 1
            continue
        if prev and prev.get("id") != f["id"] and local.exists():
            try:
                if local.stat().st_mtime > parse_mtime(prev.get("mtime", "")) + 1:
                    log(f"[{name}] CONFLICT local edit overwritten by Seafile: {shown(f['rel'])}")
            except OSError:
                pass
        todo.append(f)
    if max_files is not None:
        todo = todo[:max_files]

    n_wanted, n_todo = len(wanted), len(todo)
    suffix = " (dry run)" if dry_run else ""
    log(f"[{name}] remote files in scope: {n_wanted}, unchanged: {unchanged}, to fetch: {n_todo}{suffix}")
    fetched = failed = 0
    if not dry_run and todo:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = dict((ex.submit(fetch_one, sf, dest, f), f) for f in todo)
            done_since_save = 0
            for fut in as_completed(futs):
                f = futs[fut]
                try:
                    rel, fid = fut.result()
                    state[rel] = dict(id=fid, mtime=f["mtime"], size=f["size"])
                    fetched += 1
                    done_since_save += 1
                    if done_since_save >= 200:
                        save_state(state_path, state)
                        done_since_save = 0
                        log(f"[{name}] progress {fetched}/{n_todo}")
                except Exception as e:
                    failed += 1
                    # The exception text can carry the remote path (download URLs, FileNotFoundError)
                    detail = type(e).__name__ if target.get("redact_names") else f"{type(e).__name__}: {e}"
                    log(f"[{name}] FAIL {shown(f['rel'])}: {detail}")
        save_state(state_path, state)
        elapsed = round(time.time() - t0)
        log(f"[{name}] fetched {fetched}, failed {failed}, {elapsed}s")
    if not dry_run and target.get("dir_mode"):
        mode = int(target["dir_mode"], 8)
        os.chmod(dest, mode)
        for parent, dirs, _ in os.walk(dest):
            for d in dirs:
                os.chmod(os.path.join(parent, d), mode)
    return dict(target=name, in_scope=n_wanted, unchanged=unchanged, fetched=fetched, failed=failed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target", help="only this target name")
    ap.add_argument("--max-files", type=int)
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    token = Path(cfg["token_file"]).read_text().strip()
    if not token:
        log("ERROR empty token file")
        return 2
    sf = Seafile(cfg["seafile_url"], token)
    # Refuse anything but a read-only library token (the recursive listing
    # omits user_perm, so check it on the plain root listing).
    perm = sf.api("dir/", path="/").get("user_perm")
    if perm != "r":
        log(f"ERROR token permission is {perm!r}, refusing (need read-only 'r')")
        return 2
    state_dir = Path(cfg.get("state_dir", "/var/tmp/seafile-pull"))
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
        exclude_names = set(cfg.get("exclude_names", []))
        for target in cfg["targets"]:
            if args.target and target["name"] != args.target:
                continue
            try:
                res = run_target(sf, target, state_dir, exclude_names, dry_run=args.dry_run,
                                 workers=int(cfg.get("workers", 6)), max_files=args.max_files)
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
