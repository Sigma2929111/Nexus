from conftest import ADMIN_PW


def test_login_success(client):
    resp = client.post("/api/v1/auth/login", json={"password": ADMIN_PW})
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_login_wrong_password(client):
    resp = client.post("/api/v1/auth/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_protected_requires_token(client):
    assert client.get("/api/v1/blocks").status_code == 401
    assert client.get("/api/v1/overview").status_code == 401


def test_protected_rejects_bad_token(client):
    assert client.get("/api/v1/blocks", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_health_is_public(client):
    assert client.get("/api/v1/health").status_code == 200
