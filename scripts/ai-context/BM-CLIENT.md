# `bm.py`: command-line client for basic-memory (MCP over streamable HTTP)

`scripts/ai-context/bm.py` lets a shell session or a cron job call the
basic-memory MCP server that serves the AI Context notes vault, without an MCP
host. Python 3.10+ standard library only. Every note write from an AI session
goes through basic-memory (`bm_write` / `bm_edit`), never straight to the vault
files, so this is the tool for scripted writes.

```bash
python3 scripts/ai-context/bm.py tools --names              # the server's tool names
python3 scripts/ai-context/bm.py tools --describe           # names, input schemas, descriptions
python3 scripts/ai-context/bm.py read README.md             # one note, JSON (content, frontmatter, checksum)
python3 scripts/ai-context/bm.py --raw read README.md       # the note's text as text
python3 scripts/ai-context/bm.py read some/note.md --section Relations
python3 scripts/ai-context/bm.py search "query words" --limit 5 --output-format json
python3 scripts/ai-context/bm.py context "folder/Note Title.md" --depth 2 --since 30d --output-format json
python3 scripts/ai-context/bm.py write --title "Note Title" --folder some/folder --content-file note.md --output-format json
python3 scripts/ai-context/bm.py write --path some/folder/exact-name.md --content-file note.md --overwrite
python3 scripts/ai-context/bm.py edit some/note.md --operation append --content-file more.md
python3 scripts/ai-context/bm.py edit some/note.md --operation set_metadata --metadata '{"updated": "2026-11-23"}' --checksum <sha256 from read>
python3 scripts/ai-context/bm.py edit some/note.md --operation replace_section --section Relations --content-file relations.md
python3 scripts/ai-context/bm.py call bm_list '{"path": "01-about-me", "page_size": 50, "output_format": "json"}'
python3 scripts/ai-context/bm.py call bm_man '{"page": "bm_write"}' --raw
```

Results are printed as JSON (the tool's structured content, or its text content
parsed as JSON when it is JSON; `--raw` prints plain text results as text).
Errors go to stderr with exit code 1, including tool errors (the server's
message is printed first).

## Connection

| Setting | Default | Notes |
| --- | --- | --- |
| `BM_URL` / `--url` | `https://memory.ops.markcheli.com/mcp` | LAN vhost, admits the Mac mini only. On the server itself use the container directly: `BM_URL=http://<basic-memory container ip>:8000/mcp` (`docker inspect basic-memory`), or `http://basic-memory:8000/mcp` from a container on the `83rr-poweredge_infrastructure` network. |
| `BM_PROJECT` / `--project` | `main` | Added to every call whose tool takes a `project` argument (all note tools do). `--project ''` omits it. |
| `BM_TRANSPORT` / `--transport` | `auto` | `urllib`, or `curl` (the request is made by the `curl` binary). `auto` tries urllib and falls back to curl when Python cannot open a socket, which is the case inside a Claude Code sandbox on the Mac mini: there `curl` reaches the LAN and Python does not. |
| `BM_TIMEOUT` / `--timeout` | `120` | seconds per HTTP request |

Each invocation is one MCP session: `initialize`, `notifications/initialized`,
the call, then `DELETE` of the session. The server answers with SSE
(`text/event-stream`) or plain JSON; both are handled.

## Tool surface (basic-memory 1.0.0 image, MCP server "Basic Memory" 4.1.3)

Tools: `bm_context`, `bm_delete`, `bm_edit`, `bm_find`, `bm_list`, `bm_man`,
`bm_move`, `bm_project`, `bm_schema`, `bm_search`, `bm_read`, `bm_write`.
There are no `write_note` / `edit_note` tools on this server; `bm.py` maps its
subcommands onto the `bm_*` names (and would fall back to the old names if a
server offered only those). Every schema has `additionalProperties: false`, so
an unknown argument name is a tool error. `bm_delete` and `bm_move` exist but
are not to be used on the AI Context vault.

### `bm_write` (subcommand `write`)

