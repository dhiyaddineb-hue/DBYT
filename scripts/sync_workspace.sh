#!/usr/bin/env bash
# =============================================================================
# sync_workspace.sh — commit & push everything produced in workspace/ to GitHub.
#
# The repository is the workspace. Run this after a dubbing job (or on a cron /
# post-job hook) to persist models, uploads, jobs and output in the GitHub repo.
#
# Usage:
#   ./scripts/sync_workspace.sh "optional commit message"
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

# Ensure Git LFS is set up (downloads pointers correctly on clone)
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install >/dev/null 2>&1 || true
fi

MSG="${1:-chore(workspace): persist produced files}"

git add workspace
# Only commit if there's something staged
if git diff --cached --quiet; then
  echo "Nothing new to store in workspace/."
else
  git commit -m "$MSG"
  git push
  echo "✅ Workspace saved to the repository."
fi
