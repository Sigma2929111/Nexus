"""Agent WebSocket endpoint (direct MASTER <-> BLOCK connection)."""
from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nexus.master.core import models_db as m
from nexus.master.core import state
from nexus.master.core.db import session_scope
from nexus.master.registry import registry as reg
from nexus.shared.models import BlockStatus, HeartbeatPayload
from nexus.shared.protocol import (
    MSG_COMMAND_RESULT,
    MSG_ERROR,
    MSG_HEARTBEAT,
    MSG_HEARTBEAT_ACK,
    MSG_HELLO,
    MSG_HELLO_OK,
)
from nexus.shared.logging import get_logger

router = APIRouter()
log = get_logger("ws")


@router.websocket("/api/v1/agent/ws")
async def agent_ws(ws: WebSocket) -> None:
    await ws.accept()
    block_id = None
    try:
        first = await ws.receive_json()
        if first.get("type") != MSG_HELLO:
            await ws.send_json({"type": MSG_ERROR, "data": {"error": "expected hello"}})
            await ws.close(code=1008)
            return
        data = first.get("data", {})
        block_id = data.get("block_id")
        secret = data.get("secret")
        with session_scope() as session:
            try:
                block = reg.authenticate(session, block_id, secret)
            except reg.RegistryError as exc:
                await ws.send_json({"type": MSG_ERROR, "data": {"error": str(exc)}})
                await ws.close(code=1008)
                return
            block.status = BlockStatus.ONLINE.value
            session.add(block)
            session.commit()
        state.register_connection(block_id, ws)
        await ws.send_json({"type": MSG_HELLO_OK, "data": {"block_id": block_id}})
        log.info("block %s connected", block_id)

        while True:
            message = await ws.receive_json()
            mtype = message.get("type")
            mdata = message.get("data", {})
            if mtype == MSG_HEARTBEAT:
                try:
                    payload = HeartbeatPayload(**mdata)
                    with session_scope() as session:
                        reg.heartbeat(session, payload)
                    await ws.send_json({"type": MSG_HEARTBEAT_ACK, "data": {}})
                except Exception as exc:  # noqa: BLE001
                    await ws.send_json({"type": MSG_ERROR, "data": {"error": str(exc)}})
            elif mtype == MSG_COMMAND_RESULT:
                request_id = mdata.get("request_id")
                if request_id:
                    state.resolve_pending(request_id, mdata.get("result", {}))
            elif mtype == MSG_ERROR:
                log.warning("block %s error: %s", block_id, mdata)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws error for %s: %s", block_id, exc)
    finally:
        if block_id:
            state.drop_connection(block_id)
            with session_scope() as session:
                block = session.get(m.Block, block_id)
                if block and block.status == BlockStatus.ONLINE.value:
                    block.status = BlockStatus.OFFLINE.value
                    session.add(block)
                    session.commit()
            log.info("block %s disconnected", block_id)
