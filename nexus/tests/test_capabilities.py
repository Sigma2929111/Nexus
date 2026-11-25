from nexus.master.core import models_db as m
from nexus.master.scheduler.scheduler import missing_capabilities
from nexus.shared.models import AppSpec


def _block(caps: dict) -> m.Block:
    import json

    return m.Block(id="b", name="b", secret_hash="x", snapshot_json=json.dumps({"capabilities": caps}))


def test_docker_preset_requires_docker():
    block = _block({"python": "3.12.3"})
    assert missing_capabilities(AppSpec(name="x", kind="docker", image="nginx:alpine"), block) == ["docker"]


def test_python_and_node_requirements():
    block = _block({"python": "3.12.3"})
    assert missing_capabilities(AppSpec(name="x", command="python3 main.py"), block) == []
    assert missing_capabilities(AppSpec(name="x", command="node index.js"), block) == ["node"]


def test_capabilities_present_when_installed():
    block = _block({"python": "3.12.3", "node": "22.11.0", "docker": "24.0.7"})
    assert missing_capabilities(AppSpec(name="x", kind="docker", image="redis:7"), block) == []
