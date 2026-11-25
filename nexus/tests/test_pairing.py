from conftest import make_block


def test_pair_and_list(client, auth):
    info = make_block(client, auth, "block-1")
    assert info["block_id"].startswith("blk_")
    assert info["block_secret"]
    blocks = client.get("/api/v1/blocks", headers=auth).json()
    assert len(blocks) == 1
    assert blocks[0]["name"] == "block-1"


def test_invalid_token_rejected(client, auth):
    resp = client.post("/api/v1/blocks/pair", json={"token": "bad", "name": "rogue"})
    assert resp.status_code == 403


def test_token_is_single_use(client, auth):
    token = client.post("/api/v1/blocks", json={"name": "b"}, headers=auth).json()["pairing_token"]
    first = client.post("/api/v1/blocks/pair", json={"token": token, "name": "b"})
    assert first.status_code == 200
    second = client.post("/api/v1/blocks/pair", json={"token": token, "name": "b2"})
    assert second.status_code == 403


def test_revoke_rotates_secret(client, auth):
    info = make_block(client, auth)
    resp = client.post(f"/api/v1/blocks/{info['block_id']}/revoke", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["block_secret"] != info["block_secret"]


def test_remove_block(client, auth):
    info = make_block(client, auth)
    assert client.delete(f"/api/v1/blocks/{info['block_id']}", headers=auth).status_code == 200
    assert client.get("/api/v1/blocks", headers=auth).json() == []
