from nexus.block_agent.transport.client import to_ws_url


def test_to_ws_url_public_domain():
    assert to_ws_url("https://demo.trycloudflare.com") == "wss://demo.trycloudflare.com/api/v1/agent/ws"


def test_to_ws_url_keeps_proxy_prefix():
    assert (
        to_ws_url("http://51.158.253.74:45137/proxy/8787/")
        == "ws://51.158.253.74:45137/proxy/8787/api/v1/agent/ws"
    )


def test_to_ws_url_local_port():
    assert to_ws_url("http://127.0.0.1:8787") == "ws://127.0.0.1:8787/api/v1/agent/ws"
