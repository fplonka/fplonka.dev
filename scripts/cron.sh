#!/bin/zsh
set -e

source ~/.zshrc

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[$(date)] Starting photo sync..."

# Run photo sync
uv run scripts/photo-sync.py

# Check if there are changes
if [[ -n $(git status --porcelain) ]]; then
    echo "[$(date)] Changes detected, pushing to GitHub..."
    git add static/photos/index.html
    git commit -m "Auto-sync photos"
    GIT_SSH_COMMAND="ssh -i ~/.ssh/github_script" git push

    echo "[$(date)] Pulling on VPS..."
    ssh lucentsave_vps "cd fplonka.dev && git fetch && git pull"
    echo "[$(date)] Done!"
else
    echo "[$(date)] No changes detected, skipping push."
fi
