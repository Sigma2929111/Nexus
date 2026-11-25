import os
import tempfile

os.environ.setdefault("NEXUS_HOME", tempfile.mkdtemp(prefix="nexus_test_"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from nexus.master.core import db as dbmod  # noqa: E402
from nexus.master.core.app import create_app  # noqa: E402
from nexus.shared.config import NexusConfig, Paths  # noqa: E402
from nexus.shared.security import hash_password  # noqa: E402

ADMIN_PW = "test-password"


@pytest.fixture()
def client():
    paths = Paths.build()
    paths.ensure()
    if paths.db.exists():
        paths.db.unlink()
    dbmod.reset_engine()
    cfg = NexusConfig(role="master", mdns_enabled=False)
    digest, salt = hash_password(ADMIN_PW)
    cfg.admin_password_hash = digest
    cfg.admin_password_salt = salt
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    resp = client.post("/api/v1/auth/login", json={"password": ADMIN_PW})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def make_block(client, auth, name="test-block"):
    token = client.post("/api/v1/blocks", json={"name": name}, headers=auth).json()["pairing_token"]
    resp = client.post("/api/v1/blocks/pair", json={"token": token, "name": name, "ip": "127.0.0.1"})
    assert resp.status_code == 200, resp.text
    return resp.json()
