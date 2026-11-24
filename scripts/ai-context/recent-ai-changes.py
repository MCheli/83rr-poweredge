#!/usr/bin/env python3
"""recent-ai-changes.py: write the "Recently changed by AI" map note from basic-memory's change log.

basic-memory records every note written or edited through its tools in the
table `accepted_project_note_change` of its SQLite database (`accepted_at` in
UTC, `operation`, `file_path`, `title`, `source`). This script reads that table
read-only (sqlite URI `mode=ro`), keeps the rows of the last N days, groups
them by local day (America/New_York, newest first), collapses repeated writes
of one note on one day into a single line with a count, and writes the result
as one note through basic-memory itself (`bm_write` with `overwrite`, via
`bm.py` next to this file). The note's own writes are skipped from the listing.

    python3 scripts/ai-context/recent-ai-changes.py --dry-run     # print the note, write nothing
    python3 scripts/ai-context/recent-ai-changes.py               # write maps/Recently changed by AI.md
    # cron (deploy user): 7 * * * *  -> /data/ai-context/logs/recent-ai-changes.log

Every line of the note is "- HH:MM [[Note title]] (operation)" under a "## YYYY-MM-DD"
heading; the link is the note's title from the `entity` table when the title is
the file name, otherwise `[[path/without/.md|title]]` so Obsidian resolves it.
At most --max-lines entry lines are written (default 300), newest first.

Environment:
    BM_URL        basic-memory MCP endpoint. Unset: resolved from the running
                  `basic-memory` container (`docker inspect`) as http://<ip>:8000/mcp,
                  which is how the cron job on the server reaches it.
    BM_PROJECT    basic-memory project (default main); also selects the rows.
    BM_TIMEOUT    seconds per HTTP request (default 120)

Standard library only (Python 3.9+, zoneinfo). Nothing personal is in this
file: the database path, note path and vault layout are arguments.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
DEFAULT_DB = "/data/ai-context/state/basic-memory/config/memory.db"
DEFAULT_NOTE = "maps/Recently changed by AI.md"
DEFAULT_TZ = "America/New_York"
UTC = dt.timezone.utc


def log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S%z')} {msg}", flush=True)


def load_bm(path: Path):
    """Import bm.py (the MCP client) from a file path, without needing a package."""
    spec = importlib.util.spec_from_file_location("bm", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import bm.py from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def resolve_bm_url(container: str) -> str:
    """BM_URL from the environment, else the container's first network IP."""
    url = os.environ.get("BM_URL")
    if url:
        return url
    docker = shutil.which("docker") or "/usr/bin/docker"
    fmt = "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"
    proc = subprocess.run([docker, "inspect", "-f", fmt, container], capture_output=True, text=True, timeout=30)
    ips = proc.stdout.split()
    if proc.returncode != 0 or not ips:
        raise SystemExit(f"BM_URL unset and docker inspect {container} gave no IP: {proc.stderr.strip()}")
    return f"http://{ips[0]}:8000/mcp"


