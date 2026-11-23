"""Read-only bridge to basic-memory, the MCP server over Mark's AI Context notes.

basic-memory (container `basic-memory`, infrastructure/ai-context) indexes a
plain-Markdown mirror of the AI Context library and serves it over streamable
HTTP on the internal Docker network, with no auth of its own. Its 1.0.0 image
also has write tools (bm_write, bm_edit, bm_delete, bm_move, project create)
and no switch to hide them, so this module is the ONLY path from homelab-mcp
to it and it forwards exactly the tools in UPSTREAM_TOOLS: NotesBridge.call()
refuses every other name before anything is sent, drops the project-selection
arguments a caller might pass, and pins `project` (and, for bm_project, the
`command`) itself. Writes are turned on at the AI Context cut-over, later.

Each call opens its own short MCP session (initialize, one tools/call, close):
a few milliseconds on the Docker network, and nothing to reconnect when
basic-memory restarts. Calls time out well under Cloudflare's 100 s limit.
Nothing here logs queries, identifiers or note text.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

log = logging.getLogger("homelab-mcp.notes")

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

# basic-memory tool -> arguments this bridge always sets (after the caller's).
# Everything not listed here (bm_write, bm_edit, bm_delete, bm_move, bm_schema,
# bm_man, bm_project list/create) can't be called through homelab-mcp.
UPSTREAM_TOOLS: dict[str, dict] = {
    "bm_search": {},
    "bm_read": {},
    "bm_list": {},
    "bm_find": {},
    "bm_context": {},
    "bm_project": {"command": "recent"},  # the read-only command; list/create never
}
# Caller-supplied arguments that choose a project or widen the scope are dropped.
SCOPE_ARGS = frozenset({"project", "projects", "all_projects", "workspace", "command"})


class NotesError(Exception):
    """basic-memory couldn't be reached, refused the call, or the tool isn't allowed."""


class NotesBridge:
    def __init__(self, target: str | FastMCP, *, project: str = "main", timeout: float = 30.0):
        if isinstance(target, str) and not target.startswith(("http://", "https://")):
            raise ValueError("NOTES_MCP_URL must be an http(s) URL, e.g. http://basic-memory:8000/mcp")
        if not project.strip():
            raise ValueError("NOTES_PROJECT must not be empty")
        if not 0 < timeout < 100:
            raise ValueError("NOTES_TIMEOUT must be under 100 s (Cloudflare's limit)")
        self.target = target  # URL, or a FastMCP instance in tests (in-memory transport)
        self.project = project
        self.timeout = timeout

    def _client(self) -> Client:
        return Client(self.target, timeout=self.timeout, init_timeout=min(self.timeout, 10.0))

    def prepare(self, tool: str, args: dict) -> dict:
        """The exact arguments sent upstream, or NotesError if `tool` isn't allowed."""
        if tool not in UPSTREAM_TOOLS:
            raise NotesError(f"{tool} isn't available through this connector (read-only notes tools only).")
        clean = {k: v for k, v in args.items() if v is not None and k not in SCOPE_ARGS}
        clean.update(UPSTREAM_TOOLS[tool])
        clean["project"] = self.project
        return clean

    async def call(self, tool: str, args: dict) -> str:
        sent = self.prepare(tool, args)  # allowlist check happens before any I/O
        try:
            async with self._client() as client:
                result = await client.call_tool(tool, sent, raise_on_error=True)
        except ToolError as e:
            # basic-memory's own message (e.g. "Note not found"); no secrets in it.
            raise NotesError(f"basic-memory: {e}") from e
        except TimeoutError as e:
            raise NotesError(f"basic-memory didn't answer within {int(self.timeout)} s.") from e
        except Exception as e:  # connect refused, DNS, protocol errors, ...
            log.warning("basic-memory unreachable (%s)", type(e).__name__)
            raise NotesError("The notes server (basic-memory) isn't reachable right now. "
                             "The Seafile tools still work; try the notes again in a minute.") from e
        return render(result.content)

    async def probe(self) -> list[str]:
        """Names of the tools basic-memory offers (startup check, logs only)."""
        try:
            async with self._client() as client:
                return sorted(t.name for t in await client.list_tools())
        except Exception as e:
            raise NotesError(f"basic-memory isn't reachable ({type(e).__name__})") from e


def render(content) -> str:
    parts = []
    for block in content or []:
        text = getattr(block, "text", None)
        parts.append(text if isinstance(text, str) else f"[{getattr(block, 'type', 'binary')} content omitted]")
    return "\n".join(parts)


NOTES_INSTRUCTIONS = """\
 The notes_* tools reach the same AI Context notes through basic-memory, a \
ranked full-text index of the Markdown mirror: notes_search for ranked retrieval \
or grep-like matching lines, notes_read for one note (whole, a section or a line \
range), notes_list and notes_find for folders and file names, notes_context to \
follow the [[links]] between notes, notes_recent for what changed lately. Paths \
are relative to the notes root (e.g. "03-diary/2026-11-10.md"). They are \
read-only; notes can't be written from here.\
"""

OutputFormat = Literal["text", "json"]


