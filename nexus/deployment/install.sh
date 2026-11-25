#!/usr/bin/env bash
# NEXUS installer - works without root on a Linux Code Server.
# Installs Python deps into a local venv and creates a `nexus` launcher.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEXUS_HOME="${NEXUS_HOME:-$HOME/.nexus}"
mkdir -p "$NEXUS_HOME"

echo "[nexus] project directory: $DIR"
echo "[nexus] state directory:   $NEXUS_HOME"

# --- 1. Python -------------------------------------------------------------
PY=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$(command -v "$candidate")"; break; fi
done

if [ -z "$PY" ]; then
  echo "[nexus] python3 not found - bootstrapping via uv"
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv python install 3.12
  PY="$(uv python find 3.12)"
fi
echo "[nexus] using python: $PY"

# --- 2. Virtual environment ------------------------------------------------
if [ ! -x "$DIR/.venv/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv "$DIR/.venv" --python "$PY"
  else
    "$PY" -m venv "$DIR/.venv"
  fi
fi

# --- 3. Install package ----------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$DIR/.venv/bin/python" -e "$DIR"
else
  "$DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
  "$DIR/.venv/bin/python" -m pip install -e "$DIR"
fi

# --- 4. Launcher -----------------------------------------------------------
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/nexus" <<EOF
#!/usr/bin/env bash
exec "$DIR/.venv/bin/nexus" "\$@"
EOF
chmod +x "$HOME/.local/bin/nexus"
echo "[nexus] launcher installed at $HOME/.local/bin/nexus"

cat > "$HOME/.local/bin/nexus-run" <<EOF
#!/usr/bin/env bash
exec "$DIR/.venv/bin/python" "$DIR/scripts/nexus_run.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/nexus-run"
echo "[nexus] cluster task launcher installed at $HOME/.local/bin/nexus-run"

# --- 5. Dashboard ----------------------------------------------------------
if [ ! -f "$DIR/nexus/dashboard/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "[nexus] building dashboard..."
    (cd "$DIR/nexus/dashboard" && npm install --no-audit --no-fund && npm run build) \
      || echo "[nexus] dashboard build failed - API still works, UI unavailable"
  else
    echo "[nexus] prebuilt dashboard missing and npm not found."
    echo "[nexus] The API will still run, but the web UI will be unavailable."
  fi
fi

cat <<'EOF'

============================================================
NEXUS installed.

Make sure ~/.local/bin is on your PATH:
    export PATH="$HOME/.local/bin:$PATH"

Then choose this machine's role:

  MASTER:
    nexus up master

  BLOCK (on another server, after creating a token in the panel):
    nexus up block --master https://MASTER_IP:8787 --token TOKEN

Useful commands:
    nexus role | status | discover | down | set-password
============================================================
EOF
