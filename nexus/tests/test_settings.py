def test_settings_roundtrip(client, auth):
    resp = client.get("/api/v1/settings", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["cluster_name"] == "NEXUS Cloud"

    resp = client.put(
        "/api/v1/settings",
        json={"cluster_name": "Lab Cluster", "public_url": "https://panel.example.com/"},
        headers=auth,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cluster_name"] == "Lab Cluster"
    assert data["public_url"] == "https://panel.example.com"

    overview = client.get("/api/v1/overview", headers=auth).json()
    assert overview["cluster_name"] == "Lab Cluster"
    assert overview["master_url"] == "https://panel.example.com"


def test_settings_reject_empty_name(client, auth):
    resp = client.put("/api/v1/settings", json={"cluster_name": "  "}, headers=auth)
    assert resp.status_code == 400
