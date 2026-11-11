# homelab-mcp

A **claude.ai custom connector** (remote MCP server) for chats that run in
Anthropic's cloud and can't see the LAN. It lets Claude:

- list and read the Seafile **AI Context** library (read-only), and
- optionally, start and manage **Claude Code sessions on the Mac mini** through
  its session bus, reached over the LAN by ssh. Those sessions do the local
  work (repos, files, ssh back to this server, Home Assistant). The mini has no
  public port and no tunnel.

```
claude.ai ──HTTPS──▶ Cloudflare ──▶ nginx (mcp.markcheli.com) ──▶ homelab-mcp:8000
                                                                     │  Google OAuth (sign-in)
                                                                     ├─▶ seafile:80 (read-only library token)
                                                                     └─▶ ssh (LAN) ─▶ Mac mini bus-gateway ─▶ session-bus
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

With `BUS_SSH_TARGET` set, these are added (otherwise they don't exist):

| Tool | What it does |
| --- | --- |
| `bus_spawn(task, repo or cwd, …)` | Start a Claude Code session on the mini (marked destructive, so claude.ai asks first) |
| `bus_sessions`, `bus_status`, `bus_logs`, `bus_wait` | See what's running, read output, wait for a report |
| `bus_send`, `bus_stop` | Message or stop a session (also marked destructive) |
| `bus_doctor` | Diagnose the bus on the mini |

`bus_config` and `bus_setup` are never offered.

## Session bus on the Mac mini

The mini runs **bus-gateway** (private repo `MCheli/mac-mini-collector`,
`bus-gateway/`): a LaunchAgent that serves the session-bus plugin on a 0600 Unix
socket. This container connects with a dedicated ed25519 key that the mini's
`authorized_keys` pins with `from="<this server's LAN IP>",restrict,command="…relay.py"`,
so the key can't open a shell, a pty or any forwarding; it can only pass one
JSON request to the gateway. The mini's host key is pinned here
(`StrictHostKeyChecking=yes`), so a spoofed host on the LAN gets nothing.

The gateway re-checks every request on the mini, so even a compromised server
can only use the eight tools above: no `bypassPermissions` (every spawn gets an
explicit mode, default `default`, which asks Mark before anything not
pre-allowed), folders inside `~/repos` and `MCheli` repos only, at most three
sessions running, and nothing while `~/.session-bus/remote-off` exists. It logs
each call (never task text) to `~/Library/Logs/bus-gateway/audit.jsonl`.

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
- **Network:** no published ports. nginx proxies only the MCP and OAuth paths;
  everything else on the host is a 404. Seafile is reached on the internal
  Docker network (`http://seafile`), never over the internet.
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

Optional (container env): `BUS_SSH_PORT` (22), `MAX_READ_BYTES` (2 MiB), `SEARCH_MAX_FILES` (400),
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
5. **Deploy** (on the server, after the PR is merged and pulled):
   ```bash
   cd ~/83rr-poweredge
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build homelab-mcp
   docker compose logs --tail 30 homelab-mcp     # expect: Connected to Seafile library 'AI Context'
   docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
   curl -s https://mcp.markcheli.com/.well-known/oauth-protected-resource/mcp   # 200, JSON
   curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mcp.markcheli.com/mcp   # 401
   ```
6. **claude.ai:** Settings → Connectors → *Add custom connector* → URL
   `https://mcp.markcheli.com/mcp` → Connect → sign in with your Google account.

7. **Session bus (optional, after 1–6 work):**
   1. On the mini: pull `mac-mini-collector` and run `bus-gateway/scripts/install.sh`
      (expect `socket ok`); turn on System Settings → General → Sharing →
      Remote Login, allowed for your user only.
   2. On the server: `ssh-keygen -t ed25519 -N '' -C homelab-mcp -f /tmp/homelab-mcp-bus`,
      store it in 1Password (vault Agents), put `base64 -w0 /tmp/homelab-mcp-bus`
      in `.env` as `HOMELAB_MCP_BUS_SSH_KEY_B64`, then `shred -u /tmp/homelab-mcp-bus`
      after copying the `.pub`.
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
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Tests run against a fake Seafile, a stubbed Google verifier and a fake `ssh`;
no network.
