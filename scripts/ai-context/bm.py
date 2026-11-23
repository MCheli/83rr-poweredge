#!/usr/bin/env python3
"""bm.py: a small command-line client for basic-memory's MCP server.

Talks streamable HTTP MCP (JSON-RPC over POST, SSE or JSON responses) with the
Python standard library only, so Claude Code sessions and cron jobs can script
note reads and writes without an MCP host. Nothing here is specific to one
vault: the server URL, project name and every note identifier are arguments.

    python3 scripts/ai-context/bm.py tools                 # names + input schemas
    python3 scripts/ai-context/bm.py read README.md
    python3 scripts/ai-context/bm.py search "some words"
    python3 scripts/ai-context/bm.py context some/note
    python3 scripts/ai-context/bm.py write --title T --folder F --content-file body.md
    python3 scripts/ai-context/bm.py edit some/note --operation append --content-file more.md
    python3 scripts/ai-context/bm.py call bm_read '{"identifier": "README.md"}'

Environment:
    BM_URL        MCP endpoint (default https://memory.ops.markcheli.com/mcp)
    BM_PROJECT    project name passed to every tool (default main)
    BM_TIMEOUT    seconds per HTTP request (default 120)
    BM_TRANSPORT  auto (default), urllib or curl; auto retries through the curl
                  binary when Python itself cannot open a socket (sandboxes)

Every subcommand prints JSON on stdout: the tool result's structured content
when the server provides it, otherwise its text content (parsed as JSON when it
is JSON). Errors (HTTP, JSON-RPC, tool isError) go to stderr with exit code 1.
See scripts/ai-context/BM-CLIENT.md for the mapping onto bm_write / bm_edit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://memory.ops.markcheli.com/mcp"
PROTOCOL_VERSION = "2025-03-26"

# Tool names, by preference, for each high-level subcommand. basic-memory 1.0
# ships the bm_* family; the older *_note names are kept as a fallback.
TOOL_CANDIDATES = {
    "read": ["bm_read", "read_note"],
    "write": ["bm_write", "write_note"],
    "edit": ["bm_edit", "edit_note"],
    "search": ["bm_search", "search_notes"],
    "context": ["bm_context", "build_context"],
}


class McpError(Exception):
    pass


class McpClient:
    """Minimal streamable-HTTP MCP client (one session per instance)."""

    def __init__(self, url: str, timeout: float = 120.0, transport: str = "auto"):
        self.url = url
        self.timeout = timeout
        self.transport = transport  # auto | urllib | curl
        self.session_id: str | None = None
        self._next_id = 0
        self._tools: list[dict] | None = None

    # -- transport -----------------------------------------------------------
    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _http_urllib(self, method: str, body: bytes | None) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(self.url, data=body, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:2000]
            raise McpError(f"HTTP {exc.code} from {self.url}: {detail}") from None
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc.reason)) from None

    def _http_curl(self, method: str, body: bytes | None) -> tuple[int, dict, bytes]:
        """Same request through the curl binary (sandboxes that block Python sockets)."""
        cmd = ["curl", "-sS", "--max-time", str(int(self.timeout)), "-D", "-", "-X", method, self.url]
        for k, v in self._headers().items():
            cmd += ["-H", f"{k}: {v}"]
        if body is not None:
            cmd += ["--data-binary", "@-"]
        try:
            proc = subprocess.run(cmd, input=body or b"", capture_output=True, timeout=self.timeout + 10)
        except FileNotFoundError:
            raise McpError("curl transport requested but curl is not installed") from None
        if proc.returncode != 0:
            raise ConnectionError(proc.stderr.decode(errors="replace").strip() or f"curl exit {proc.returncode}")
        out = proc.stdout
        status, headers = 0, {}
        # -D - writes every header block (e.g. "100 Continue") before the body.
        while out.startswith(b"HTTP/"):
            sep = out.find(b"\r\n\r\n")
            if sep < 0:
                sep = out.find(b"\n\n")
                block, out = out[:sep], out[sep + 2 :]
            else:
                block, out = out[:sep], out[sep + 4 :]
            lines = block.decode(errors="replace").splitlines()
            try:
                status = int(lines[0].split()[1])
            except (IndexError, ValueError):
                status = 0
            headers = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
        if status >= 400:
            raise McpError(f"HTTP {status} from {self.url}: {out.decode(errors='replace')[:2000]}")
        return status, headers, out

    def _http(self, method: str, body: bytes | None) -> tuple[int, dict, bytes]:
        if self.transport == "curl":
            return self._http_curl(method, body)
        try:
            return self._http_urllib(method, body)
        except ConnectionError as exc:
            if self.transport != "auto":
                raise McpError(f"cannot reach {self.url}: {exc}") from None
            try:
                result = self._http_curl(method, body)
            except ConnectionError as exc2:
                raise McpError(f"cannot reach {self.url}: {exc} (curl: {exc2})") from None
            self.transport = "curl"
            return result

    def _post(self, payload: dict, expect_response: bool = True) -> dict | None:
        body = json.dumps(payload).encode()
        _status, headers, raw = self._http("POST", body)
        sid = headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if not expect_response or not raw:
            return None
        want_id = payload.get("id")
        if headers.get("content-type", "").startswith("text/event-stream"):
            return self._parse_sse(raw.decode(errors="replace"), want_id)
        return json.loads(raw)

    @staticmethod
    def _parse_sse(text: str, want_id) -> dict:
        """Return the JSON-RPC message whose id matches (last data event otherwise)."""
        last = None
        for block in text.replace("\r\n", "\n").split("\n\n"):
            data_lines = [ln[5:].lstrip() for ln in block.split("\n") if ln.startswith("data:")]
            if not data_lines:
                continue
            try:
                msg = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                continue
            last = msg
            if isinstance(msg, dict) and msg.get("id") == want_id and ("result" in msg or "error" in msg):
                return msg
        if last is None:
            raise McpError("empty SSE response")
        return last

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        msg = self._post(payload)
        if msg is None:
            raise McpError(f"no response to {method}")
        if "error" in msg:
            raise McpError(f"{method} failed: {json.dumps(msg['error'])}")
        return msg.get("result", {})

    # -- lifecycle -------------------------------------------------------------
    def initialize(self) -> dict:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "bm.py", "version": "1.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_response=False)
        return result

    def close(self) -> None:
        if not self.session_id:
            return
        try:
            self._http("DELETE", None)
        except Exception:
            pass  # best effort; the server expires idle sessions anyway

    # -- tools -----------------------------------------------------------------
    def list_tools(self) -> list[dict]:
        if self._tools is None:
            tools: list[dict] = []
            cursor = None
            while True:
                params = {"cursor": cursor} if cursor else {}
                result = self._rpc("tools/list", params)
                tools.extend(result.get("tools", []))
                cursor = result.get("nextCursor")
                if not cursor:
                    break
            self._tools = tools
        return self._tools

    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.list_tools()]

    def pick_tool(self, kind: str) -> str:
        names = set(self.tool_names())
        for cand in TOOL_CANDIDATES[kind]:
            if cand in names:
                return cand
        raise McpError(f"no {kind} tool on this server (have: {', '.join(sorted(names))})")

    def tool_accepts(self, name: str, param: str) -> bool:
        for t in self.list_tools():
            if t["name"] == name:
                return param in t.get("inputSchema", {}).get("properties", {})
        return True  # unknown tool: let the server decide

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


# -- result shaping --------------------------------------------------------------
def shape_result(result: dict):
    """Turn a tools/call result into something JSON-printable and useful."""
    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]
    texts = []
    other = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            texts.append(item.get("text", ""))
        else:
            other.append(item)
    if len(texts) == 1 and not other:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    if texts and not other:
        return texts
    return result


def emit(obj, raw: bool = False) -> None:
    if raw and isinstance(obj, str):
        sys.stdout.write(obj)
        if not obj.endswith("\n"):
            sys.stdout.write("\n")
        return
    json.dump(obj, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def read_content(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [v.strip() for v in value.split(",")]
    return [v for v in items if v]


def drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# -- subcommands -----------------------------------------------------------------
def cmd_tools(client: McpClient, args) -> None:
    tools = client.list_tools()
    if args.names:
        emit([t["name"] for t in tools])
        return
    out = []
    for t in tools:
        entry = {"name": t["name"], "inputSchema": t.get("inputSchema", {})}
        if args.describe:
            entry["description"] = t.get("description", "")
        out.append(entry)
    emit(out)


def cmd_call(client: McpClient, args) -> None:
    try:
        arguments = json.loads(args.json_args) if args.json_args else {}
    except json.JSONDecodeError as exc:
        raise McpError(f"arguments are not valid JSON: {exc}") from None
    if not isinstance(arguments, dict):
        raise McpError("arguments must be a JSON object")
    if args.project and "project" not in arguments and client.tool_accepts(args.tool, "project"):
        arguments["project"] = args.project
    result = client.call_tool(args.tool, arguments)
    if result.get("isError"):
        emit(shape_result(result))
        raise McpError(f"tool {args.tool} returned an error")
    emit(shape_result(result), raw=args.raw)


def _project_args(args) -> dict:
    return {"project": args.project} if args.project else {}


def cmd_read(client: McpClient, args) -> None:
    tool = client.pick_tool("read")
    arguments = {"identifier": args.identifier, **_project_args(args)}
    if args.section:
        arguments["section"] = args.section
    if args.output_format:
        arguments["output_format"] = args.output_format
    _run(client, tool, arguments, args.raw)


def cmd_search(client: McpClient, args) -> None:
    tool = client.pick_tool("search")
    arguments = {"query": args.query, **_project_args(args)}
    if args.limit is not None:
        arguments["page_size"] = args.limit
    if args.output_format:
        arguments["output_format"] = args.output_format
    _run(client, tool, arguments, args.raw)


def cmd_context(client: McpClient, args) -> None:
    tool = client.pick_tool("context")
    arguments = {"identifier": args.identifier, **_project_args(args)}
    if args.depth is not None:
        arguments["depth"] = args.depth
    if args.since:
        arguments["since"] = args.since
    if args.compact:
        arguments["compact"] = True
    if args.output_format:
        arguments["output_format"] = args.output_format
    _run(client, tool, arguments, args.raw)


def _parse_json_object(text: str | None, what: str) -> dict | None:
    if text is None:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpError(f"{what} is not valid JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise McpError(f"{what} must be a JSON object")
    return obj


def cmd_write(client: McpClient, args) -> None:
    """bm_write: `--path` writes exactly there; otherwise `--title` + `--folder`."""
    tool = client.pick_tool("write")
    if not args.path and not (args.title and args.folder):
        raise McpError("write needs --path, or --title and --folder")
    content = read_content(args.content_file)
    arguments = drop_none(
        {
            "identifier": args.path,
            "title": args.title,
            "directory": args.folder if not args.path else None,
            "content": content,
            "tags": split_list(args.tags),
            "note_type": args.type,
            "metadata": _parse_json_object(args.metadata, "--metadata"),
            "overwrite": True if args.overwrite else None,
            "expected_checksum": args.checksum,
            "output_format": args.output_format,
            **_project_args(args),
        }
    )
    extra = _parse_json_object(args.extra, "--extra")
    if extra:
        arguments.update(extra)
    _run(client, tool, arguments, args.raw)


NO_CONTENT_COMMANDS = {"set_metadata"}


def cmd_edit(client: McpClient, args) -> None:
    """bm_edit: the `command` names the edit; content comes from a file or stdin."""
    tool = client.pick_tool("edit")
    content = None
    if args.operation not in NO_CONTENT_COMMANDS:
        content = read_content(args.content_file)
    arguments = drop_none(
        {
            "identifier": args.identifier,
            "command": args.operation,
            "content": content,
            "section": args.section,
            "find_text": args.find,
            "expected_replacements": args.expected,
            "replace_subsections": (not args.keep_subsections) if args.keep_subsections else None,
            "metadata": _parse_json_object(args.metadata, "--metadata"),
            "expected_checksum": args.checksum,
            "output_format": args.output_format,
            **_project_args(args),
        }
    )
    extra = _parse_json_object(args.extra, "--extra")
    if extra:
        arguments.update(extra)
    _run(client, tool, arguments, args.raw)


def _run(client: McpClient, tool: str, arguments: dict, raw: bool) -> None:
    result = client.call_tool(tool, arguments)
    shaped = shape_result(result)
    if result.get("isError"):
        emit(shaped)
        raise McpError(f"tool {tool} returned an error")
    emit(shaped, raw=raw)


# -- argument parsing --------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.environ.get("BM_URL", DEFAULT_URL), help="MCP endpoint (env BM_URL)")
    p.add_argument("--project", default=os.environ.get("BM_PROJECT", "main"), help="project name (env BM_PROJECT; '' to omit)")
    p.add_argument("--timeout", type=float, default=float(os.environ.get("BM_TIMEOUT", "120")))
    p.add_argument(
        "--transport",
        choices=["auto", "urllib", "curl"],
        default=os.environ.get("BM_TRANSPORT", "auto"),
        help="HTTP transport (env BM_TRANSPORT); auto falls back to curl when Python cannot open sockets",
    )
    p.add_argument("--raw", action="store_true", help="print plain text results as text instead of a JSON string")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("tools", help="list tool names and input schemas")
    s.add_argument("--names", action="store_true", help="names only")
    s.add_argument("--describe", action="store_true", help="include descriptions")
    s.set_defaults(func=cmd_tools)

    s = sub.add_parser("read", help="read one note (bm_read)")
    s.add_argument("identifier", help="path, permalink or title")
    s.add_argument("--section", help="only this heading's section")
    s.add_argument("--output-format", choices=["text", "json"])
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("search", help="full-text search (bm_search)")
    s.add_argument("query")
    s.add_argument("--limit", type=int)
    s.add_argument("--output-format", choices=["text", "json"])
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("context", help="follow relations from a note (bm_context)")
    s.add_argument("identifier", help="path, permalink, memory:// url or pattern")
    s.add_argument("--depth", type=int, help="relation hops (1-5)")
    s.add_argument("--since", help="time window for related results, e.g. 30d (server default 7d)")
    s.add_argument("--compact", action="store_true", help="graph shape only, no bodies")
    s.add_argument("--output-format", choices=["text", "json"])
    s.set_defaults(func=cmd_context)

    s = sub.add_parser("write", help="create (or with --overwrite replace) one note (bm_write)")
    s.add_argument("--title", help="note title; with --folder it also names the file")
    s.add_argument("--folder", help="folder for a note addressed by title (bm_write 'directory')")
    s.add_argument("--path", help="exact file path instead of --title/--folder (bm_write 'identifier')")
    s.add_argument("--content-file", help="markdown, may start with front matter; '-' or omitted = stdin")
    s.add_argument("--tags", help="comma-separated")
    s.add_argument("--type", help="front matter type (bm_write 'note_type'; a type: in the content wins)")
    s.add_argument("--metadata", help="JSON object of extra front matter fields")
    s.add_argument("--overwrite", action="store_true", help="replace an existing note")
    s.add_argument("--checksum", help="expected_checksum from a previous read (implies overwrite)")
    s.add_argument("--output-format", choices=["text", "json"])
    s.add_argument("--extra", help="JSON object merged into the arguments")
    s.set_defaults(func=cmd_write)

    s = sub.add_parser("edit", help="change part of one note (bm_edit)")
    s.add_argument("identifier")
    s.add_argument(
        "--operation",
        required=True,
        choices=[
            "append",
            "prepend",
            "find_replace",
            "replace_section",
            "insert_before_section",
            "insert_after_section",
            "set_metadata",
        ],
        help="bm_edit 'command'",
    )
    s.add_argument("--content-file", help="new content; '-' or omitted = stdin (not for set_metadata)")
    s.add_argument("--section", help="heading for section commands, e.g. 'Relations' or 'Auth/Decisions'")
    s.add_argument("--find", help="exact text to find for find_replace")
    s.add_argument("--expected", type=int, help="expected_replacements for find_replace (default 1)")
    s.add_argument("--keep-subsections", action="store_true", help="replace_section stops at the first subsection")
    s.add_argument("--metadata", help="JSON object of front matter fields to merge (set_metadata, or alongside any command)")
    s.add_argument("--checksum", help="expected_checksum from a previous read, to guard the edit")
    s.add_argument("--output-format", choices=["text", "json"])
    s.add_argument("--extra", help="JSON object merged into the arguments")
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("call", help="call any tool with a JSON object of arguments")
    s.add_argument("tool")
    s.add_argument("json_args", nargs="?", default="{}")
    s.set_defaults(func=cmd_call)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.project == "":
        args.project = None
    client = McpClient(args.url, timeout=args.timeout, transport=args.transport)
    try:
        client.initialize()
        args.func(client, args)
        return 0
    except McpError as exc:
        print(f"bm.py: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
