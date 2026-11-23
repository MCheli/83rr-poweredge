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

- Image pinned by digest (1.0.0). It indexes a **disposable copy** of the
  notes vault (`AI_CONTEXT_INDEX_COPY_DIR`, default
  `state/basic-memory-copy`, outside both vaults and outside git) that cron
  refreshes every 15 minutes with `rsync -a --update --delete`; the real vault is
  never mounted into the container. Index/config on the host under
  `state/basic-memory`; one project (`main`), MCP server started with
  `--project main`.
- Transport: streamable HTTP, path `/mcp`, no published port. nginx serves it
  at **https://memory.ops.markcheli.com/mcp** (LAN-only vhost, `allow
  192.168.1.0/24; deny all;`). basic-memory has **no authentication of its
  own**; the OAuth sign-in that protects `mcp.markcheli.com` lives inside
  homelab-mcp's code (FastMCP `GoogleProvider` + email allowlist), so sharing
  it would mean new code there. Until then this stays LAN-only.
- Read-only method: the write tools (`bm_write`, `bm_edit`, `bm_delete`,
  `bm_move`, project create) still exist (1.0.0 has no switch to hide them)
  and they do work on the copy, but the copy is thrown away by the next
  rsync, so nothing they do ever reaches the vault, Seafile or Obsidian.
- File rewriting: `ensure_frontmatter_on_sync=false`,
  `update_permalinks_on_move=false`, `kebab_filenames=false`, and still
  basic-memory rewrites the front matter of every note it indexes (it always
  adds a `permalink:` line). That is why it gets a copy. See "Permalinks".
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
*/15 * * * * AUTOCOMMIT_PUSH_REPOS=/data/ai-context/notes /data/ai-context/bin/git-autocommit.sh /data/ai-context/notes /data/ai-context/raw >> /data/ai-context/logs/git-autocommit.log 2>&1
*/15 * * * * rsync -a --update --delete --exclude .git --exclude .obsidian /data/ai-context/notes/ /data/ai-context/state/basic-memory-copy/ >> /data/ai-context/logs/index-copy-sync.log 2>&1
```

The third line keeps basic-memory's disposable index copy current (vault →
copy only, never back). `--update` matters: basic-memory rewrites the front
matter of every note it indexes, so the copy's files are *newer* than the
vault's and a plain `rsync -a` would re-copy all of them every run and
trigger a full re-index (~15 min of CPU) four times an hour. With `--update`
those rewritten files are skipped; a real edit in the vault carries a newer
mtime than the rewrite and still comes across, and deletions still propagate.
(Edge case: a note whose Seafile mtime is older than the copy's rewrite time,
e.g. uploaded during the initial index, is skipped until it changes again.
A `rm -rf` of the copy followed by the rsync and `basic-memory reindex`
resets everything.)

`seafile-pull.py` fetches only files whose Seafile file id changed, never
deletes locally, and skips the configured work folders/files. `git-autocommit.sh`
commits whatever changed and, for the repos listed in `AUTOCOMMIT_PUSH_REPOS`
only, pushes to `origin` when the remote is behind (one attempt per run, failures
logged). The MAIN vault pushes to a **private** GitHub repo as an offsite copy
of its history (remote added by hand once; gitleaks clean in file and git
mode before the first push). The RAW vault has no remote and is never pushed.
Each vault's
`.gitignore` starts from `vault.gitignore` (Obsidian workspace files, trash,
tool state, files flagged by the secret scan).

## Secret scan before the first commit

```bash
docker run --rm -v /data/ai-context/notes:/scan:ro zricethezav/gitleaks:latest detect --no-git --source /scan --report-format json --report-path /dev/stdout
```

Hits are reported as path + rule only; the files stay on disk and are added
to that vault's `.gitignore`.

## Permalinks (measured 2026-11-23, basic-memory 1.0.0)

basic-memory indexes a note only after it has a `permalink:` line in its YAML
front matter and it adds one itself when the vault is writable. With the vault
read-only, notes without a permalink fail normalisation and are skipped:
**4 of 2343 notes indexed** on the real vault.

On a throwaway *writable* copy of the same notes it indexed all 2343 in about
15 minutes (text search then answers in well under a second; the semantic
embeddings, fastembed on CPU, kept running for a good while longer). But it
did not just add a permalink: it **re-serialised the whole YAML front matter
of 2339 notes** (flow lists such as `sources: [a, b]` became block lists, and
so on: 18k insertions / 6.6k deletions in git terms). So never mount the real
vault `rw` for basic-memory, or every note would change and sync everywhere.

Also observed on the `:ro` mount: `bm_write` reports "Created …" although the
file write fails (`EROFS`, logged); the note exists only in the SQLite index
until `bm_delete` removes it. Writes never reach the vault.

Decision (2026-11-23): basic-memory indexes a **writable, disposable copy**
of the vault (`AI_CONTEXT_INDEX_COPY_DIR`) that cron refreshes from the vault
with `rsync -a --update --delete` every 15 minutes. The index covers every note, the
permalink/front-matter rewrites stay in the copy, and the vault, Seafile and
Obsidian never see them. The copy can be deleted at any time; the next rsync
and a `basic-memory reindex` rebuild it. The alternatives (adding `permalink:`
lines to the real notes, or a `:ro` mount of the vault with 4/2343 coverage)
were not taken.

## Cut-over (later, not done)

When the server folders become the live store: stop the Seafile pull cron and
point the diary writer / transcriber / homelab-mcp at the folders. (The MAIN
vault already has its private remote; decide then whether RAW needs one.)
