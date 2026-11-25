"""End-to-end smoke check: real MASTER + real BLOCK agent.

Runs entirely with subprocesses so it exercises the actual CLI, pairing,
WebSocket heartbeat and resource reporting. Exits 0 on success.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ADMIN_PW = "admin123"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_http(url: str, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"service did not come up: {url}")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    venv_python = root / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    home = tempfile.mkdtemp(prefix="nexus_e2e_")
    env = os.environ.copy()
    env["NEXUS_HOME"] = home
    env["NEXUS_ADMIN_PASSWORD"] = ADMIN_PW
    env["PYTHONUNBUFFERED"] = "1"

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    master_log = open(Path(home) / "master.log", "w")
    agent_log = open(Path(home) / "agent.log", "w")

    master = subprocess.Popen(
        [python, "-m", "nexus.cli", "up", "master", "--no-tls", "--port", str(port)],
        cwd=str(root),
        env=env,
        stdout=master_log,
        stderr=subprocess.STDOUT,
    )
    agent = None
    ok = False
    try:
        wait_http(f"{base}/api/v1/health")
        print("[ok] master is up")

        token_resp = httpx.post(f"{base}/api/v1/auth/login", json={"password": ADMIN_PW}, timeout=10)
        token_resp.raise_for_status()
        headers = {"Authorization": f"Bearer {token_resp.json()['token']}"}
        print("[ok] admin login")

        unauth = httpx.get(f"{base}/api/v1/blocks", timeout=10)
        assert unauth.status_code == 401, "unauthenticated access must be rejected"
        print("[ok] unauthenticated API rejected")

        created = httpx.post(f"{base}/api/v1/blocks", json={"name": "e2e-block"}, headers=headers, timeout=10)
        created.raise_for_status()
        pairing = created.json()["pairing_token"]
        print("[ok] pairing token issued")

        bad = httpx.post(f"{base}/api/v1/blocks/pair", json={"token": "definitely-bad", "name": "rogue"}, timeout=10)
        assert bad.status_code == 403, f"bad token must be rejected, got {bad.status_code}"
        print("[ok] invalid pairing token rejected")

        agent = subprocess.Popen(
            [
                python,
                "-m",
                "nexus.cli",
                "up",
                "block",
                "--master",
                base,
                "--token",
                pairing,
                "--name",
                "e2e-block",
            ],
            cwd=str(root),
            env=env,
            stdout=agent_log,
            stderr=subprocess.STDOUT,
        )
        print("[..] block agent started, waiting for ONLINE")

        deadline = time.time() + 40
        block = None
        while time.time() < deadline:
            blocks = httpx.get(f"{base}/api/v1/blocks", headers=headers, timeout=10).json()
            if blocks and blocks[0]["status"] == "ONLINE":
                block = blocks[0]
                break
            time.sleep(0.5)
        assert block is not None, "block never reached ONLINE"
        assert block["quotas"]["cpu"]["physical"] > 0, "no CPU reported"
        print(f"[ok] block ONLINE: {block['name']} cpu={block['quotas']['cpu']['physical']} ram_mb={block['quotas']['ram']['physical']:.0f}")

        overview = httpx.get(f"{base}/api/v1/overview", headers=headers, timeout=10).json()
        assert overview["blocks_online"] == 1
        print("[ok] overview reflects online block")

        plan = httpx.post(f"{base}/api/v1/inference/plan", json={"preset": "llama-3-8b"}, headers=headers, timeout=10).json()
        assert plan["feasible"] is False and plan["reasons"], "no-GPU plan must be honestly infeasible"
        print("[ok] inference planner is honest without GPUs")

        ok = True
    finally:
        for proc in (agent, master):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        master_log.close()
        agent_log.close()
        if not ok:
            print("--- master log ---")
            print((Path(home) / "master.log").read_text()[-3000:])
            print("--- agent log ---")
            print((Path(home) / "agent.log").read_text()[-3000:])

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
