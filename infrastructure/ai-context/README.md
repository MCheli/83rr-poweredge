# AI Context on the server (the main copy since 2026-11-23)

The Markdown notes that make up Mark's **AI Context** live here, as plain
folders on this server with local git history. AI assistants reach them through
[basic-memory](https://github.com/basicmachines-co/basic-memory) (AGPL-3.0),
read **and write**, behind homelab-mcp's Google OAuth (claude.ai) or, for Claude
Code sessions on the Mac mini, the LAN vhost; Mark reaches them from his Mac and
iPhone through Obsidian Sync's official headless client. The Seafile library
"AI Context" is a **backup** that this server pushes to every 30 minutes and
that nothing writes to any more.

Cut-over done 2026-11-23 (trial since the same morning, side by side with
Seafile). Before it, the folders were a mirror pulled from Seafile.

```
                 claude.ai ──OAuth──▶ homelab-mcp ──docker net──▶ basic-memory ──rw──▶ $AI_CONTEXT_NOTES_DIR  (MAIN vault, git, auto-commit */15, pushed to MCheli/notes)
   Mac mini sessions ──LAN vhost memory.ops (192.168.1.161 only)──▶    │                        ▲
                                                                        │          obsidian-sync-notes (Obsidian Sync, E2E, bidirectional: Mark's devices)
   house-transcriber ──bind mount /output──────────────────────────────────────▶ $AI_CONTEXT_RAW_DIR  (RAW vault, git, auto-commit */15, local only)
                                                                                   ▲
                                                                     obsidian-sync-raw (Obsidian Sync, E2E)
   both vaults ──seafile-backup-push.py (rw library token, */30, never deletes)──▶ Seafile "AI Context" (backup; 04-work and 05-raw/work-laptop stay Seafile-only)
```

Everything personal (the notes, the tokens, the compose `.env`) lives outside
the repo checkout. This directory only holds the generic service definitions;
`scripts/ai-context/` holds the generic scripts.

## Layout on the host

| Path (defaults from `.env.example`) | What |
| --- | --- |
| `/data/ai-context/notes` | MAIN vault: `README.md`, `01-about-me/`, `02-systems/`, `03-diary/`, `templates/` |
| `/data/ai-context/raw` | RAW vault: what used to be `05-raw/` (`house-transcripts/`, `iphone-health/`, `mac-mini/`, `whole-foods/`; work-laptop excluded) |
| `/data/ai-context/state/seafile-push/` | backup push state (`notes.json`, `raw.json`: size/mtime/sha256 per file as last uploaded) |
| `/data/ai-context/state/seafile-pull/` | the old pull's state (kept for a roll-back) |
| `/data/ai-context/state/basic-memory/` | basic-memory `config/config.json`, `.bmignore`, SQLite index, log |
| `/data/ai-context/state/obsidian-notes/`, `obsidian-raw/` | headless client login/session state |
| `/data/ai-context/.secrets/seafile-rw-token` | read-write library token for the backup push (mode 600; the same token house-transcriber used for its Seafile writes) |
| `/data/ai-context/.secrets/seafile-token` | the old read-only pull token (kept for a roll-back) |
| `/data/ai-context/push-config.json`, `pull-config.json` | which folders go where (see each script's docstring) |
| `/data/ai-context/bin/` | copies of the scripts that cron runs |
| `/data/ai-context/logs/` | cron logs |

## Services (`docker-compose.yml` here, standalone)

```bash
cd ~/83rr-poweredge
cp infrastructure/ai-context/.env.example infrastructure/ai-context/.env   # once, adjust paths
docker compose -f infrastructure/ai-context/docker-compose.yml up -d basic-memory
docker compose -f infrastructure/ai-context/docker-compose.yml logs --tail 50 basic-memory
```

### basic-memory (MCP, read-write on the real vault)

- Image pinned by digest (1.0.0). The MAIN vault is mounted **read-write** at
  `/notes`; one project (`main`), MCP server started with `--project main`.
  Index/config on the host under `state/basic-memory`.
- It is the only path for AI writes to the notes (Mark's decision, 2026-11-23):
  `bm_write`/`bm_edit` from a Mac mini session, or `notes_write`/`notes_edit`
  through homelab-mcp from claude.ai. No session edits vault files directly.
- Transport: streamable HTTP, path `/mcp`, no published port, **no auth of its
  own**. Two ways in:
  - homelab-mcp (`infrastructure/homelab-mcp`) over the Docker network
    (`http://basic-memory:8000/mcp`): Google OAuth, email allowlist, a fixed
    allow-list of 8 tools (6 read, write, edit), project pinned, no delete/move.
  - nginx vhost **https://memory.ops.markcheli.com/mcp**, `allow 192.168.1.161;
    deny all;` (the Mac mini only; it was the whole LAN while basic-memory was
    read-only).
- `templates/` is in `.bmignore` (`state/basic-memory/config/.bmignore`, lines
  added 2026-11-23): never indexed, never rewritten, so the templates keep their
  placeholder front matter. homelab-mcp also refuses writes under it.
- Front matter: `ensure_frontmatter_on_sync=false`,
  `update_permalinks_on_move=false`, `kebab_filenames=false`, and still
  basic-memory adds a `permalink:` line and re-serialises the YAML front matter
  of every note it indexes (flow lists become block lists, long values get
  folded, the file's final newline goes). That happened **once**, at the
  cut-over, as a single commit in the vault (`basic-memory: one-time
  front-matter normalisation (cutover)`, 2336 notes, +18291/-6648 lines, body
  text untouched apart from the final newline); from then on only notes that
  change are touched. Tag `pre-cutover-2026-11-23` in both vaults marks the
  state before it.
- `.obsidian`, `.git` and the usual noise are ignored by the default
  `.bmignore`.

Quick checks (from the Mac mini):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://memory.ops.markcheli.com/mcp   # 406/400 without MCP headers = alive; 403 from any other LAN host
docker compose -f infrastructure/ai-context/docker-compose.yml exec basic-memory basic-memory status
```

### Obsidian Sync headless (one container per vault)

Built locally from `Dockerfile.obsidian-headless` (`obsidian-headless` npm
package, open beta, Node 22). Compose profile `obsidian`, so a plain `up -d`
never starts them before they are configured. State: login under
`state/obsidian-<vault>/`, sync settings in `<vault>/.obsidian/` (git-ignored).
Bidirectional: what basic-memory or the transcriber writes goes to Mark's
devices, and his edits come back into the vault (then git, basic-memory's
index and the Seafile backup see them). Conflict strategy "conflict" keeps both
copies as `*conflict*` files; `find /data/ai-context -iname '*conflict*'`
should stay empty (it did through the cut-over's 2336-file rewrite).

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

### Writers

| Writer | Path into the vault |
| --- | --- |
| claude.ai (diary writer, any chat) | homelab-mcp `notes_write` / `notes_edit` → basic-memory |
| Claude Code sessions on the Mac mini | basic-memory `bm_write` / `bm_edit` at memory.ops |
| house-transcriber | appends files straight into `raw/house-transcripts/YYYY/YYYY-MM-DD.md` (bind mount `/output`, runs as uid 1000; `docs/house-transcriber.md`) |
| Mark | Obsidian on his devices (Obsidian Sync) |
| Mac mini collector | still Seafile `05-raw/mac-mini` at the time of writing; the pull is off, so its dumps reach the RAW vault only once it writes here (ssh/rsync into `raw/mac-mini`) |

## Cron (deploy user)

```
#*/30 * * * * python3 /data/ai-context/bin/seafile-pull.py ...                      # disabled 2026-11-23 (cut-over), line kept commented for a roll-back
*/15 * * * * AUTOCOMMIT_PUSH_REPOS=/data/ai-context/notes /data/ai-context/bin/git-autocommit.sh /data/ai-context/notes /data/ai-context/raw >> /data/ai-context/logs/git-autocommit.log 2>&1
*/30 * * * * python3 /data/ai-context/bin/seafile-backup-push.py --config /data/ai-context/push-config.json >> /data/ai-context/logs/seafile-backup-push.log 2>&1
```

`git-autocommit.sh` commits whatever changed and, for the repos listed in
`AUTOCOMMIT_PUSH_REPOS` only, pushes to `origin` when the remote is behind (one
attempt per run, failures logged). The MAIN vault pushes to a **private**
GitHub repo as an offsite copy of its history (remote added by hand once;
gitleaks clean in file and git mode before the first push). The RAW vault has
no remote and is never pushed. Each vault's `.gitignore` starts from
`vault.gitignore` (Obsidian workspace files, trash, tool state, files flagged
by the secret scan).

`seafile-backup-push.py` is the reverse of the old pull: it uploads the local
files that changed (size/mtime/sha256 state per target; new files are compared
with Seafile's listing first) into the library at the same paths, with
`replace=1`. It **never deletes** anything in Seafile, refuses anything that
would land under `/04-work` or `/05-raw/work-laptop` (hard-coded), skips
dot-paths, gitignored files (the secret-flagged raw dumps) and the configured
`exclude_names`, and needs the read-write library token (it refuses a read-only
one). Its first run (2026-11-23) uploaded exactly the 2336 notes the
front-matter normalisation had changed and nothing from `raw/`.

Divergence guard: Seafile is not supposed to be written any more, but an old
writer (the claude.ai diary skill into `~/Seafile/AI Context`, say) might still
do it. Before uploading, the script lists every Seafile file under
`guard_prefixes` (default `/03-diary`) that is missing on this server, or that
Seafile holds in a version the script did not upload (file id differs from the
`remote_id` recorded at upload) and with a newer mtime than the local copy, and
logs `DIVERGED <path>` for it. Such a file is never overwritten and never
imported: look at the log (`grep DIVERGED /data/ai-context/logs/seafile-backup-push.log`),
merge by hand through basic-memory, then the next push carries the server copy.
`--adopt-remote` was run once at deployment to record the ids of the files
uploaded before the guard existed.

The diary writer's state lives in the vault as notes since the cut-over:
`03-diary/_state.md` (the old `_state.json` as one fenced JSON block) and
`03-diary/_runs.md` (the old `_runs.log` lines), both written and read through
basic-memory; `_state.json` and `_runs.log` stay in place for a roll-back.

The index-copy rsync line that existed during the trial is gone with the copy
(`state/basic-memory-copy` deleted at the cut-over).

## Secret scan before the first commit

```bash
docker run --rm -v /data/ai-context/notes:/scan:ro zricethezav/gitleaks:latest detect --no-git --source /scan --report-format json --report-path /dev/stdout
```

Hits are reported as path + rule only; the files stay on disk and are added
to that vault's `.gitignore`.

## Permalinks (measured 2026-11-23, basic-memory 1.0.0)

basic-memory indexes a note only after it has a `permalink:` line in its YAML
front matter and it adds one itself when the vault is writable. With the vault
read-only, notes without a permalink fail normalisation and are skipped (4 of
2343 indexed on a `:ro` mount). On a writable vault it indexes everything in
about 15 minutes and re-serialises the whole front matter of every note while
doing so (see above). During the trial that is why it indexed a disposable rsync
copy; at the cut-over the rewrite was accepted once, on the real vault, as one
commit, and the copy was dropped.

Also observed on a `:ro` mount: `bm_write` reports "Created …" although the
file write fails (`EROFS`), so never run it read-only expecting writes to fail
loudly.

## Roll-back (to Seafile as the main copy)

Everything needed is still in place; nothing was deleted in Seafile.

1. Stop AI writes: in nginx put `allow 192.168.1.0/24;` back or leave it;
   redeploy homelab-mcp from a commit before the write tools (or set
   `HOMELAB_MCP_NOTES_MCP_URL=` empty in `.env` to drop the notes tools).
2. basic-memory back to the copy: in `infrastructure/ai-context/.env` set the
   notes mount back to `state/basic-memory-copy` (the compose variable is
   `AI_CONTEXT_NOTES_DIR`; point a copy dir at it or restore the old
   `AI_CONTEXT_INDEX_COPY_DIR` compose line from git), restore the `*/15 rsync
   -a --update --delete ... notes/ state/basic-memory-copy/` cron line,
   `rm` the index (`state/basic-memory/config/memory.db*`), `up -d basic-memory`.
3. Cron: comment out the `seafile-backup-push.py` line, uncomment the
   `seafile-pull.py` line (its state and read-only token are still there).
4. house-transcriber back to the Seafile API: `docs/house-transcriber.md`
   (roll-back paragraph).
5. The notes themselves: Seafile already holds the normalised front matter
   (pushed at the cut-over). To get the pre-cut-over text back, `git checkout
   pre-cutover-2026-11-23 -- .` in the vault and let the pull/push settle, or
   leave the permalink lines in place (they are harmless to Obsidian and
   Seafile).
