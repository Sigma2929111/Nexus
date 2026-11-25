#!/usr/bin/env bash
# Stop the locally running NEXUS process.
set -euo pipefail
NEXUS_HOME="${NEXUS_HOME:-$HOME/.nexus}"
PID_FILE="$NEXUS_HOME/nexus.pid"
if [ ! -f "$PID_FILE" ]; then
  echo "[nexus] no pid file, nothing to stop"
  exit 0
fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "[nexus] sent SIGTERM to $PID"
else
  echo "[nexus] process $PID not running"
fi
rm -f "$PID_FILE"
