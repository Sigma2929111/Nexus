"""Runtime PATH discovery for BLOCK agents.

Apps are launched with the same user as the agent, but that user may have
Python/Node installed in non-standard locations (venv, ~/.local, uv, etc).
We expose those directories on PATH so presets like `python3 main.py` and
`node index.js` work without editing every command.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_dirs() -> list[str]:
    dirs: list[str] = []
    try:
        dirs.append(str(Path(sys.executable).resolve().parent))
    except OSError:
        pass
    home = Path.home()
    for rel in (".local/bin", ".local/node/bin", ".local/share/uv/python"):
        p = home / rel
        if p.is_dir():
            dirs.append(str(p))
    for raw in ("/usr/local/bin", "/usr/bin", "/bin"):
        if Path(raw).is_dir():
            dirs.append(raw)
    return dirs


def runtime_path() -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for part in _candidate_dirs() + os.environ.get("PATH", "").split(os.pathsep):
        if part and part not in seen:
            seen.add(part)
            parts.append(part)
    return os.pathsep.join(parts)


def apply_runtime_path() -> None:
    os.environ["PATH"] = runtime_path()
