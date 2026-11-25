from conftest import make_block
from nexus.shared.models import ResourceSnapshot


def test_agent_ws_heartbeat_marks_online(client, auth):
    info = make_block(client, auth, "ws-block")
    bid, secret = info["block_id"], info["block_secret"]
    snap = ResourceSnapshot(cpu_cores=8, ram_total_mb=32000, disk_total_mb=200000).model_dump()
    with client.websocket_connect("/api/v1/agent/ws") as ws:
        ws.send_json({"type": "hello", "data": {"block_id": bid, "secret": secret}})
        assert ws.receive_json()["type"] == "hello_ok"
        ws.send_json(
            {
                "type": "heartbeat",
                "data": {"block_id": bid, "secret": secret, "snapshot": snap, "apps": []},
            }
        )
        assert ws.receive_json()["type"] == "heartbeat_ack"
        blocks = client.get("/api/v1/blocks", headers=auth).json()
        assert blocks[0]["status"] == "ONLINE"
        assert blocks[0]["quotas"]["cpu"]["physical"] == 8
        assert blocks[0]["quotas"]["ram"]["physical"] == 32000


def test_agent_ws_rejects_bad_secret(client, auth):
    info = make_block(client, auth, "ws-block")
    with client.websocket_connect("/api/v1/agent/ws") as ws:
        ws.send_json({"type": "hello", "data": {"block_id": info["block_id"], "secret": "wrong"}})
        msg = ws.receive_json()
        assert msg["type"] == "error"
