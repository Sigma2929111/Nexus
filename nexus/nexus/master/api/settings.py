"""Cluster settings: display name and the public MASTER address used in
block install commands. Persisted in the machine config file.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexus.master.core.state import get_config
from nexus.master.security.auth import require_admin

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    cluster_name: Optional[str] = None
    public_url: Optional[str] = None


def _payload(config) -> dict:
    return {
        "cluster_name": config.cluster_name,
        "public_url": config.public_url,
        "heartbeat_interval": config.heartbeat_interval,
        "offline_after": config.offline_after,
        "role": config.role,
    }


@router.get("")
def get_settings(actor: str = Depends(require_admin)) -> dict:
    return _payload(get_config())


@router.put("")
def update_settings(body: SettingsUpdate, actor: str = Depends(require_admin)) -> dict:
    config = get_config()
    if body.cluster_name is not None:
        name = body.cluster_name.strip()
        if not name:
            raise HTTPException(400, "cluster name cannot be empty")
        config.cluster_name = name[:64]
    if body.public_url is not None:
        url = body.public_url.strip()
        config.public_url = url.rstrip("/") or None
    config.save()
    return _payload(config)
