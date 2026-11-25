"""Cluster-wide task execution: run a command on one or all blocks."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.master.core.commands import AgentUnavailable, call_agent
from nexus.master.core.db import session_scope
from nexus.master.registry import registry as reg
from nexus.master.security.auth import require_admin
from nexus.shared.models import BlockStatus
from nexus.shared.protocol import CMD_CLUSTER_EXEC

router = APIRouter(prefix="/api/v1/cluster", tags=["cluster"])


class ClusterExecRequest(BaseModel):
    command: str
    block_ids: Optional[list[str]] = None
    cwd: Optional[str] = None
    timeout: float = 60.0
    env: dict[str, str] = Field(default_factory=dict)


@router.post("/exec")
async def cluster_exec(body: ClusterExecRequest, actor: str = Depends(require_admin)) -> dict:
    if not body.command.strip():
        raise HTTPException(400, "empty command")
    timeout = max(1.0, min(float(body.timeout), 300.0))

    with session_scope() as session:
        blocks = reg.list_blocks(session)

    if body.block_ids:
        wanted = set(body.block_ids)
        targets = [b for b in blocks if b.id in wanted]
    else:
        targets = [b for b in blocks if b.status == BlockStatus.ONLINE]
    if not targets:
        raise HTTPException(400, "no online blocks to run on")

    payload = {
        "command": body.command,
        "cwd": body.cwd or None,
        "timeout": timeout,
        "env": body.env,
    }

    async def run(block) -> dict:
        try:
            result = await call_agent(
                block.id, CMD_CLUSTER_EXEC, payload, timeout=timeout + 10.0
            )
            return {"block_id": block.id, "block_name": block.name, **result}
        except AgentUnavailable as exc:
            return {
                "block_id": block.id,
                "block_name": block.name,
                "ok": False,
                "error": str(exc),
                "output": "",
            }

    results = await asyncio.gather(*(run(b) for b in targets))
    with session_scope() as session:
        reg.audit(session, actor, "cluster.exec", f"{len(targets)} blocks: {body.command[:120]}")
        session.commit()
    return {"command": body.command, "results": results}