def parse_utc(value: str) -> dt.datetime:
    """accepted_at is stored as a naive UTC timestamp ('YYYY-MM-DD HH:MM:SS[.ffffff]')."""
    text = value.replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    ts = dt.datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def fetch_changes(db_path: str, project: str | None, days: int, skip_path: str) -> list[dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        project_id = None
        if project:
            try:
                row = con.execute("select id from project where name = ?", (project,)).fetchone()
                project_id = row["id"] if row else None
            except sqlite3.Error:
                project_id = None
        since = (dt.datetime.now(UTC) - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        sql = (
            "select c.accepted_at, c.operation, c.file_path, c.title as change_title, e.title as entity_title "
            "from accepted_project_note_change c left join entity e on e.id = c.entity_id "
            "where c.accepted_at >= ?"
        )
        params: list = [since]
        if project_id is not None:
            sql += " and c.project_id = ?"
            params.append(project_id)
        sql += " order by c.accepted_at desc"
        rows = []
        for r in con.execute(sql, params):
            if r["file_path"] == skip_path:
                continue
            rows.append(
                {
                    "at": parse_utc(r["accepted_at"]),
                    "operation": r["operation"] or "changed",
                    "file_path": r["file_path"],
                    "title": r["entity_title"] or r["change_title"] or Path(r["file_path"]).stem,
                }
            )
        return rows
    finally:
        con.close()


def link_for(file_path: str, title: str) -> str:
    """[[Title]] when the file is named after it, else [[path|Title]] so Obsidian resolves it."""
    stem = Path(file_path).stem
    if stem == title:
        return f"[[{title}]]"
    return f"[[{file_path[:-3] if file_path.endswith('.md') else file_path}|{title}]]"


def build_note(rows: list[dict], tz: ZoneInfo, days: int, max_lines: int, now: dt.datetime) -> tuple[str, int, int]:
    """Return (markdown, entry lines written, changes counted)."""
    by_day: dict[dt.date, dict[str, dict]] = collections.OrderedDict()
    for r in rows:  # rows are newest first
        local = r["at"].astimezone(tz)
        day = by_day.setdefault(local.date(), {})
        entry = day.get(r["file_path"])
        if entry is None:
            day[r["file_path"]] = {
                "latest": local,
                "count": 1,
                "ops": [r["operation"]],
                "title": r["title"],
                "file_path": r["file_path"],
            }
        else:
            entry["count"] += 1
            if r["operation"] not in entry["ops"]:
                entry["ops"].append(r["operation"])

    total = len(rows)
    lines: list[str] = []
    written = 0
    truncated = 0
    for day in sorted(by_day, reverse=True):
        entries = sorted(by_day[day].values(), key=lambda e: e["latest"], reverse=True)
        n_changes = sum(e["count"] for e in entries)
        if written >= max_lines:
            truncated += len(entries)
            continue
        weekday = day.strftime("%A")
        lines.append("")
        lines.append(f"## {day.isoformat()} ({weekday}): {n_changes} change{'s' if n_changes != 1 else ''}, {len(entries)} note{'s' if len(entries) != 1 else ''}")
        for e in entries:
            if written >= max_lines:
                truncated += 1
                continue
            ops = ", ".join(e["ops"])
            count = f", {e['count']}×" if e["count"] > 1 else ""
            lines.append(f"- {e['latest'].strftime('%H:%M')} {link_for(e['file_path'], e['title'])} ({ops}{count})")
            written += 1
    if truncated:
        lines.append("")
        lines.append(f"- … {truncated} older note{'s' if truncated != 1 else ''} not shown (cap {max_lines} lines)")

    today = now.astimezone(tz).date().isoformat()
    stamp = now.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
    head = [
        "---",
        "title: Recently changed by AI",
        "type: map",
        "tags:",
        "  - map/ai-changes",
        f"updated: {today}",
        "source: derived",
        "---",
        "",
        "# Recently changed by AI",
        "",
        f"Notes written or edited through basic-memory in the last {days} days, from its change log "
        f"(`accepted_project_note_change`), grouped by day in {tz.key}, newest first. Repeated writes of one "
        "note on one day are one line with a count; this note's own writes are not listed. Regenerated every "
        f"hour by `recent-ai-changes.py`; last run {stamp}, {total} changes across "
        f"{sum(len(d) for d in by_day.values())} note-days.",
    ]
    if not rows:
        lines = ["", "No changes recorded in this window."]
    return "\n".join(head + lines) + "\n", written, total


def write_note(bm, url: str, project: str | None, note_path: str, content: str, timeout: float) -> dict:
    client = bm.McpClient(url, timeout=timeout, transport="auto")
    try:
        client.initialize()
        tool = client.pick_tool("write")
        arguments = {"identifier": note_path, "content": content, "overwrite": True, "output_format": "json"}
        if project:
            arguments["project"] = project
        result = client.call_tool(tool, arguments)
        shaped = bm.shape_result(result)
        if result.get("isError"):
            raise SystemExit(f"bm_write failed: {shaped}")
        return shaped if isinstance(shaped, dict) else {"result": shaped}
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DEFAULT_DB, help="basic-memory SQLite database (opened read-only)")
    p.add_argument("--days", type=int, default=7, help="window in days (default 7)")
    p.add_argument("--note-path", default=DEFAULT_NOTE, help="vault path of the note to write")
    p.add_argument("--max-lines", type=int, default=300, help="cap on entry lines (default 300)")
    p.add_argument("--tz", default=DEFAULT_TZ, help="time zone for grouping (default America/New_York)")
    p.add_argument("--bm", default=str(HERE / "bm.py"), help="path to bm.py (default: next to this script)")
    p.add_argument("--container", default="basic-memory", help="container whose IP gives BM_URL when unset")
    p.add_argument("--project", default=os.environ.get("BM_PROJECT", "main"), help="basic-memory project ('' to omit)")
    p.add_argument("--dry-run", action="store_true", help="print the note to stdout, write nothing")
    args = p.parse_args(argv)
    project = args.project or None

    tz = ZoneInfo(args.tz)
    now = dt.datetime.now(UTC)
    rows = fetch_changes(args.db, project, args.days, args.note_path)
    content, written, total = build_note(rows, tz, args.days, args.max_lines, now)
    if args.dry_run:
        sys.stdout.write(content)
        return 0

    bm = load_bm(Path(args.bm))
    url = resolve_bm_url(args.container)
    timeout = float(os.environ.get("BM_TIMEOUT", "120"))
    try:
        result = write_note(bm, url, project, args.note_path, content, timeout)
    except (bm.McpError, SystemExit, OSError) as exc:
        log(f"FAIL {args.note_path}: {exc}")
        return 1
    log(f"wrote {args.note_path}: {total} changes in {args.days} days, {written} lines, checksum {str(result.get('checksum', ''))[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
