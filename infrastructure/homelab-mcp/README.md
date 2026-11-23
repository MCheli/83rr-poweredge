# homelab-mcp

A **claude.ai custom connector** (remote MCP server) for chats that run in
Anthropic's cloud and can't see the LAN. It lets Claude:

- list and read the Seafile **AI Context** library (read-only; since the
  2026-11-23 cut-over Seafile is a backup copy of the notes, up to an hour behind),
- search, read, **write and edit** the AI Context notes through **basic-memory**
  (`notes_*` tools forwarded over the internal Docker network to the notes vault
  on this server, the main copy; see `infrastructure/ai-context/README.md`), and
- optionally, start and manage **Claude Code sessions on the Mac mini** through
  its session bus, reached over the LAN by ssh. Those sessions do the local
  work (repos, files, ssh back to this server, Home Assistant). The mini has no
  public port and no tunnel, and
- over that same link, read Mark's **iMessages, live and read-only**
  (`imessage_*` tools, since 2026-11-23), so Claude can spot texts that need him.

```
claude.ai ──HTTPS──▶ Cloudflare ──▶ nginx (mcp.markcheli.com) ──▶ homelab-mcp:8000
                                                                     │  Google OAuth (sign-in)
                                                                     ├─▶ seafile:80 (read-only library token)
                                                                     ├─▶ basic-memory:8000/mcp (MCP client, 6 read + write/edit, project pinned)
                                                                     └─▶ ssh (LAN) ─▶ Mac mini bus-gateway ─┬─▶ session-bus
                                                                                                           └─▶ iMessage service (0600 socket) ─▶ chat.db, mode=ro
```

## Tools

The Seafile tools are read-only (`readOnlyHint`), and they only see the one
library the token belongs to.

| Tool | What it does |
| --- | --- |
| `library_info` | Library name, size, file count, last modified |
| `list_directory(path)` | One folder's entries |
| `find_files(path, name_glob, modified_since, limit)` | Recursive file search by name and/or date, newest first |
| `read_file(path, offset, max_chars)` | Text file contents, paged; binaries are reported, not returned |
| `search_text(query, path)` | Grep text files (`.md`, `.txt`, `.json`, …) under a folder |

No write, move, delete or share-link tools exist for Seafile.

With `NOTES_MCP_URL` set (the compose default points at `basic-memory`), these
tools are added; each one is a fixed-allowlist forward to one basic-memory tool
(`app/notes.py`), with `project` pinned to `main`:

| Tool | basic-memory tool | What it does |
| --- | --- | --- |
| `notes_search(query, mode, path, since, lines, filters, …)` | `bm_search` | Ranked search; `lines` gives grep-like matching lines |
| `notes_read(identifier, section, start_line, end_line, max_tokens, …)` | `bm_read` | One note, whole or sliced |
| `notes_list(path, glob, sort, …)` | `bm_list` | One folder |
| `notes_find(path, name, filters, fields, depth, …)` | `bm_find` | Recursive search by file-name glob or front matter |
| `notes_context(identifier, depth, since, …)` | `bm_context` | Follow `[[links]]` between notes |
| `notes_recent(since, items, …)` | `bm_project(command="recent")` | What changed lately |
| `notes_write(content, identifier \| title+directory, overwrite, expected_checksum, …)` | `bm_write` | Create or replace one note (acting tool, `destructiveHint`) |
| `notes_edit(identifier, command, content, section, find_text, metadata, …)` | `bm_edit` | Append/prepend, find/replace, replace or insert a section, set front matter (acting tool) |

The two writing tools exist since the AI Context cut-over (2026-11-23): every
AI note write goes through basic-memory on the server, behind this connector's
Google OAuth, and lands in the real notes vault (Obsidian Sync and the
Seafile backup push follow). They only accept vault-relative paths and refuse
anything under `templates/` (basic-memory doesn't index it, and the templates'
placeholder front matter must stay as it is).

