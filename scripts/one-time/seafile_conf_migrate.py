#!/usr/bin/env python3
"""Seafile config migration for the 11.0 -> 12.0 -> 13.0 Docker upgrade.

Edits seahub_settings.py and seafile.conf in the Seafile conf dir
(/storage/seafile/seafile/conf on the host) for one upgrade hop. Shows a diff
and changes nothing unless --apply is given. With --apply, each changed file
is first copied to <file>.pre-<step>. Idempotent: re-running a step is a no-op.

  --step 12  (before starting the 12.0 image)
    seahub_settings.py: drop SERVICE_URL and FILE_SERVER_ROOT (removed in
                        12.0; now derived from SEAFILE_SERVER_PROTOCOL/HOSTNAME)
    seafile.conf:       [notification] host -> seafile-notification (the
                        notification server moved to its own container)

  --step 13  (before starting the 13.0 image)
    seahub_settings.py: drop DATABASES, CACHES, COMPRESS_CACHE_BACKEND and
                        NOTIFICATION_SERVER_URL (now SEAFILE_MYSQL_DB_*,
                        CACHE_PROVIDER/REDIS_*, NOTIFICATION_SERVER_URL env)
    seafile.conf:       drop [database] and [notification] (now env)

Usage (on the server, as root because the conf dir is root-owned):
  sudo python3 scripts/one-time/seafile_conf_migrate.py --step 12
  sudo python3 scripts/one-time/seafile_conf_migrate.py --step 12 --apply

Never prints secret values: the diff masks password/key/secret lines.
"""

import argparse
import difflib
import re
import shutil
import sys
from pathlib import Path

DEFAULT_CONF_DIR = "/storage/seafile/seafile/conf"
SECRET_RE = re.compile(r"(password|passwd|secret|key)", re.IGNORECASE)


def drop_assignment(text, name):
    """Remove a top-level `NAME = ...` statement, including a multi-line {...} block."""
    lines = text.splitlines(keepends=True)
    out, i = [], 0
    pat = re.compile(rf"^{re.escape(name)}\s*=")
    while i < len(lines):
        if pat.match(lines[i]):
            depth = lines[i].count("{") - lines[i].count("}")
            i += 1
            while depth > 0 and i < len(lines):
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def drop_section(text, section):
    """Remove an INI [section] and its body, up to the next section header."""
    lines = text.splitlines(keepends=True)
    out, skipping = [], False
    for line in lines:
        header = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if header:
            skipping = header.group(1).strip().lower() == section.lower()
        if not skipping:
            out.append(line)
    return "".join(out)


def set_option(text, section, key, value):
    """Set `key = value` inside [section] (the section must exist)."""
    lines = text.splitlines(keepends=True)
    out, in_section, done = [], False, False
    for line in lines:
        header = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if header:
            if in_section and not done:
                out.append(f"{key} = {value}\n")
                done = True
            in_section = header.group(1).strip().lower() == section.lower()
        elif in_section and re.match(rf"^\s*{re.escape(key)}\s*=", line):
            line = f"{key} = {value}\n"
            done = True
        out.append(line)
    if in_section and not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key} = {value}\n")
        done = True
    if not done:
        raise SystemExit(f"[{section}] not found; refusing to guess")
    return "".join(out)


def migrate(step, seahub, seafile_conf):
    if step == 12:
        for name in ("SERVICE_URL", "FILE_SERVER_ROOT"):
            seahub = drop_assignment(seahub, name)
        if re.search(r"^\s*\[notification\]", seafile_conf, re.MULTILINE | re.IGNORECASE):
            seafile_conf = set_option(seafile_conf, "notification", "host", "seafile-notification")
    elif step == 13:
        for name in ("DATABASES", "CACHES", "COMPRESS_CACHE_BACKEND", "NOTIFICATION_SERVER_URL"):
            seahub = drop_assignment(seahub, name)
        for section in ("database", "notification"):
            seafile_conf = drop_section(seafile_conf, section)
    return seahub, seafile_conf


def masked(lines):
    return [re.sub(r"(=\s*|:\s*).*", r"\1<masked>", l) if SECRET_RE.search(l) else l for l in lines]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=int, choices=(12, 13), required=True)
    ap.add_argument("--conf-dir", default=DEFAULT_CONF_DIR)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: show diff only)")
    args = ap.parse_args()

    conf = Path(args.conf_dir)
    files = {"seahub_settings.py": conf / "seahub_settings.py", "seafile.conf": conf / "seafile.conf"}
    for p in files.values():
        if not p.is_file():
            sys.exit(f"missing {p}")

    old = {k: p.read_text() for k, p in files.items()}
    new = dict(zip(old, migrate(args.step, old["seahub_settings.py"], old["seafile.conf"])))

    changed = [k for k in old if old[k] != new[k]]
    for k in changed:
        sys.stdout.writelines(difflib.unified_diff(
            masked(old[k].splitlines(keepends=True)), masked(new[k].splitlines(keepends=True)),
            fromfile=f"{k} (current)", tofile=f"{k} (step {args.step})"))
    if not changed:
        print(f"step {args.step}: nothing to change (already migrated)")
        return
    if not args.apply:
        print(f"\nDry run. Re-run with --apply to write {', '.join(changed)}.")
        return
    for k in changed:
        backup = files[k].with_name(f"{files[k].name}.pre-{args.step}")
        shutil.copy2(files[k], backup)
        files[k].write_text(new[k])
        print(f"wrote {files[k]} (previous copy: {backup.name})")


if __name__ == "__main__":
    main()
