#!/usr/bin/env bash
# Commit any change in one or more local git repos (no remote, no push).
# Meant for cron: every run, `git add -A` and commit when the index differs.
#
#   git-autocommit.sh /data/ai-context/notes /data/ai-context/raw
#
# The repos must exist already (git init done once by hand, with the author set
# in each repo's config:
#   git config user.name  ai-context-autocommit
#   git config user.email noreply@localhost
# ). Nothing here ever deletes, resets or rebases.
#
# Optional push: AUTOCOMMIT_PUSH_REPOS is a space-separated list of repo paths
# that also get `git push -q origin HEAD` whenever they have commits the
# remote lacks (a remote "origin" and an upstream branch must exist, set up by
# hand once). One attempt per run, failures are logged, no retries. Repos not
# in the list are never pushed.
#   AUTOCOMMIT_PUSH_REPOS=/data/ai-context/notes git-autocommit.sh /data/ai-context/notes /data/ai-context/raw
set -u

push_repos=" ${AUTOCOMMIT_PUSH_REPOS:-} "
status=0
for repo in "$@"; do
    now=$(date '+%Y-%m-%d %H:%M:%S%z')
    if [ ! -d "$repo/.git" ]; then
        echo "$now [$repo] not a git repo, skipping"
        status=1
        continue
    fi
    if ! git -C "$repo" add -A >/dev/null 2>&1; then
        echo "$now [$repo] git add failed"
        status=1
        continue
    fi
    if ! git -C "$repo" diff --cached --quiet; then
        n=$(git -C "$repo" diff --cached --name-only | wc -l | tr -d ' ')
        if git -C "$repo" commit -q -m "auto: $(date -Is)"; then
            echo "$now [$repo] committed $n file(s): $(git -C "$repo" rev-parse --short HEAD)"
        else
            echo "$now [$repo] commit failed"
            status=1
            continue
        fi
    fi
    # Push only listed repos, and only when the remote is behind.
    case "$push_repos" in
        *" $repo "*)
            if ! git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
                echo "$now [$repo] push requested but no upstream configured"
                status=1
                continue
            fi
            ahead=$(git -C "$repo" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
            if [ "$ahead" -gt 0 ]; then
                if git -C "$repo" push -q origin HEAD 2>/dev/null; then
                    echo "$now [$repo] pushed $ahead commit(s) to origin"
                else
                    echo "$now [$repo] push failed ($ahead commit(s) pending)"
                    status=1
                fi
            fi
            ;;
    esac
done
exit $status
