"""Block management endpoints."""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from nexus.master.core.state import drop_connection, get_connection
from nexus.master.registry import registry as reg
from nexus.master.security.auth import require_admin
from nexus.shared.models import (
    BlockCreate,
    BlockPublic,
    BlockStatus,
    PairRequest,
    PairResponse,
    ResourceOfferSet,
    ResourceUpdate,
)
from nexus.shared.protocol import CMD_AGENT_RESTART

router = APIRouter(prefix="/api/v1/blocks", tags=["blocks"])


@router.get("", response_model=list[BlockPublic])
def list_blocks(actor: str = Depends(require_admin)) -> list[BlockPublic]:
    with session_scope() as session:
        return reg.list_blocks(session)


@router.post("/pair", response_model=PairResponse)
def pair(req: PairRequest, request: Request) -> PairResponse:
    client_ip = request.client.host if request.client else None
    with session_scope() as session:
        try:
            response, _ = reg.pair_block(session, req, client_ip)
            return response
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("")
def create_block(body: BlockCreate, actor: str = Depends(require_admin)) -> dict:
    """Create a pending block entry and issue a single-use pairing token."""
    with session_scope() as session:
        token = reg.create_pairing_token(session, note=body.name)
        return {
            "pairing_token": token,
            "name": body.name,
            "ip": body.ip,
            "port": body.port,
            "hint": "Run: nexus up block --master <this-master-url> --token <token>",
        }


@router.get("/{block_id}", response_model=BlockPublic)
def get_block(block_id: str, actor: str = Depends(require_admin)) -> BlockPublic:
    with session_scope() as session:
        try:
            block = reg.get_block(session, block_id)
            return reg.block_public(session, block)
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.put("/{block_id}/resources", response_model=BlockPublic)
def update_resources(block_id: str, body: ResourceUpdate, actor: str = Depends(require_admin)) -> BlockPublic:
    with session_scope() as session:
        try:
            block = reg.update_offers(session, block_id, body.offers)
            return reg.block_public(session, block)
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("/{block_id}/approve", response_model=BlockPublic)
def approve(block_id: str, actor: str = Depends(require_admin)) -> BlockPublic:
    with session_scope() as session:
        try:
            return reg.block_public(session, reg.approve(session, block_id))
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("/{block_id}/disable", response_model=BlockPublic)
def disable(block_id: str, actor: str = Depends(require_admin)) -> BlockPublic:
    with session_scope() as session:
        try:
            block = reg.set_status(session, block_id, BlockStatus.DISABLED)
            return reg.block_public(session, block)
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("/{block_id}/enable", response_model=BlockPublic)
def enable(block_id: str, actor: str = Depends(require_admin)) -> BlockPublic:
    with session_scope() as session:
        try:
            return reg.block_public(session, reg.set_status(session, block_id, BlockStatus.CONNECTING))
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("/{block_id}/revoke")
def revoke(block_id: str, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        try:
            secret = reg.revoke(session, block_id)
            drop_connection(block_id)
            return {"block_id": block_id, "block_secret": secret}
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.delete("/{block_id}")
def remove(block_id: str, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        try:
            reg.remove(session, block_id)
            drop_connection(block_id)
            return {"removed": block_id}
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))


@router.post("/{block_id}/restart-agent")
async def restart_agent(block_id: str, actor: str = Depends(require_admin)) -> dict:
    ws = get_connection(block_id)
    if ws is None:
        raise HTTPException(409, "block is not connected")
    await ws.send_json({"type": "command", "data": {"action": CMD_AGENT_RESTART}})
    return {"sent": CMD_AGENT_RESTART}


@router.get("/{block_id}/metrics")
def get_metrics(block_id: str, actor: str = Depends(require_admin)) -> list[dict]:
    with session_scope() as session:
        return reg.metrics(session, block_id)


@router.get("/{block_id}/audit")
def block_audit(block_id: str, actor: str = Depends(require_admin)) -> list[dict]:
    with session_scope() as session:
        rows = session.exec(select(m.AuditLog).order_by(m.AuditLog.ts.desc()).limit(100)).all()
        return [
            {"ts": r.ts, "actor": r.actor, "action": r.action, "detail": r.detail}
            for r in rows
            if block_id in (r.detail or "") or block_id in (r.action or "")
        ]
