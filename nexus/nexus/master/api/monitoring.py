"""Monitoring and overview endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlmodel import select

from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from nexus.master.core.state import get_config
from nexus.master.registry import registry as reg
from nexus.master.security.auth import require_admin
from nexus.shared.models import BlockStatus

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "nexus-master"}


@router.get("/overview")
def overview(actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        blocks = reg.list_blocks(session)
        apps = session.exec(select(m.Application)).all()
    totals = {
        "cpu_offered": 0.0,
        "cpu_allocated": 0.0,
        "ram_offered": 0.0,
        "ram_allocated": 0.0,
        "disk_offered": 0.0,
        "disk_allocated": 0.0,
        "gpu_offered": 0.0,
        "gpu_allocated": 0.0,
        "cpu_physical": 0.0,
        "ram_physical": 0.0,
        "disk_physical": 0.0,
        "gpu_physical": 0.0,
    }
    for b in blocks:
        totals["cpu_offered"] += b.quotas.cpu.offered
        totals["cpu_allocated"] += b.quotas.cpu.allocated
        totals["ram_offered"] += b.quotas.ram.offered
        totals["ram_allocated"] += b.quotas.ram.allocated
        totals["disk_offered"] += b.quotas.disk.offered
        totals["disk_allocated"] += b.quotas.disk.allocated
        totals["gpu_offered"] += b.quotas.gpu.offered
        totals["gpu_allocated"] += b.quotas.gpu.allocated
        totals["cpu_physical"] += b.quotas.cpu.physical
        totals["ram_physical"] += b.quotas.ram.physical
        totals["disk_physical"] += b.quotas.disk.physical
        totals["gpu_physical"] += b.quotas.gpu.physical
    return {
        "cluster_name": get_config().cluster_name,
        "master_url": get_config().public_url,
        "blocks_total": len(blocks),
        "blocks_online": sum(1 for b in blocks if b.status == BlockStatus.ONLINE),
        "blocks_offline": sum(1 for b in blocks if b.status == BlockStatus.OFFLINE),
        "blocks_pending": sum(1 for b in blocks if b.status == BlockStatus.PENDING),
        "apps_total": len(apps),
        "apps_running": sum(1 for a in apps if a.status == "RUNNING"),
        "totals": totals,
        "blocks": [b.model_dump() for b in blocks],
    }


@router.get("/audit")
def audit(actor: str = Depends(require_admin)) -> list[dict]:
    with session_scope() as session:
        rows = reg.audit_log(session)
        return [
            {"ts": r.ts, "actor": r.actor, "action": r.action, "detail": r.detail} for r in rows
        ]
