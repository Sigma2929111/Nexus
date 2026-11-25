"""Process-wide runtime state for the MASTER."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from nexus.shared.config import NexusConfig

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import WebSocket

_config: Optional[NexusConfig] = None
_connections: dict[str, "WebSocket"] = {}
_pending: dict[str, "asyncio.Future"] = {}


def get_config() -> NexusConfig:
    global _config
    if _config is None:
        _config = NexusConfig.load()
    return _config


def set_config(config: NexusConfig) -> None:
    global _config
    _config = config


def register_connection(block_id: str, ws: "WebSocket") -> None:
    _connections[block_id] = ws


def drop_connection(block_id: str) -> None:
    _connections.pop(block_id, None)


def get_connection(block_id: str) -> Optional["WebSocket"]:
    return _connections.get(block_id)


def is_connected(block_id: str) -> bool:
    return block_id in _connections


def connected_ids() -> list[str]:
    return list(_connections.keys())


def add_pending(request_id: str, future: "asyncio.Future") -> None:
    _pending[request_id] = future


def resolve_pending(request_id: str, result: dict) -> None:
    fut = _pending.pop(request_id, None)
    if fut is not None and not fut.done():
        fut.set_result(result)


def drop_pending(request_id: str) -> None:
    _pending.pop(request_id, None)
