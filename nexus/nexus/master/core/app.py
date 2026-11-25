"""MASTER FastAPI application factory."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nexus.master.api import apps, auth, blocks, cluster, inference, monitoring, security, settings, ws
from nexus.master.api import package as package_api
from nexus.master.core import state
from nexus.master.core.db import init_db, session_scope
from nexus.master.core.mdns import MdnsAdvertiser
from nexus.master.registry import registry as reg
from nexus.shared.config import NexusConfig
from nexus.shared.logging import get_logger

log = get_logger("app")

DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


async def _offline_watchdog() -> None:
    while True:
        config = state.get_config()
        interval = max(config.heartbeat_interval, 5)
        await asyncio.sleep(interval)
        try:
            with session_scope() as session:
                changed = reg.mark_offline_stale(session, config.offline_after)
            for block_id in changed:
                log.info("block %s marked OFFLINE (stale heartbeat)", block_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("watchdog error: %s", exc)


def create_app(config: Optional[NexusConfig] = None) -> FastAPI:
    if config is not None:
        state.set_config(config)
    init_db()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_offline_watchdog())
        advertiser = None
        config = state.get_config()
        if config.role == "master" and config.mdns_enabled:
            advertiser = MdnsAdvertiser(config.port)
            advertiser.start_in_background()
        log.info("NEXUS MASTER started")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if advertiser:
                advertiser.stop()

    app = FastAPI(title="NEXUS Cloud", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(blocks.router)
    app.include_router(apps.router)
    app.include_router(apps.presets_router)
    app.include_router(monitoring.router)
    app.include_router(security.router)
    app.include_router(settings.router)
    app.include_router(package_api.router)
    app.include_router(cluster.router)
    app.include_router(inference.router)
    app.include_router(ws.router)

    if DASHBOARD_DIST.exists():
        assets = DASHBOARD_DIST / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            candidate = DASHBOARD_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(DASHBOARD_DIST / "index.html")
    else:

        @app.get("/")
        def index() -> dict:
            return {
                "service": "NEXUS MASTER",
                "note": "dashboard not built yet; run `npm run build` in nexus/dashboard",
            }

    return app


app = create_app()
