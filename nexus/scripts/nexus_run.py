#!/usr/bin/env python3
"""Run a shell command on one or all NEXUS blocks.

Usage:
  nexus-run "npm install && npm test"
  nexus-run --block Plugged.host --cwd /home/container/projects/app "git pull"
  nexus-run --timeout 120 -- "make -j4"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = os.environ.get("NEXUS_URL", "http://127.0.0.1:8787")
PASSWORD_FILE = Path(
    os.environ.get("NEXUS_PASSWORD_FILE", str(Path.home() / ".nexus" / "INITIAL_ADMIN_PASSWORD.txt"))
)


def _request(url: str, method: str = "GET", body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=320) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach master at {url}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(prog="nexus-run", description="Run a command on NEXUS blocks")
    parser.add_argument("--url", default=DEFAULT_URL, help="master URL (default: %(default)s)")
    parser.add_argument("--block", action="append", default=[], help="block name or id (repeatable)")
    parser.add_argument("--cwd", default=None, help="working directory on each block")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds (default: 60)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run")
    args = parser.parse_args()

    command = " ".join(args.command).strip()
    if command.startswith("--"):
        command = command[2:].strip()
    if not command:
        parser.error("empty command")

    password = os.environ.get("NEXUS_PASSWORD")
    if not password:
        try:
            password = PASSWORD_FILE.read_text().strip()
        except OSError as exc:
            raise SystemExit(f"cannot read password file {PASSWORD_FILE}: {exc}") from exc

    base = args.url.rstrip("/")
    token = _request(f"{base}/api/v1/auth/login", "POST", {"password": password}).get("token")
    if not token:
        raise SystemExit("login failed")

    blocks = _request(f"{base}/api/v1/blocks", token=token)
    by_name = {b["name"]: b["id"] for b in blocks}
    by_id = {b["id"]: b["name"] for b in blocks}
    wanted: list[str] = []
    for ref in args.block:
        if ref in by_name:
            wanted.append(by_name[ref])
        elif ref in by_id:
            wanted.append(ref)
        else:
            raise SystemExit(f"unknown block: {ref}")

    body = {
        "command": command,
        "block_ids": wanted or None,
        "cwd": args.cwd,
        "timeout": args.timeout,
    }
    result = _request(f"{base}/api/v1/cluster/exec", "POST", body, token=token)
    failed = 0
    for item in result.get("results", []):
        status = "OK" if item.get("ok") else "FAIL"
        if not item.get("ok"):
            failed += 1
        ms = item.get("duration_ms")
        print(f"=== {item.get('block_name')} · {status}{f' · {ms} ms' if ms is not None else ''} ===")
        if item.get("error"):
            print(f"error: {item['error']}")
        if item.get("output"):
            print(item["output"].rstrip())
        print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
