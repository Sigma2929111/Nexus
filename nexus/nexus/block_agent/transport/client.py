"""WebSocket transport used by a BLOCK to reach its MASTER."""
from __future__ import annotations

import ssl
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import websockets

from nexus.shared.logging import get_logger

log = get_logger("transport")


def to_ws_url(master_url: str) -> str:
    parsed = urlparse(master_url if "://" in master_url else f"https://{master_url}")
    scheme = "wss" if parsed.scheme in ("https", "wss") else "ws"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if scheme == "wss" else 80)
    prefix = parsed.path.rstrip("/")
    suffix = "/api/v1/agent/ws"
    if prefix.endswith(suffix):
        prefix = prefix[: -len(suffix)]
    netloc = host if port in (80, 443) else f"{host}:{port}"
    return f"{scheme}://{netloc}{prefix}{suffix}"


def build_ssl_context(master_url: str, ca_path: Optional[str] = None) -> Optional[ssl.SSLContext]:
    if not master_url.startswith(("https", "wss")):
        return None
    if ca_path and Path(ca_path).exists():
        ctx = ssl.create_default_context(cafile=ca_path)
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    log.warning(
        "TLS verification disabled (no CA provided). Provide --ca <master.crt> to pin the MASTER certificate."
    )
    return ctx


class AgentTransport:
    def __init__(self, master_url: str, ca_path: Optional[str] = None) -> None:
        self.master_url = master_url
        self.url = to_ws_url(master_url)
        self.ssl = build_ssl_context(master_url, ca_path)
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.url, ssl=self.ssl, ping_interval=20, ping_timeout=20)
        return self.ws

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
