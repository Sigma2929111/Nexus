"""Helpers for issuing commands to a connected BLOCK agent."""
from __future__ import annotations

import asyncio

from nexus.master.core import state
from nexus.shared.security import generate_token


class AgentUnavailable(Exception):
    pass


async def call_agent(block_id: str, action: str, payload: dict | None = None, timeout: float = 15.0) -> dict:
    ws = state.get_connection(block_id)
    if ws is None:
        raise AgentUnavailable(f"block {block_id} is not connected")
    request_id = generate_token(8)
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    state.add_pending(request_id, future)
    await ws.send_json(
        {
            "type": "command",
            "data": {"request_id": request_id, "action": action, "payload": payload or {}},
        }
    )
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        raise AgentUnavailable(f"block {block_id} did not answer {action} in time")
    finally:
        state.drop_pending(request_id)
