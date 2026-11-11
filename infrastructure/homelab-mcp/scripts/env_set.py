#!/usr/bin/env python3
"""Set KEY=VALUE lines from stdin in the repo's .env without printing any value.

    printf 'HOMELAB_MCP_JWT_SIGNING_KEY=%s\\n' "$(openssl rand -hex 32)" \\
      | python3 infrastructure/homelab-mcp/scripts/env_set.py --if-missing

- Backs .env up first (.env.bak-YYYYmmdd-HHMMSS, mode 600), once per run.
- Replaces an existing KEY= line (and drops duplicates of it) or appends one.
- --if-missing leaves a key alone when it already has a non-empty value.
- Values with spaces or '#' are single-quoted so docker compose reads them whole.
- Prints only key names and what happened; never values.
Standard library only.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def fmt(value: str) -> str:
    if "'" in value:
        raise ValueError("values can't contain a single quote")
    return f"'{value}'" if re.search(r"[\s#\"$`\\]", value) else value


def current(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=".env")
    ap.add_argument("--if-missing", action="store_true")
    args = ap.parse_args(argv)

    updates: dict[str, str] = {}
    for n, line in enumerate(sys.stdin.read().splitlines(), 1):
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep or not KEY_RE.match(key):
            print(f"line {n}: not KEY=VALUE (nothing changed)", file=sys.stderr)
            return 2
        if not value:
            print(f"{key}: empty value (nothing changed)", file=sys.stderr)
            return 2
        try:
            updates[key] = fmt(value)
        except ValueError as e:
            print(f"{key}: {e} (nothing changed)", file=sys.stderr)
            return 2
    if not updates:
        print("no KEY=VALUE lines on stdin", file=sys.stderr)
        return 2

    path = Path(args.file)
    lines = path.read_text().splitlines() if path.exists() else []
    out: list[str] = []
    seen: dict[str, str] = {}
    for line in lines:
        m = LINE_RE.match(line)
        if m and m.group(1) in updates:
            key = m.group(1)
            if key in seen:
                continue  # drop duplicates; the first occurrence gets the value
            if args.if_missing and current(m.group(2)):
                seen[key] = "kept"
                out.append(line)
            else:
                seen[key] = "set"
                out.append(f"{key}={updates[key]}")
            continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            seen[key] = "added"
            out.append(f"{key}={value}")

    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
        mode = path.stat().st_mode & 0o777
    else:
        backup, mode = None, 0o600
    fd, tmp = tempfile.mkstemp(dir=str(path.parent or "."), prefix=".env.tmp-")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    for key in updates:
        print(f"{key}: {seen[key]}")
    if backup:
        print(f"backup: {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
