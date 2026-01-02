#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Run photo sync
uv run scripts/photo-sync.py

# Check if there are changes
if [[ -n $(git status --porcelain) ]]; then
    git add static/photos/index.html
    git commit -m "Auto-sync photos"
    GIT_SSH_COMMAND="ssh -i ~/.ssh/github_script" git push

    # Pull on VPS (uses key from SSH config)
    ssh lucentsave_vps "cd fplonka.dev && git fetch && git pull"
fi
