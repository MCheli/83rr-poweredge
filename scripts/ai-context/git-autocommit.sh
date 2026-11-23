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
# ). Nothing here ever deletes, resets, rebases or pushes.
set -u

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
    if git -C "$repo" diff --cached --quiet; then
        continue  # nothing to commit, stay silent
    fi
    n=$(git -C "$repo" diff --cached --name-only | wc -l | tr -d ' ')
    if git -C "$repo" commit -q -m "auto: $(date -Is)"; then
        echo "$now [$repo] committed $n file(s): $(git -C "$repo" rev-parse --short HEAD)"
    else
        echo "$now [$repo] commit failed"
        status=1
    fi
done
exit $status
