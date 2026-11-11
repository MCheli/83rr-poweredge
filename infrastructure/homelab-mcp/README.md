# homelab-mcp

A read-only **claude.ai custom connector** (remote MCP server) that lets Claude
list and read the Seafile **AI Context** library from any chat, including chats
that run in Anthropic's cloud and can't see the LAN.

```
claude.ai ──HTTPS──▶ Cloudflare ──▶ nginx (mcp.markcheli.com) ──▶ homelab-mcp:8000
                                                                     │  Google OAuth (sign-in)
                                                                     └─▶ seafile:80 (read-only library token)
```

## Tools

All tools are read-only (`readOnlyHint`), and they only see the one library the
token belongs to.

| Tool | What it does |
| --- | --- |
| `library_info` | Library name, size, file count, last modified |
| `list_directory(path)` | One folder's entries |
| `find_files(path, name_glob, modified_since, limit)` | Recursive file search by name and/or date, newest first |
| `read_file(path, offset, max_chars)` | Text file contents, paged; binaries are reported, not returned |
| `search_text(query, path)` | Grep text files (`.md`, `.txt`, `.json`, …) under a folder |

No write, move, delete, share-link or shell tools exist.

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

Optional (container env): `MAX_READ_BYTES` (2 MiB), `SEARCH_MAX_FILES` (400),
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

Tests run against a fake Seafile and a stubbed Google verifier; no network.
