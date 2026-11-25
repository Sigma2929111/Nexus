"""Distributed inference planning endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import select

from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from nexus.master.resource_manager import manager as rm
from nexus.master.security.auth import require_admin
from nexus.inference.engine import BlockCapacity, ModelProfile, plan_pipeline
from nexus.shared.models import BlockStatus

router = APIRouter(prefix="/api/v1/inference", tags=["inference"])

PRESETS = {
    "llama-3-8b": ModelProfile(name="Llama-3-8B", layers=32, params_billion=8.0, dtype="fp16", context_len=4096, kv_cache_mb_per_1k_ctx=128),
    "llama-3-70b": ModelProfile(name="Llama-3-70B", layers=80, params_billion=70.0, dtype="fp16", context_len=4096, kv_cache_mb_per_1k_ctx=320),
    "mistral-7b": ModelProfile(name="Mistral-7B", layers=32, params_billion=7.0, dtype="fp16", context_len=8192, kv_cache_mb_per_1k_ctx=96),
    "qwen2-72b": ModelProfile(name="Qwen2-72B", layers=80, params_billion=72.0, dtype="fp16", context_len=4096, kv_cache_mb_per_1k_ctx=320),
}


class PlanRequest(BaseModel):
    preset: Optional[str] = None
    model: Optional[ModelProfile] = None
    block_ids: Optional[list[str]] = None


@router.get("/presets")
def presets(actor: str = Depends(require_admin)) -> dict:
    return {k: v.model_dump() for k, v in PRESETS.items()}


@router.post("/plan")
def plan(body: PlanRequest, actor: str = Depends(require_admin)) -> dict:
    model = body.model
    if model is None and body.preset:
        model = PRESETS.get(body.preset)
    if model is None:
        model = PRESETS["llama-3-8b"]

    with session_scope() as session:
        rows = session.exec(select(m.Block)).all()
        caps: list[BlockCapacity] = []
        for block in rows:
            if body.block_ids and block.id not in body.block_ids:
                continue
            snap = rm.parse_snapshot(block)
            vram_total = sum(g.vram_total_mb for g in snap.gpus)
            vram_used = sum(g.vram_used_mb for g in snap.gpus)
            caps.append(
                BlockCapacity(
                    block_id=block.id,
                    name=block.name,
                    online=block.status == BlockStatus.ONLINE.value,
                    gpu_count=len(snap.gpus),
                    vram_total_mb=vram_total,
                    vram_free_mb=max(vram_total - vram_used, 0.0),
                    net_rx_kbps=snap.net_rx_kbps,
                    net_tx_kbps=snap.net_tx_kbps,
                )
            )
    result = plan_pipeline(model, caps)
    return result.model_dump()
