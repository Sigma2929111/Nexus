"""Block registry: pairing, authentication, heartbeat and lifecycle."""
from __future__ import annotations

import json
import time
from typing import Optional

from sqlmodel import Session, select

from nexus.master.core import models_db as m
from nexus.master.resource_manager import manager as rm
from nexus.shared.models import (
    AppSpec,
    BlockPublic,
    BlockStatus,
    HeartbeatPayload,
    PairRequest,
    PairResponse,
    ResourceOfferSet,
    ResourceQuotas,
)
from nexus.shared.security import generate_token, hash_secret

ACTIVE_APP_STATES = {"CREATED", "STARTING", "RUNNING"}


class RegistryError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def audit(session: Session, actor: str, action: str, detail: str = "") -> None:
    session.add(m.AuditLog(actor=actor, action=action, detail=detail))


def create_pairing_token(session: Session, note: Optional[str] = None) -> str:
    token = generate_token(24)
    session.add(m.PairingToken(token_hash=hash_secret(token), note=note))
    audit(session, "admin", "pairing_token.create", note or "")
    session.commit()
    return token


def _consume_token(session: Session, token: str) -> None:
    th = hash_secret(token)
    row = session.exec(select(m.PairingToken).where(m.PairingToken.token_hash == th)).first()
    if row is None:
        raise RegistryError("invalid pairing token", 403)
    if row.used:
        raise RegistryError("pairing token already used", 403)
    row.used = True
    session.add(row)


def _apps_for(session: Session, block_id: str) -> list[AppSpec]:
    rows = session.exec(
        select(m.Application).where(m.Application.block_id == block_id)
    ).all()
    specs: list[AppSpec] = []
    for row in rows:
        if row.status not in ACTIVE_APP_STATES:
            continue
        try:
            specs.append(AppSpec(**json.loads(row.spec_json)))
        except Exception:
            continue
    return specs


def block_public(session: Session, block: m.Block) -> BlockPublic:
    apps = _apps_for(session, block.id)
    quotas = rm.quotas_from_block(block, apps)
    try:
        offers = ResourceOfferSet(**json.loads(block.offers_json or "{}"))
    except Exception:
        offers = ResourceOfferSet()
    try:
        capabilities = json.loads(block.snapshot_json or "{}").get("capabilities", {}) or {}
    except Exception:
        capabilities = {}
    return BlockPublic(
        id=block.id,
        name=block.name,
        ip=block.ip,
        port=block.port,
        status=BlockStatus(block.status),
        description=block.description,
        last_heartbeat=block.last_heartbeat,
        agent_version=block.agent_version,
        quotas=quotas,
        offers=offers,
        capabilities=capabilities,
        app_count=len(apps),
        available=block.status == BlockStatus.ONLINE.value,
    )


def pair_block(session: Session, req: PairRequest, client_ip: Optional[str]) -> tuple[PairResponse, m.Block]:
    _consume_token(session, req.token)
    block_id = f"blk_{generate_token(8)}"
    secret = generate_token(32)
    block = m.Block(
        id=block_id,
        name=req.name or block_id,
        ip=req.ip or client_ip,
        port=req.port,
        description=req.description,
        secret_hash=hash_secret(secret),
        status=BlockStatus.CONNECTING.value,
        approved=True,
        agent_version=req.agent_version,
        offers_json=ResourceOfferSet().model_dump_json(),
        snapshot_json=req.snapshot.model_dump_json() if req.snapshot else "{}",
    )
    session.add(block)
    audit(session, "block", "block.pair", f"{block_id} from {block.ip}")
    session.commit()
    session.refresh(block)
    return (
        PairResponse(block_id=block_id, block_secret=secret, master_name="nexus-master"),
        block,
    )


def authenticate(session: Session, block_id: str, secret: str) -> m.Block:
    block = session.get(m.Block, block_id)
    if block is None:
        raise RegistryError("unknown block", 403)
    if not block.approved:
        raise RegistryError("block not approved", 403)
    if block.status == BlockStatus.DISABLED.value:
        raise RegistryError("block disabled", 403)
    if hash_secret(secret) != block.secret_hash:
        raise RegistryError("invalid block secret", 403)
    return block


