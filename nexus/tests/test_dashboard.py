import re

from nexus.master.core.app import DASHBOARD_DIST


def test_dashboard_dist_exists():
    assert (DASHBOARD_DIST / "index.html").exists(), "prebuilt dashboard dist is missing"


def test_dashboard_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert '<div id="root">' in resp.text


def test_spa_fallback(client):
    resp = client.get("/some/deep/route")
    assert resp.status_code == 200
    assert '<div id="root">' in resp.text


def test_dashboard_assets_served(client):
    index = client.get("/").text
    match = re.search(r'/assets/([^"]+\.js)', index)
    assert match, "no JS asset referenced in index.html"
    asset = client.get(f"/assets/{match.group(1)}")
    assert asset.status_code == 200
    assert len(asset.content) > 1000


def test_api_unknown_is_404_not_spa(client):
    assert client.get("/api/v1/does-not-exist").status_code == 404
