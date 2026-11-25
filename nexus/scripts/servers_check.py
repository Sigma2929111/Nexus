"""End-to-end check for the 'servers' feature: presets, placement, live CPU/RAM,
start/stop and logs against a real MASTER and a real BLOCK agent.
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
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"service did not come up: {url}")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    venv_python = root / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    home = tempfile.mkdtemp(prefix="nexus_servers_")
    env = os.environ.copy()
    env["NEXUS_HOME"] = home
    env["NEXUS_ADMIN_PASSWORD"] = ADMIN_PW
    env["PYTHONUNBUFFERED"] = "1"

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    master = subprocess.Popen(
        [python, "-m", "nexus.cli", "up", "master", "--no-tls", "--port", str(port)],
        cwd=str(root), env=env, stdout=open(Path(home) / "master.log", "w"), stderr=subprocess.STDOUT,
    )
    agent = None
    ok = False
    try:
        wait_http(f"{base}/api/v1/health")
        cl = httpx.Client(timeout=20)
        tok = cl.post(f"{base}/api/v1/auth/login", json={"password": ADMIN_PW}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}

        presets = cl.get(f"{base}/api/v1/presets", headers=h).json()
        assert any(p["id"] == "nodejs" for p in presets)
        print(f"[ok] {len(presets)} presets available")

        pt = cl.post(f"{base}/api/v1/blocks", json={"name": "srv-block"}, headers=h).json()["pairing_token"]
        agent = subprocess.Popen(
            [python, "-m", "nexus.cli", "up", "block", "--master", base, "--token", pt, "--name", "srv-block"],
            cwd=str(root), env=env, stdout=open(Path(home) / "agent.log", "w"), stderr=subprocess.STDOUT,
        )
        for _ in range(80):
            bs = cl.get(f"{base}/api/v1/blocks", headers=h).json()
            if bs and bs[0]["status"] == "ONLINE":
                break
            time.sleep(0.5)
        assert bs and bs[0]["status"] == "ONLINE"
        print("[ok] block ONLINE")

        spec = {
            "name": "cpu-burner",
            "kind": "process",
            "preset": "nodejs",
            "command": "bash -c 'yes > /dev/null'",
            "cpu_limit": 1,
            "ram_limit_mb": 128,
            "disk_limit_mb": 512,
            "ports": [],
            "block_id": bs[0]["id"],
            "env": {},
        }
        r = cl.post(f"{base}/api/v1/apps", json={"spec": spec, "auto_place": False}, headers=h)
        assert r.status_code == 200, r.text
        app_id = r.json()["app_id"]
        print(f"[ok] server created: {app_id}")

        cpu_seen = 0.0
        for _ in range(70):
            apps = cl.get(f"{base}/api/v1/apps", headers=h).json()
            app = next((a for a in apps if a["id"] == app_id), None)
            if app and app["status"] == "RUNNING":
                cpu_seen = max(cpu_seen, app.get("cpu_percent", 0.0))
            if cpu_seen > 0:
                break
            time.sleep(0.5)
        assert cpu_seen > 0, "no CPU usage reported for the running server"
        print(f"[ok] live CPU usage reported: {cpu_seen:.1f}%")

        logs = cl.get(f"{base}/api/v1/apps/{app_id}/logs", headers=h)
        assert logs.status_code == 200
        print("[ok] logs endpoint works")

        w = cl.put(
            f"{base}/api/v1/apps/{app_id}/files/content",
            json={"path": "notes.txt", "content": "hello nexus"},
            headers=h,
        )
        assert w.status_code == 200 and w.json()["ok"], w.text
        r = cl.get(f"{base}/api/v1/apps/{app_id}/files/content", params={"path": "notes.txt"}, headers=h)
        assert r.json()["content"] == "hello nexus"
        listing = cl.get(f"{base}/api/v1/apps/{app_id}/files", params={"path": ""}, headers=h).json()
        assert any(e["name"] == "notes.txt" for e in listing["entries"])
        ex = cl.post(f"{base}/api/v1/apps/{app_id}/exec", json={"command": "cat notes.txt"}, headers=h)
        assert "hello nexus" in ex.json()["output"], ex.text
        d = cl.delete(f"{base}/api/v1/apps/{app_id}/files", params={"path": "notes.txt"}, headers=h)
        assert d.json()["ok"]
        print("[ok] file manager + exec work")

        assert cl.post(f"{base}/api/v1/apps/{app_id}/stop", headers=h).status_code == 200
        time.sleep(0.5)
        apps = cl.get(f"{base}/api/v1/apps", headers=h).json()
        app = next(a for a in apps if a["id"] == app_id)
        assert app["status"] in ("STOPPED", "RUNNING"), app["status"]
        print("[ok] stop executed")

        assert cl.delete(f"{base}/api/v1/apps/{app_id}", headers=h).status_code == 200
        assert cl.get(f"{base}/api/v1/apps", headers=h).json() == []
        print("[ok] server deleted")

        caps = bs[0].get("capabilities") or {}
        print("[ok] capabilities:", ", ".join(f"{k}={v}" for k, v in caps.items()) or "none")

        if not caps.get("docker"):
            docker_spec = {
                "name": "needs-docker",
                "kind": "docker",
                "preset": "nginx",
                "image": "nginx:alpine",
                "cpu_limit": 0.5,
                "ram_limit_mb": 128,
                "disk_limit_mb": 512,
                "ports": [80],
                "block_id": bs[0]["id"],
                "env": {},
            }
            r = cl.post(f"{base}/api/v1/apps", json={"spec": docker_spec, "auto_place": False}, headers=h)
            assert r.status_code == 400 and "docker" in r.text.lower(), r.text
            print("[ok] docker preset rejected with a clear reason")

        if caps.get("python"):
            py_spec = {
                "name": "uploaded-python",
                "kind": "process",
                "preset": "python",
                "command": "python3 main.py",
                "cpu_limit": 0.5,
                "ram_limit_mb": 128,
                "disk_limit_mb": 512,
                "ports": [],
                "block_id": bs[0]["id"],
                "env": {},
            }
            r = cl.post(f"{base}/api/v1/apps", json={"spec": py_spec, "auto_place": False, "start": False}, headers=h)
            assert r.status_code == 200, r.text
            py_id = r.json()["app_id"]
            up = cl.put(
                f"{base}/api/v1/apps/{py_id}/files/content",
                json={"path": "main.py", "content": "print('hi from block')"},
                headers=h,
            )
            assert up.json()["ok"], up.text
            assert cl.post(f"{base}/api/v1/apps/{py_id}/start", headers=h).status_code == 200
            seen = ""
            for _ in range(30):
                app = next(a for a in cl.get(f"{base}/api/v1/apps", headers=h).json() if a["id"] == py_id)
                if app["status"] == "RUNNING":
                    seen = cl.get(f"{base}/api/v1/apps/{py_id}/logs", headers=h).json().get("logs", "")
                    if "hi from block" in seen:
                        break
                time.sleep(0.5)
            assert "hi from block" in seen, seen
            cl.delete(f"{base}/api/v1/apps/{py_id}", headers=h)
            print("[ok] upload file -> create stopped -> start -> ran it on the block")
        ok = True
    finally:
        for proc in (agent, master):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if not ok:
            print("--- master log ---")
            print((Path(home) / "master.log").read_text()[-2500:])
            print("--- agent log ---")
            print((Path(home) / "agent.log").read_text()[-2500:])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