| Parameter | `bm.py` flag | Meaning |
| --- | --- | --- |
| `content` (required) | `--content-file F`, `-` or omitted = stdin | The Markdown, saved as given; may start with front matter. |
| `identifier` | `--path` | Exact file path (`.md` added when missing). Use instead of title + directory. |
| `title` | `--title` | With `directory` it also names the file (title case is kept: `Note Title.md`). |
| `directory` | `--folder` | Folder for a note addressed by title; `/` is the root. Missing folders are created. |
| `note_type` | `--type` | Front matter `type:` (default `note`); a `type:` in the content wins. |
| `tags` | `--tags a,b` | List or `a,b,c`. |
| `metadata` | `--metadata '{...}'` | Extra front matter fields merged in. |
| `overwrite` | `--overwrite` | Replace an existing note; without it an existing note is an error. |
| `expected_checksum` | `--checksum` | Replace only the revision read (checksum from `read`); implies overwrite. |
| `output_format` | `--output-format json` | `text` (default) or `json`: `{action, title, permalink, file_path, checksum, similar_notes}`. |
| `project` (required) | `--project` | |

What the server does to a written note: it adds a `permalink:` line to the
front matter (after the `type:` line when there is one), re-serialises the YAML
(flow lists `[a, b]` become block lists, custom keys and their order are kept)
and drops the file's final newline. The body is saved byte for byte, fenced
blocks included. Permalinks are `<project>/<folder path>/<kebab-cased title>`.

### `bm_edit` (subcommand `edit`)

| Parameter | `bm.py` flag | Meaning |
| --- | --- | --- |
| `identifier` (required) | positional | Path, permalink, memory:// URL or exact title. |
| `command` (required) | `--operation` | `append`, `prepend`, `find_replace`, `replace_section`, `insert_before_section`, `insert_after_section`, `set_metadata`. |
| `content` | `--content-file F` / stdin | Text to add or the replacement (not for `set_metadata`). |
| `section` | `--section` | Heading for the section commands, named without the `#`s: `Relations`, `Auth/Decisions` for a nested one, `Decisions[1]` for the second of two. |
| `find_text` | `--find` | For `find_replace`: exact, case-sensitive text. |
| `expected_replacements` | `--expected N` | For `find_replace`: how many times `find_text` must occur (default 1). |
| `replace_subsections` | `--keep-subsections` sets it false | `replace_section` replaces the subsections too unless false. |
| `metadata` | `--metadata '{...}'` | Front matter fields to set (`set_metadata`); also merges alongside any other command. `title` and `permalink` are refused. |
| `expected_checksum` | `--checksum` | Edit only the revision read; otherwise `REVISION_CONFLICT` with the current checksum, nothing changed. |
| `output_format` | `--output-format json` | `json`: `{action, title, permalink, file_path, checksum, command}`. |
| `project` (required) | `--project` | |

How the edits behave:

- **Front matter**: `set_metadata` merges the given keys into the existing front
  matter and leaves the body alone. Other keys are kept; the whole front matter
  is re-serialised the same way as on write. A value given as a JSON string is
  written as a YAML string, so a date set this way comes out quoted
  (`updated: '2026-11-23'`), where the same date written in the content of a
  `write` stays unquoted (`updated: 2026-11-23`).
- **Append / prepend**: `append` adds `content` at the end of the file,
  `prepend` right after the front matter. A `section` with `append` is refused;
  use `insert_after_section` to add under a heading.
- **Section replace**: `replace_section` swaps the body under the heading
  (keeping the heading line) and, by default, its subsections.
  `insert_before_section` / `insert_after_section` add text around a section.
- Read first with `read … --output-format json` to get the `checksum`, pass it
  as `--checksum`, and the edit fails safely if the note changed in between.
- A missing note is an error; `bm_edit` never creates notes.

### Observations and relations

basic-memory parses `- [category] text` lines as observations and
`- relation_type [[Other Note]]` lines as relations, wherever they appear in the
body. A relation to a note that does not exist yet is stored unresolved and is
resolved when that note is written later. A trailing parenthesis on an
observation line, `- [fact] text (detail)`, is treated as the observation's
context: the file keeps the full line, the index stores `text` as the content.

## Running it elsewhere

The script has no dependencies, so it can be copied to the server and run with
the system Python (`scp scripts/ai-context/bm.py host:/tmp/bm.py`, then
`BM_URL=http://<container ip>:8000/mcp python3 -I /tmp/bm.py …`). Nothing in it
is specific to one vault or project.
