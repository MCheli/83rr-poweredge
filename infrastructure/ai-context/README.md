# AI Context on the server (trial, side by side with Seafile)

A second home for the Markdown notes that live in the Seafile **AI Context**
library: plain folders on this server, local git history, read-only MCP access
for AI assistants through [basic-memory](https://github.com/basicmachines-co/basic-memory)
(AGPL-3.0), and Obsidian Sync's official headless client to reach the same
files from Obsidian on other devices.

**Seafile stays the live store until a cut-over is decided.** The folders here
are a mirror that a cron job refreshes from Seafile every 30 minutes
(Seafile wins on conflict). Nothing here writes to Seafile.

```
Seafile "AI Context" ──(read-only API token, every 30 min)──▶ $AI_CONTEXT_NOTES_DIR  (git, auto-commit every 15 min)
                                                            └▶ $AI_CONTEXT_RAW_DIR    (git, auto-commit every 15 min)
                                                                   │                        │
                                        basic-memory ◀─ :ro ───────┘                        │
                                        (MCP, LAN-only via nginx)                           │
                                        obsidian-sync-notes ◀──────┘   obsidian-sync-raw ◀──┘
                                        (Obsidian Sync, E2E)           (Obsidian Sync, E2E)
```

Everything personal (the notes, the Seafile token, the compose `.env`) lives
outside the repo checkout. This directory only holds the generic service
definitions; `scripts/ai-context/` holds the generic scripts.

## Layout on the host

| Path (defaults from `.env.example`) | What |
| --- | --- |
| `/data/ai-context/notes` | MAIN vault: `README.md`, `01-about-me/`, `02-systems/`, `03-diary/`, `templates/` |
| `/data/ai-context/raw` | RAW vault: the contents of `05-raw/` (work sub-folders excluded) |
| `/data/ai-context/state/seafile-pull/` | pull state (`notes.json`, `raw.json`: Seafile file id per path) |
| `/data/ai-context/state/basic-memory/` | basic-memory `config/config.json` + SQLite index |
| `/data/ai-context/state/obsidian-notes/`, `obsidian-raw/` | headless client login/session state |
| `/data/ai-context/.secrets/seafile-token` | the read-only library token (mode 600) |
| `/data/ai-context/pull-config.json` | which Seafile folders go where (see the script's docstring) |
| `/data/ai-context/bin/` | copies of the two scripts that cron runs |
| `/data/ai-context/logs/` | cron logs |

## Services (`docker-compose.yml` here, standalone)

```bash
cd ~/83rr-poweredge
cp infrastructure/ai-context/.env.example infrastructure/ai-context/.env   # once, adjust paths
docker compose -f infrastructure/ai-context/docker-compose.yml up -d basic-memory
docker compose -f infrastructure/ai-context/docker-compose.yml logs --tail 50 basic-memory
```

### basic-memory (read-only MCP)

- Image pinned by digest (1.0.0). Notes mounted **read-only**; index/config on
  the host under `state/basic-memory`; one project (`main`), MCP server
  started with `--project main`.
- Transport: streamable HTTP, path `/mcp`, no published port. nginx serves it
  at **https://memory.ops.markcheli.com/mcp** (LAN-only vhost, `allow
  192.168.1.0/24; deny all;`). basic-memory has **no authentication of its
  own**; the OAuth sign-in that protects `mcp.markcheli.com` lives inside
  homelab-mcp's code (FastMCP `GoogleProvider` + email allowlist), so sharing
  it would mean new code there. Until then this stays LAN-only.
- Read-only method: the write tools (`write_note`, `edit_note`, `delete_note`,
  `move_note`, project create/delete) still exist (1.0.0 has no switch to hide
  them) but fail with a read-only filesystem error.
- File rewriting: `ensure_frontmatter_on_sync=false`,
  `update_permalinks_on_move=false`, `kebab_filenames=false`. **Permalinks:**
  basic-memory always tries to add a `permalink:` front-matter line to a note
  that has none; on the `:ro` mount that write fails and the indexer skips the
  note. See "Permalinks" below for what that means for this vault.
- `.obsidian`, `.git` and the usual noise are ignored by basic-memory's default
  `.bmignore` (created in `state/basic-memory/config/`).

Quick checks (from the LAN):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://memory.ops.markcheli.com/mcp   # 406/400 without MCP headers = alive
docker compose -f infrastructure/ai-context/docker-compose.yml exec basic-memory basic-memory status
```

### Obsidian Sync headless (one container per vault)

Built locally from `Dockerfile.obsidian-headless` (`obsidian-headless` npm
package, open beta, Node 22). Compose profile `obsidian`, so a plain `up -d`
never starts them before they are configured. State: login under
`state/obsidian-<vault>/`, sync settings in `<vault>/.obsidian/` (git-ignored).

One-off setup, run as the deploy user (credentials come from 1Password; never
put them on a command line that lands in shell history):

```bash
C="docker compose -f infrastructure/ai-context/docker-compose.yml"
# 1. login (same account for both containers; prompts for email/password/MFA)
$C run --rm obsidian-sync-notes login
$C run --rm obsidian-sync-raw   login
$C run --rm obsidian-sync-notes sync-list-remote
# 2. remote vaults (end-to-end encrypted; the password is prompted, keep it in 1Password)
$C run --rm obsidian-sync-notes sync-create-remote --name "AI Context"     --encryption end-to-end
$C run --rm obsidian-sync-raw   sync-create-remote --name "AI Context Raw" --encryption end-to-end
# 3. connect the folders, keep both copies on conflict, bidirectional
$C run --rm obsidian-sync-notes sync-setup  --vault "AI Context"     --path /vault --device-name 83rr-poweredge
$C run --rm obsidian-sync-notes sync-config --path /vault --mode bidirectional --conflict-strategy conflict --file-types image,audio,video,pdf,unsupported
$C run --rm obsidian-sync-raw   sync-setup  --vault "AI Context Raw" --path /vault --device-name 83rr-poweredge
$C run --rm obsidian-sync-raw   sync-config --path /vault --mode bidirectional --conflict-strategy conflict --file-types image,audio,video,pdf,unsupported
# 4. long-running sync (restart: unless-stopped)
$C --profile obsidian up -d
$C run --rm obsidian-sync-notes sync-status --path /vault
```

Limits (Sync Plus): 200 MB per file; the vaults here are far below that.

## Cron (deploy user)

```
*/30 * * * * python3 /data/ai-context/bin/seafile-pull.py --config /data/ai-context/pull-config.json >> /data/ai-context/logs/seafile-pull.log 2>&1
*/15 * * * * /data/ai-context/bin/git-autocommit.sh /data/ai-context/notes /data/ai-context/raw >> /data/ai-context/logs/git-autocommit.log 2>&1
```

`seafile-pull.py` fetches only files whose Seafile file id changed, never
deletes locally, and skips the configured work folders/files. `git-autocommit.sh`
commits whatever changed (no remote, nothing is pushed anywhere). Each vault's
`.gitignore` starts from `vault.gitignore` (Obsidian workspace files, trash,
tool state, files flagged by the secret scan).

## Secret scan before the first commit

```bash
docker run --rm -v /data/ai-context/notes:/scan:ro zricethezav/gitleaks:latest detect --no-git --source /scan --report-format json --report-path /dev/stdout
```

Hits are reported as path + rule only; the files stay on disk and are added
to that vault's `.gitignore`.

## Permalinks

basic-memory indexes a note only after it has a `permalink:` line in its YAML
front matter (it adds one itself when the vault is writable). With the vault
read-only, notes without a permalink are skipped by the index. Options when
this matters: let basic-memory write permalinks once (mount `rw` for a single
`basic-memory reindex`, which changes the files and Seafile/Obsidian will see
that), add them in the templates going forward, or run basic-memory against a
writable copy. This is a decision for the vault owner, not something the
container does on its own.

## Cut-over (later, not done)

When the server folders become the live store: stop the Seafile pull cron,
point the diary writer / transcriber / homelab-mcp at the folders, and
consider a private git remote for the two vault repos.
