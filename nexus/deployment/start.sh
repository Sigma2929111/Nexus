#!/usr/bin/env bash
# Start NEXUS in the background as MASTER or BLOCK.
# Usage:
#   ./start.sh master [--port 8787] [--no-tls]
#   ./start.sh block --master https://IP:8787 --token TOKEN [--name NAME] [--ca cert.pem]
set -euo pipefail

ROLE="${1:-}"
shift || true
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEXUS_HOME="${NEXUS_HOME:-$HOME/.nexus}"
mkdir -p "$NEXUS_HOME"
PID_FILE="$NEXUS_HOME/nexus.pid"
LOG_FILE="$NEXUS_HOME/nexus.log"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[nexus] already running (pid $(cat "$PID_FILE"))"
  exit 1
fi

case "$ROLE" in
  master|block) ;;
  *) echo "usage: $0 {master|block} [options]"; exit 2 ;;
esac

cd "$DIR"
setsid nohup "$DIR/.venv/bin/nexus" up "$ROLE" "$@" >"$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
sleep 1
echo "[nexus] started $ROLE (pid $(cat "$PID_FILE"))"
echo "[nexus] logs: $LOG_FILE"
