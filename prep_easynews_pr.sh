#!/usr/bin/env bash
# Prepare a clean PR branch for Easynews DDL: branch from upstream/master and
# cherry-pick only commits from easynews-ddl-provider that are not in upstream.
# Run from repo root. Main repo: https://github.com/mylar3/mylar3.git

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

UPSTREAM_URL="https://github.com/mylar3/mylar3.git"
SOURCE_BRANCH="easynews-ddl-provider"
PR_BRANCH="pr-easynews-ddl"

# 1) Add upstream and fetch
if ! git remote get-url upstream &>/dev/null; then
  echo "Adding remote upstream -> $UPSTREAM_URL"
  git remote add upstream "$UPSTREAM_URL"
fi
echo "Fetching upstream..."
git fetch upstream

# 2) Show what would be cherry-picked (oldest first)
COMMITS=$(git log --reverse --format="%h %s" upstream/master.."$SOURCE_BRANCH" 2>/dev/null || true)
if [ -z "$COMMITS" ]; then
  echo "No commits on $SOURCE_BRANCH ahead of upstream/master. Nothing to cherry-pick."
  exit 0
fi
echo "Commits to cherry-pick (oldest first):"
echo "$COMMITS"
echo ""
echo "If this list includes unrelated commits, set SKIP_CHERRYPICK=1 and cherry-pick only Easynews commits manually."
if [ "${SKIP_CHERRYPICK:-0}" = "1" ]; then echo "SKIP_CHERRYPICK=1: skipping cherry-pick."; exit 0; fi
echo ""

# 3) Create PR branch from upstream/master
if git show-ref --verify --quiet "refs/heads/$PR_BRANCH"; then
  echo "Branch $PR_BRANCH already exists. Checking out and resetting to upstream/master..."
  git checkout "$PR_BRANCH"
  git reset --hard upstream/master
else
  echo "Creating branch $PR_BRANCH from upstream/master..."
  git checkout -b "$PR_BRANCH" upstream/master
fi

# 4) Cherry-pick each commit (oldest first; use full hash for cherry-pick)
git log --reverse --format="%H" upstream/master.."$SOURCE_BRANCH" | while read -r hash; do
  subject=$(git log -1 --format="%s" "$hash")
  echo "Cherry-picking: $hash $subject"
  if ! git cherry-pick "$hash"; then
    echo "Conflict or error. Resolve, then: git cherry-pick --continue (or --abort)."
    exit 1
  fi
done

echo ""
echo "Done. Next steps:"
echo "  1. Review: git log upstream/master..HEAD --oneline"
echo "  2. Push:   git push origin $PR_BRANCH"
echo "  3. Open PR at https://github.com/mylar3/mylar3/compare against master (from your fork)."
