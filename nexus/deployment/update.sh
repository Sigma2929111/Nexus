#!/usr/bin/env bash
# Update NEXUS in place (git pull + reinstall).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -d .git ]; then
  echo "[nexus] pulling latest changes..."
  git pull --ff-only || echo "[nexus] git pull failed - continuing with local files"
else
  echo "[nexus] not a git checkout - skipping pull"
fi

echo "[nexus] reinstalling..."
bash "$DIR/deployment/install.sh"
echo "[nexus] update complete. Restart with: $DIR/deployment/stop.sh && $DIR/deployment/start.sh <role>"
