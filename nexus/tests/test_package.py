import os

import nexus.master.api.package as pkg


def test_package_info_and_download(client, auth, monkeypatch, tmp_path):
    monkeypatch.setattr(pkg, "PACKAGE_DIR", tmp_path)
    empty = client.get("/api/v1/package/info", headers=auth)
    assert empty.status_code == 200
    assert empty.json()["available"] is False

    older = tmp_path / "nexus-cloud-20260101-0000.tar.gz"
    older.write_bytes(b"old")
    newer = tmp_path / "nexus-cloud-20260102-0000.tar.gz"
    newer.write_bytes(b"new-payload")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    info = client.get("/api/v1/package/info", headers=auth).json()
    assert info["available"] is True
    assert info["name"] == newer.name
    assert info["size"] == len(b"new-payload")

    resp = client.get("/api/v1/package/latest", headers=auth)
    assert resp.status_code == 200
    assert resp.content == b"new-payload"
    assert "attachment" in resp.headers["content-disposition"]
    assert newer.name in resp.headers["content-disposition"]


def test_package_requires_auth(client):
    assert client.get("/api/v1/package/info").status_code == 401
    assert client.get("/api/v1/package/latest").status_code == 401
