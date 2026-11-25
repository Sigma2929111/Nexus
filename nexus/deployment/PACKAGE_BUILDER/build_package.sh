#!/usr/bin/env bash
# Build a clean release archive of NEXUS (single package, role chosen at runtime).
# Excludes virtualenvs, node_modules, git history, databases, logs and secrets.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$DIR/dist_packages}"
NAME="nexus-cloud-$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT"

echo "[package] building $NAME from $DIR"
tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.db' \
  --exclude='.pytest_cache' \
  --exclude='dist_packages' \
  --exclude='*.log' \
  --exclude='.nexus' \
  --exclude='*.tar.gz' \
  -czf "$OUT/$NAME.tar.gz" \
  -C "$(dirname "$DIR")" "$(basename "$DIR")"

echo "[package] created: $OUT/$NAME.tar.gz"
echo "[package] sanity check (no obvious secrets):"
if tar -tzf "$OUT/$NAME.tar.gz" | grep -E '(\.env$|\.key$|secret|\.db$)' | grep -v '\.env\.example' ; then
  echo "[package] WARNING: the archive may contain sensitive files (see list above)" >&2
else
  echo "[package] clean - no secrets detected"
fi
