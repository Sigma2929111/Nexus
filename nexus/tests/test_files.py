import tempfile
from pathlib import Path

import psutil

from nexus.block_agent.execution.manager import ProcessManager
from nexus.block_agent.monitoring.collector import ResourceCollector
from nexus.shared.models import AppSpec


def make_pm() -> ProcessManager:
    pm = ProcessManager(Path(tempfile.mkdtemp()))
    result = pm.create(
        "app1",
        AppSpec(name="x", kind="process", command="sleep 30", cpu_limit=1, ram_limit_mb=128),
    )
    assert result["ok"]
    return pm


def test_file_write_read_list_delete():
    pm = make_pm()
    try:
        assert pm.file_write("app1", "dir/a.txt", "hello")["ok"]
        read = pm.file_read("app1", "dir/a.txt")
        assert read["ok"] and read["content"] == "hello"
        listing = pm.files_list("app1", "dir")
        assert any(e["name"] == "a.txt" for e in listing["entries"])
        assert pm.file_mkdir("app1", "sub")["ok"]
        assert pm.file_rename("app1", "dir/a.txt", "dir/b.txt")["ok"]
        assert pm.file_delete("app1", "dir")["ok"]
        assert not (Path(pm.apps["app1"].workdir) / "dir").exists()
    finally:
        pm.shutdown()


def test_path_traversal_blocked():
    pm = make_pm()
    try:
        assert pm.file_write("app1", "../evil.txt", "x")["ok"] is False
        assert pm.file_delete("app1", "")["ok"] is False
    finally:
        pm.shutdown()


def test_exec_runs_in_app_dir():
    pm = make_pm()
    try:
        pm.file_write("app1", "marker.txt", "ok")
        result = pm.exec("app1", "cat marker.txt")
        assert result["ok"]
        assert "ok" in result["output"]
    finally:
        pm.shutdown()


def test_collector_respects_container_limits():
    snapshot = ResourceCollector().collect()
    host_cores = float(psutil.cpu_count(logical=True) or 1)
    host_ram = psutil.virtual_memory().total / (1024 * 1024)
    assert 0 < snapshot.cpu_cores <= host_cores
    assert 0 < snapshot.ram_total_mb <= host_ram
    assert 0 <= snapshot.cpu_usage_percent <= 100


def test_create_without_start():
    pm = ProcessManager(Path(tempfile.mkdtemp()))
    try:
        result = pm.create("app2", AppSpec(name="y", kind="process", command="sleep 30"), start=False)
        assert result["ok"] and result["status"] == "CREATED"
        state = pm.states()[0]
        assert state.status == "CREATED" and state.pid is None
    finally:
        pm.shutdown()


def test_runtime_path_has_python():
    import shutil

    from nexus.block_agent.runtime_env import apply_runtime_path, runtime_path

    apply_runtime_path()
    assert shutil.which("python3", path=runtime_path()) is not None
