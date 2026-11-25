#!/usr/bin/env bash
# Health check for a locally running MASTER (tries HTTPS then HTTP).
set -uo pipefail
PORT="${NEXUS_PORT:-8787}"
for SCHEME in https http; do
  URL="$SCHEME://127.0.0.1:$PORT/api/v1/health"
  if OUT="$(curl -sk --max-time 5 "$URL" 2>/dev/null)" && [ -n "$OUT" ]; then
    echo "[nexus] $URL"
    echo "$OUT"
    exit 0
  fi
done
echo "[nexus] MASTER is not healthy on port $PORT" >&2
exit 1
