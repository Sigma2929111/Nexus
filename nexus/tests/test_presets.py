from nexus.shared.presets import PRESETS, get_preset


def test_presets_endpoint(client, auth):
    resp = client.get("/api/v1/presets", headers=auth)
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert "nodejs" in ids and "minecraft" in ids and "custom" in ids


def test_presets_have_resources():
    for preset in PRESETS:
        assert preset.cpu > 0
        assert preset.ram_mb > 0
        assert preset.disk_mb > 0


def test_get_preset():
    assert get_preset("postgres").kind == "docker"
    assert get_preset("does-not-exist") is None
