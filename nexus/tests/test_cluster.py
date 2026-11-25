from sqlmodel import select

from nexus.block_agent.execution.manager import ProcessManager
from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from tests.conftest import make_block


def test_cluster_exec_without_blocks(client, auth):
    resp = client.post("/api/v1/cluster/exec", json={"command": "echo hi"}, headers=auth)
    assert resp.status_code == 400


def test_cluster_exec_runs_on_online_block(client, auth, monkeypatch):
    pair = make_block(client, auth, name="worker")
    with session_scope() as session:
        block = session.exec(select(m.Block)).first()
        block.status = "ONLINE"
        session.add(block)
        session.commit()

    calls = []

    async def fake_call(block_id, action, payload, timeout=15.0):
        calls.append((block_id, action, payload))
        return {"ok": True, "exit_code": 0, "output": "hello", "duration_ms": 3}

    monkeypatch.setattr("nexus.master.api.cluster.call_agent", fake_call)
    resp = client.post(
        "/api/v1/cluster/exec",
        json={"command": "echo hello", "timeout": 5},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["results"][0]["block_id"] == pair["block_id"]
    assert data["results"][0]["output"] == "hello"
    assert calls[0][1] == "cluster.exec"


def test_run_command_echo_and_home_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pm = ProcessManager(tmp_path / "apps")
    ok = pm.run_command("echo hi")
    assert ok["ok"] is True
    assert "hi" in ok["output"]

    outside = pm.run_command("pwd", cwd="/")
    assert outside["ok"] is False
    assert "inside the account home" in outside["error"]