def heartbeat(session: Session, payload: HeartbeatPayload) -> m.Block:
    block = authenticate(session, payload.block_id, payload.secret)
    block.snapshot_json = payload.snapshot.model_dump_json()
    block.last_heartbeat = payload.sent_at or time.time()
    block.agent_version = payload.agent_version
    if block.status != BlockStatus.DISABLED.value:
        block.status = BlockStatus.ONLINE.value
    block.updated_at = time.time()
    session.add(block)
    session.add(
        m.Metric(block_id=block.id, captured_at=block.last_heartbeat, data_json=payload.snapshot.model_dump_json())
    )
    for state in payload.apps:
        runtime = session.get(m.AppRuntime, state.app_id)
        if runtime is None:
            runtime = m.AppRuntime(app_id=state.app_id, block_id=block.id)
        runtime.block_id = block.id
        runtime.status = state.status
        runtime.pid = state.pid
        runtime.cpu_percent = state.cpu_percent
        runtime.ram_mb = state.ram_mb
        runtime.updated_at = time.time()
        session.add(runtime)
    session.commit()
    session.refresh(block)
    return block


def list_blocks(session: Session) -> list[BlockPublic]:
    rows = session.exec(select(m.Block).order_by(m.Block.created_at)).all()
    return [block_public(session, b) for b in rows]


def get_block(session: Session, block_id: str) -> m.Block:
    block = session.get(m.Block, block_id)
    if block is None:
        raise RegistryError("block not found", 404)
    return block


def update_offers(session: Session, block_id: str, offers: ResourceOfferSet) -> m.Block:
    block = get_block(session, block_id)
    block.offers_json = offers.model_dump_json()
    block.updated_at = time.time()
    session.add(block)
    audit(session, "admin", "block.resources", block_id)
    session.commit()
    session.refresh(block)
    return block


def set_status(session: Session, block_id: str, status: BlockStatus) -> m.Block:
    block = get_block(session, block_id)
    block.status = status.value
    block.updated_at = time.time()
    session.add(block)
    audit(session, "admin", "block.status", f"{block_id} -> {status.value}")
    session.commit()
    session.refresh(block)
    return block


def approve(session: Session, block_id: str) -> m.Block:
    block = get_block(session, block_id)
    block.approved = True
    session.add(block)
    audit(session, "admin", "block.approve", block_id)
    session.commit()
    session.refresh(block)
    return block


def remove(session: Session, block_id: str) -> None:
    block = get_block(session, block_id)
    session.delete(block)
    audit(session, "admin", "block.remove", block_id)
    session.commit()


def revoke(session: Session, block_id: str) -> str:
    block = get_block(session, block_id)
    secret = generate_token(32)
    block.secret_hash = hash_secret(secret)
    block.status = BlockStatus.OFFLINE.value
    block.updated_at = time.time()
    session.add(block)
    audit(session, "admin", "block.revoke", block_id)
    session.commit()
    return secret


def mark_offline_stale(session: Session, offline_after: int) -> list[str]:
    """Mark blocks offline when their last heartbeat is too old."""
    changed: list[str] = []
    now = time.time()
    rows = session.exec(select(m.Block)).all()
    for block in rows:
        if block.status != BlockStatus.ONLINE.value:
            continue
        if block.last_heartbeat is None or now - block.last_heartbeat > offline_after:
            block.status = BlockStatus.OFFLINE.value
            session.add(block)
            changed.append(block.id)
    if changed:
        session.commit()
    return changed


def metrics(session: Session, block_id: str, limit: int = 120) -> list[dict]:
    rows = session.exec(
        select(m.Metric)
        .where(m.Metric.block_id == block_id)
        .order_by(m.Metric.captured_at.desc())
        .limit(limit)
    ).all()
    out = []
    for row in reversed(rows):
        out.append({"t": row.captured_at, "data": json.loads(row.data_json)})
    return out


def audit_log(session: Session, limit: int = 200) -> list[m.AuditLog]:
    return list(session.exec(select(m.AuditLog).order_by(m.AuditLog.ts.desc()).limit(limit)).all())