basic-memory 1.0.0 also offers `bm_delete`, `bm_move`, `bm_project`
`list`/`create`, `bm_schema` and `bm_man`. None of those is reachable through
here: the bridge refuses any tool name outside its allowlist before sending
anything, drops the `project`/`projects`/`all_projects` arguments a caller might
pass and sets `project` (and `bm_project`'s `command`) itself; nothing can be
deleted or moved from claude.ai. If basic-memory is down the `notes_*` tools
return a clear error and everything else keeps working; calls time out at 30 s.
Queries, identifiers and note text are never logged.

With `BUS_SSH_TARGET` set, these are added (otherwise they don't exist):

| Tool | What it does |
| --- | --- |
| `bus_spawn(task, name, repo or cwd, …)` | Start a Claude Code session on the mini (marked destructive, so claude.ai asks first) |
| `bus_sessions`, `bus_status`, `bus_logs`, `bus_wait` | See what's running, read output, wait for a report |
| `bus_send`, `bus_stop` | Message or stop a session (also marked destructive) |
| `bus_doctor` | Diagnose the bus on the mini |

`bus_config` and `bus_setup` are never offered.

With `BUS_SSH_TARGET` set these four **read-only iMessage tools** are added too
(`app/imessage.py`). They travel over the same ssh link to bus-gateway, which
hands them to the iMessage service on the mini; this container never sees
chat.db, and nothing new listens anywhere. Answers are near-real-time (what
Messages has right now, seconds old).

| Tool | What it does |
| --- | --- |
| `imessage_recent(since, limit)` | Newest messages: time (ISO 8601 with offset, US Eastern), chat, sender (contact name, else number/email; `me` for Mark), `is_from_me`, `is_group`, text |
| `imessage_search(query, contact, since, limit)` | Case-insensitive text search; `contact` (name, phone or email) limits it to chats that person is in |
| `imessage_threads(since, limit)` | Chats with recent activity: participants, last message time + preview, `incoming_since_my_last_reply` |
| `imessage_unanswered(hours, limit)` | Incoming messages (default last 48 h) Mark hasn't followed with a message or tapback in that chat; group chats included and marked |

Guarantees, all enforced on the mini (`mac-mini-collector`, `collector/imessage_service.py`):
chat.db is opened `file:…?mode=ro` with `PRAGMA query_only` and nothing can be
sent, replied to, reacted to, marked read or deleted (no AppleScript, no
Shortcuts); verification codes and one-time passwords are dropped with the
nightly collector's filter, tapbacks and system rows are skipped; `limit` is
1–100 (default 25), each text is cut at 1,000 characters and each answer kept
under 50 KB; inputs are validated and SQL is parameterized; logs on both ends
carry counts and timings only, never message text, names or handles.

## Session bus on the Mac mini

The mini runs **bus-gateway** (private repo `MCheli/mac-mini-collector`,
`bus-gateway/`): a LaunchAgent that serves the session-bus plugin on a 0600 Unix
socket. This container connects with a dedicated ed25519 key that the mini's
`authorized_keys` pins with `from="<this server's LAN IP>",restrict,command="…relay.py"`,
so the key can't open a shell, a pty or any forwarding; it can only pass one
JSON request to the gateway. The mini's host key is pinned here
(`StrictHostKeyChecking=yes`), so a spoofed host on the LAN gets nothing.

The gateway is installed root-owned outside `~/repos` and re-checks every
request on the mini, so even a compromised server can only use the eight bus
tools and four iMessage tools above, and only in ways that leave Mark in control:

- permission modes `default`, `plan` and `dontAsk` only (more is an opt-in on
  the mini), so no session edits or runs a command his rules don't allow
  without his approval; never `bypassPermissions`;
- folders inside `~/repos` only, never `~/repos` itself or the gateway's own
  repo; `MCheli` repos already cloned there; no cloning from here;
- status, logs, messages and stops reach only bus sessions in those folders;
- at most ten sessions working at once; finished ones (done, blocked, stopped,
  failed, gone, or idle with their report written) don't count;
- sessions don't get Mark's ssh agent;
- the `imessage_*` tools are forwarded to the iMessage service's own 0600
  socket (a LaunchAgent under the collector's Full-Disk-Access launcher, so no
  new grant); the gateway never opens chat.db and the service can only read it;
- nothing but `bus_stop` while `~/.session-bus/remote-off` exists (the
  iMessage tools included).

It logs each call (never task text) to `~/Library/Logs/bus-gateway/audit.jsonl`.
Calls are kept under Cloudflare's 100 s limit (ssh gives up at 95 s); a spawn
needs a unique name, so a retry after a timeout can't start a second session.

## Security model

- **Who can connect:** claude.ai registers itself via OAuth 2.1 (dynamic client
  registration + PKCE). FastMCP's `GoogleProvider` sends you to Google to sign
  in; `AllowlistGoogleProvider` then rejects every token whose **verified**
  Google email isn't in `ALLOWED_EMAILS`. Without a valid token, `/mcp` returns
  401. Authorization codes are only issued to claude.ai's callback URLs
  (`ALLOWED_CLIENT_REDIRECT_URIS`).
- **What it can read:** a Seafile *library API token* (scoped to AI Context
  only). The server checks at startup that the token's permission is `r` and
  refuses to start with an `rw` token. The client only sends GET requests.
- **iMessages:** never on this server. The `imessage_*` tools are plain
  requests over the pinned ssh link to the mini, where the read-only service
  answers them (see Tools above). No message text is logged here; the ssh
  reply is parsed and handed straight back to the caller.
- **Network:** no published ports. nginx proxies only the MCP and OAuth paths;
  everything else on the host is a 404. Seafile (`http://seafile`) and
  basic-memory (`http://basic-memory:8000/mcp`, which has no auth of its own)
  are reached on the internal Docker network, never over the internet;
  basic-memory gets no public URL or port of its own. Its LAN vhost
  (`memory.ops.markcheli.com`) is limited to the Mac mini (192.168.1.161)
  since basic-memory writes to the real vault; everything else reaches it
  only through this connector's OAuth.
- **Container:** non-root, read-only root filesystem, all capabilities dropped,
  `no-new-privileges`. State (OAuth client registrations, Fernet-encrypted
  upstream tokens) lives in the `homelab_mcp_data` volume.
- **Logs:** request URLs from the HTTP client are suppressed, since Seafile
  download links carry one-time tokens.

## Configuration

Set in the root `.env` (values live in 1Password):

| Variable | What |
| --- | --- |
| `HOMELAB_MCP_ALLOWED_EMAILS` | Comma-separated Google accounts allowed to use the connector |
| `HOMELAB_MCP_GOOGLE_CLIENT_ID` / `_SECRET` | Google OAuth "Web application" client, redirect URI `https://mcp.markcheli.com/auth/callback` |
| `HOMELAB_MCP_JWT_SIGNING_KEY` | `openssl rand -hex 32`; signs the tokens this server hands claude.ai and derives the storage encryption key. Rotating it signs everyone out |
| `HOMELAB_MCP_SEAFILE_TOKEN` | AI Context library → API Token, permission **Read-Only** |

Optional, for the session bus (leave the target empty to turn it off):

| Variable | What |
| --- | --- |
| `HOMELAB_MCP_BUS_SSH_TARGET` | `<user>@<mini LAN IP>` |
| `HOMELAB_MCP_BUS_SSH_KEY_B64` | `base64 -w0` of the dedicated private key; written to the container's tmpfs, mode 0600 |
| `HOMELAB_MCP_BUS_SSH_HOST_KEY` | the mini's `/etc/ssh/ssh_host_ed25519_key.pub` (`ssh-ed25519 AAAA…`) |

Notes via basic-memory (on by default):

| Variable | What |
| --- | --- |
| `HOMELAB_MCP_NOTES_MCP_URL` | basic-memory's MCP endpoint; compose defaults to `http://basic-memory:8000/mcp`. Set it empty in `.env` to leave the `notes_*` tools out |

Optional (container env): `NOTES_PROJECT` (`main`), `NOTES_TIMEOUT` (30 s, must stay under 100),
`BUS_SSH_PORT` (22), `MAX_READ_BYTES` (2 MiB), `SEARCH_MAX_FILES` (400),
`SEARCH_MAX_FILE_BYTES` (512 KiB), `TZ_NAME` (`America/New_York`, used for
dates without an offset in `find_files`), `LOG_LEVEL`.

## Turning it on

1. **Seafile token:** files.markcheli.com → AI Context library → its ⋯ menu →
   **Advanced → API Token** (top level in some versions) → app name `claude-connector`, permission **Read-Only** →
   copy into 1Password and `.env` as `HOMELAB_MCP_SEAFILE_TOKEN`.
2. **Google OAuth client:** Google Cloud console → APIs & Services →
   Credentials → Create OAuth client ID → *Web application* → authorized
   redirect URI `https://mcp.markcheli.com/auth/callback`. Scopes needed:
   `openid`, `email`. Publish the consent screen (or Google expires refresh
   tokens after 7 days in *Testing* mode and you'll be asked to sign in weekly).
3. **Signing key:** `openssl rand -hex 32` → `HOMELAB_MCP_JWT_SIGNING_KEY`.
4. **DNS:** Cloudflare → `mcp.markcheli.com` A `173.48.155.66`, **proxied**
   (the dashboard; `cloudflare_dns_manager.py` creates unproxied records).
5. **Deploy** (on the server, after the PR is merged and pulled). The service
   has the compose profile `mcp`, so add `COMPOSE_PROFILES=mcp` to `.env` (keeps
   it running on later plain `up -d` runs); naming it, as below, also starts it:
   ```bash
   cd ~/83rr-poweredge
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build homelab-mcp
   docker compose logs --tail 30 homelab-mcp     # expect: Connected to Seafile library 'AI Context' + Notes tools enabled
   docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
   curl -s https://mcp.markcheli.com/.well-known/oauth-protected-resource/mcp   # 200, JSON
   curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mcp.markcheli.com/mcp   # 401
   ```
6. **claude.ai:** Settings → Connectors → *Add custom connector* → URL
   `https://mcp.markcheli.com/mcp` → Connect → sign in with your Google account.

7. **Session bus (optional, after 1–6 work):**
   1. On the mini: pull `mac-mini-collector` and run `bus-gateway/scripts/install.sh`
      (expect `socket ok`); turn on System Settings → General → Sharing →
      Remote Login, allowed for your user only; then
      `sudo bus-gateway/scripts/harden-sshd.sh` (keys only, that user only).
   2. On the server: `ssh-keygen -t ed25519 -N '' -C homelab-mcp -f /tmp/homelab-mcp-bus`,
      put `base64 -w0 /tmp/homelab-mcp-bus` in `.env` as
      `HOMELAB_MCP_BUS_SSH_KEY_B64`, then `shred -u /tmp/homelab-mcp-bus` after
      copying the `.pub`. (No other copy is needed: if `.env` is lost, make a new
      key and replace the line on the mini.)
   3. On the mini: add the line `install.sh` printed to `~/.ssh/authorized_keys`,
      with this server's LAN IP in `from=` and the `.pub` contents as the key.
   4. Mini's host key → `HOMELAB_MCP_BUS_SSH_HOST_KEY`
      (`cat /etc/ssh/ssh_host_ed25519_key.pub` on the mini); the mini's LAN IP →
      `HOMELAB_MCP_BUS_SSH_TARGET=<user>@<IP>` (give it a DHCP reservation).
   5. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build homelab-mcp`,
      then in claude.ai ask for `bus_sessions`. Off switch on the mini:
      `touch ~/.session-bus/remote-off`.

If claude.ai can't reach it but the curls work from outside, check Cloudflare
Security → Bots / WAF for challenges on `mcp.markcheli.com` (API clients can't
pass a browser challenge) and add a skip rule for that host.

## Development

```bash
cd infrastructure/homelab-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Tests run against a fake Seafile, a stubbed Google verifier, a fake `ssh` and
an in-memory fake basic-memory (which also offers `bm_delete`/`bm_move`, to
prove those never surface while write/edit do); no network.