def register_notes_tools(mcp: FastMCP, bridge: NotesBridge | None) -> list[str]:
    """Add the notes_* tools to `mcp` when a bridge is configured. Returns their names."""
    if bridge is None:
        return []

    async def forward(tool: str, **args) -> str:
        try:
            return await bridge.call(tool, args)
        except NotesError as e:
            raise ToolError(str(e)) from e

    async def notes_search(
        query: str | None = None,
        mode: Literal["hybrid", "text", "semantic", "title", "permalink"] | None = None,
        path: str | None = None,
        since: str | None = None,
        lines: int | None = None,
        max_matches: int = 10,
        filters: dict | None = None,
        note_types: list[str] | None = None,
        identifier: str | None = None,
        compact: bool = False,
        page: int = 1,
        page_size: int = 10,
        output_format: OutputFormat = "text",
    ) -> str:
        """Search Mark's notes, ranked by relevance.

        query supports quoted phrases, AND/OR/NOT and tag:name; omit it to search by
        filters alone. mode: text, title or permalink (globs with *); hybrid/semantic
        when available. lines (0-10) returns each hit's matching lines with that much
        context, like grep, instead of an excerpt. path limits the search to a folder
        (e.g. "03-diary"); identifier searches one note; since like "7d" or a date.
        """
        return await forward("bm_search", query=query, mode=mode, path=path, since=since, lines=lines,
                             max_matches=max_matches, filters=filters, note_types=note_types,
                             identifier=identifier, compact=compact, page=page, page_size=page_size,
                             output_format=output_format)

    async def notes_read(
        identifier: str,
        section: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        max_tokens: int | None = None,
        include_frontmatter: bool = True,
        include_content: bool = True,
        output_format: OutputFormat = "text",
    ) -> str:
        """Read one note by path ("02-systems/mac-mini.md"), permalink, memory:// URL or exact title.

        Slice a long note with section (a heading, "Auth/Decisions" for one under
        "Auth"), start_line/end_line, or max_tokens (cut at a section or paragraph
        boundary; the result says where to continue). include_content=false returns
        only the metadata. A missing note is an error: find it with notes_search.
        """
        return await forward("bm_read", identifier=identifier, section=section, start_line=start_line,
                             end_line=end_line, max_tokens=max_tokens, include_frontmatter=include_frontmatter,
                             include_content=include_content, output_format=output_format)

    async def notes_list(
        path: str = "/",
        glob: str | None = None,
        sort: Literal["title_asc", "title_desc", "updated_asc", "updated_desc"] | None = None,
        page: int = 1,
        page_size: int = 10,
        output_format: OutputFormat = "text",
    ) -> str:
        """List one folder of the notes: subfolders, then files with title, date and id.

        "/" is the notes root. glob filters file names ("*.md", "*meeting*"); sort
        orders them. For a recursive search by name or front matter use notes_find.
        """
        return await forward("bm_list", path=path, glob=glob, sort=sort, page=page, page_size=page_size,
                             output_format=output_format)

    async def notes_find(
        path: str = "/",
        name: str | None = None,
        filters: dict | None = None,
        fields: list[str] | None = None,
        depth: int = 10,
        page: int = 1,
        page_size: int = 10,
        output_format: OutputFormat = "text",
    ) -> str:
        """Find notes recursively under a folder by file-name glob or front-matter filters.

        name is a glob ("2026-11-*.md"); filters match front matter, e.g.
        {"status": "active"} (not together with name); fields returns just those
        front-matter values per note (needs filters). depth: folder levels (1-10).
        """
        return await forward("bm_find", path=path, name=name, filters=filters, fields=fields, depth=depth,
                             page=page, page_size=page_size, output_format=output_format)

    async def notes_context(
        identifier: str,
        depth: int = 1,
        since: str = "7d",
        max_related: int = 10,
        compact: bool = False,
        page: int = 1,
        page_size: int = 10,
        output_format: OutputFormat = "json",
    ) -> str:
        """Follow the links from a note: the note, its observations and the notes its
        relations reach, up to depth hops (1-5). identifier is a path, permalink,
        memory:// URL or a pattern like "02-systems/*". since limits related results to
        recent changes. compact returns the graph shape without note bodies.
        """
        return await forward("bm_context", identifier=identifier, depth=depth, since=since,
                             max_related=max_related, compact=compact, page=page, page_size=page_size,
                             output_format=output_format)

    async def notes_recent(
        since: str = "7d",
        items: list[Literal["note", "observation", "relation"]] | None = None,
        page: int = 1,
        page_size: int = 10,
        output_format: OutputFormat = "text",
    ) -> str:
        """What changed in the notes lately. since: "7d", "24h", "2 days ago", "last week"
        or a date. items: notes (default), observations, relations, or a mix.
        """
        return await forward("bm_project", since=since, items=items, page=page, page_size=page_size,
                             output_format=output_format)

    tools = [notes_search, notes_read, notes_list, notes_find, notes_context, notes_recent]
    for fn in tools:
        mcp.tool(fn, annotations=READ_ONLY)
    return [fn.__name__ for fn in tools]
