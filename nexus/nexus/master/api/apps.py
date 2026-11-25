"""Application hosting endpoints."""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexus.master.core import models_db as m
from nexus.master.core.commands import AgentUnavailable, call_agent
from nexus.master.core.db import session_scope
from nexus.master.registry import registry as reg
from nexus.master.scheduler import scheduler
from nexus.master.security.auth import require_admin
from nexus.shared.models import AppSpec
from nexus.shared.protocol import (
    CMD_APP_CREATE,
    CMD_APP_DELETE,
    CMD_APP_EXEC,
    CMD_APP_LOGS,
    CMD_APP_RESTART,
    CMD_APP_START,
    CMD_APP_STOP,
    CMD_FS_DELETE,
    CMD_FS_LIST,
    CMD_FS_MKDIR,
    CMD_FS_READ,
    CMD_FS_RENAME,
    CMD_FS_WRITE,
)
from nexus.shared.presets import PRESETS
from nexus.shared.security import generate_token

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])
presets_router = APIRouter(prefix="/api/v1/presets", tags=["presets"])


@presets_router.get("")
def list_presets(actor: str = Depends(require_admin)) -> list[dict]:
    return [p.model_dump() for p in PRESETS]


class CreateAppRequest(BaseModel):
    spec: AppSpec
    auto_place: bool = True
    start: bool = True


def _app_public(row: m.Application, runtime: Optional[m.AppRuntime] = None) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "block_id": row.block_id,
        "status": runtime.status if runtime else row.status,
        "pid": runtime.pid if runtime else None,
        "cpu_percent": runtime.cpu_percent if runtime else 0.0,
        "ram_mb": runtime.ram_mb if runtime else 0.0,
        "spec": json.loads(row.spec_json or "{}"),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_apps(actor: str = Depends(require_admin)) -> list[dict]:
    from sqlmodel import select

    with session_scope() as session:
        rows = session.exec(select(m.Application).order_by(m.Application.created_at)).all()
        runtimes = {r.app_id: r for r in session.exec(select(m.AppRuntime)).all()}
        return [_app_public(r, runtimes.get(r.id)) for r in rows]


@router.post("")
async def create_app(body: CreateAppRequest, actor: str = Depends(require_admin)) -> dict:
    spec = body.spec
    block_id = spec.block_id
    with session_scope() as session:
        if not block_id and body.auto_place:
            block_id, reasons = scheduler.choose_block(session, spec)
            if not block_id:
                raise HTTPException(409, {"error": "no block can host this app", "reasons": reasons})
        if not block_id:
            raise HTTPException(400, "block_id required when auto_place is false")
        try:
            reg.get_block(session, block_id)
        except reg.RegistryError as exc:
            raise HTTPException(exc.code, str(exc))
        block_row = session.get(m.Block, block_id)
        if block_row is not None:
            missing = scheduler.missing_capabilities(spec, block_row)
            if missing:
                raise HTTPException(
                    400,
                    f"block '{block_row.name}' is missing: {', '.join(missing)}. "
                    "Pick another block or use a preset that this block supports.",
                )
        spec.block_id = block_id
        app_id = f"app_{generate_token(8)}"
        row = m.Application(
            id=app_id,
            name=spec.name,
            kind=spec.kind,
            block_id=block_id,
            spec_json=spec.model_dump_json(),
            status="CREATED",
        )
        session.add(row)
        session.add(m.AppRuntime(app_id=app_id, block_id=block_id, status="CREATING"))
        reg.audit(session, actor, "app.create", f"{app_id} on {block_id}")
        session.commit()
    try:
        result = await call_agent(
            block_id,
            CMD_APP_CREATE,
            {"app_id": app_id, "spec": spec.model_dump(), "start": body.start},
        )
    except AgentUnavailable as exc:
        with session_scope() as session:
            row = session.get(m.Application, app_id)
            if row:
                session.delete(row)
            runtime = session.get(m.AppRuntime, app_id)
            if runtime:
                session.delete(runtime)
            session.commit()
        raise HTTPException(409, str(exc))
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        runtime = session.get(m.AppRuntime, app_id)
        ok = bool(result.get("ok"))
        final_status = ("RUNNING" if body.start else "CREATED") if ok else "ERROR"
        if row:
            row.status = final_status
            row.updated_at = time.time()
            session.add(row)
        if runtime:
            runtime.status = final_status
            runtime.updated_at = time.time()
            session.add(runtime)
        if not ok:
            if row:
                session.delete(row)
            if runtime:
                session.delete(runtime)
            reg.audit(session, actor, "app.create.failed", f"{app_id}: {result.get('error')}")
            session.commit()
    if not ok:
        raise HTTPException(400, result.get("error") or "failed to create the app")
    return {"app_id": app_id, "block_id": block_id, "result": result}


async def _app_action(app_id: str, action: str, payload: dict | None = None) -> dict:
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row is None:
            raise HTTPException(404, "app not found")
        block_id = row.block_id
    if not block_id:
        raise HTTPException(409, "app has no assigned block")
    try:
        result = await call_agent(block_id, action, {"app_id": app_id, **(payload or {})})
    except AgentUnavailable as exc:
        raise HTTPException(409, str(exc))
    status_map = {
        CMD_APP_START: "RUNNING",
        CMD_APP_STOP: "STOPPED",
        CMD_APP_RESTART: "RUNNING",
    }
    if action in status_map:
        with session_scope() as session:
            new_status = status_map[action] if result.get("ok") else "ERROR"
            row = session.get(m.Application, app_id)
            if row:
                row.status = new_status
                row.updated_at = time.time()
                session.add(row)
            runtime = session.get(m.AppRuntime, app_id)
            if runtime:
                runtime.status = new_status
                runtime.updated_at = time.time()
                session.add(runtime)
            session.commit()
    return result


@router.post("/{app_id}/start")
async def start_app(app_id: str, actor: str = Depends(require_admin)) -> dict:
    return await _app_action(app_id, CMD_APP_START)


@router.post("/{app_id}/stop")
async def stop_app(app_id: str, actor: str = Depends(require_admin)) -> dict:
    return await _app_action(app_id, CMD_APP_STOP)


@router.post("/{app_id}/restart")
async def restart_app(app_id: str, actor: str = Depends(require_admin)) -> dict:
    return await _app_action(app_id, CMD_APP_RESTART)


@router.get("/{app_id}/logs")
async def app_logs(app_id: str, actor: str = Depends(require_admin)) -> dict:
    return await _app_action(app_id, CMD_APP_LOGS)


@router.delete("/{app_id}")
async def delete_app(app_id: str, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row is None:
            raise HTTPException(404, "app not found")
        block_id = row.block_id
    if block_id:
        try:
            await call_agent(block_id, CMD_APP_DELETE, {"app_id": app_id})
        except AgentUnavailable:
            pass
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row:
            session.delete(row)
            reg.audit(session, actor, "app.delete", app_id)
            session.commit()
    return {"deleted": app_id}


async def _agent_call(app_id: str, action: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row is None:
            raise HTTPException(404, "app not found")
        block_id = row.block_id
    if not block_id:
        raise HTTPException(409, "app has no assigned block")
    try:
        return await call_agent(block_id, action, {"app_id": app_id, **(payload or {})}, timeout=timeout)
    except AgentUnavailable as exc:
        raise HTTPException(409, str(exc))


@router.get("/{app_id}")
def get_app(app_id: str, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row is None:
            raise HTTPException(404, "app not found")
        runtime = session.get(m.AppRuntime, app_id)
        return _app_public(row, runtime)


class UpdateAppRequest(BaseModel):
    name: Optional[str] = None
    command: Optional[str] = None
    image: Optional[str] = None
    env: Optional[dict[str, str]] = None
    ports: Optional[list[int]] = None
    cpu_limit: Optional[float] = None
    ram_limit_mb: Optional[float] = None
    disk_limit_mb: Optional[float] = None
    restart: bool = False


@router.patch("/{app_id}")
async def update_app(app_id: str, body: UpdateAppRequest, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        if row is None:
            raise HTTPException(404, "app not found")
        spec_data = json.loads(row.spec_json or "{}")
        updates = body.model_dump(exclude_none=True, exclude={"restart"})
        spec_data.update(updates)
        try:
            spec = AppSpec(**spec_data)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"invalid spec: {exc}")
        row.spec_json = spec.model_dump_json()
        row.name = spec.name
        row.updated_at = time.time()
        session.add(row)
        reg.audit(session, actor, "app.update", app_id)
        session.commit()
    if body.restart:
        res = await _agent_call(app_id, CMD_APP_RESTART)
        new_status = "RUNNING" if res.get("ok") else "ERROR"
        with session_scope() as session:
            row = session.get(m.Application, app_id)
            if row:
                row.status = new_status
                row.updated_at = time.time()
                session.add(row)
            runtime = session.get(m.AppRuntime, app_id)
            if runtime:
                runtime.status = new_status
                runtime.updated_at = time.time()
                session.add(runtime)
            session.commit()
    with session_scope() as session:
        row = session.get(m.Application, app_id)
        runtime = session.get(m.AppRuntime, app_id)
        return _app_public(row, runtime)


@router.get("/{app_id}/files")
async def list_files(app_id: str, path: str = "", actor: str = Depends(require_admin)) -> dict:
    return await _agent_call(app_id, CMD_FS_LIST, {"path": path})


@router.get("/{app_id}/files/content")
async def read_file(app_id: str, path: str, actor: str = Depends(require_admin)) -> dict:
    return await _agent_call(app_id, CMD_FS_READ, {"path": path})


class FileWriteRequest(BaseModel):
    path: str
    content: str = ""


@router.put("/{app_id}/files/content")
async def write_file(app_id: str, body: FileWriteRequest, actor: str = Depends(require_admin)) -> dict:
    result = await _agent_call(app_id, CMD_FS_WRITE, {"path": body.path, "content": body.content})
    if result.get("ok"):
        with session_scope() as session:
            reg.audit(session, actor, "file.write", f"{app_id}:{body.path}")
            session.commit()
    return result


@router.delete("/{app_id}/files")
async def delete_file(app_id: str, path: str, actor: str = Depends(require_admin)) -> dict:
    result = await _agent_call(app_id, CMD_FS_DELETE, {"path": path})
    if result.get("ok"):
        with session_scope() as session:
            reg.audit(session, actor, "file.delete", f"{app_id}:{path}")
            session.commit()
    return result


class PathRequest(BaseModel):
    path: str


@router.post("/{app_id}/files/mkdir")
async def make_dir(app_id: str, body: PathRequest, actor: str = Depends(require_admin)) -> dict:
    return await _agent_call(app_id, CMD_FS_MKDIR, {"path": body.path})


class RenameRequest(BaseModel):
    path: str
    new_path: str


@router.post("/{app_id}/files/rename")
async def rename_path(app_id: str, body: RenameRequest, actor: str = Depends(require_admin)) -> dict:
    return await _agent_call(app_id, CMD_FS_RENAME, {"path": body.path, "new_path": body.new_path})


class ExecRequest(BaseModel):
    command: str
    timeout: float = 20.0


@router.post("/{app_id}/exec")
async def exec_command(app_id: str, body: ExecRequest, actor: str = Depends(require_admin)) -> dict:
    result = await _agent_call(
        app_id,
        CMD_APP_EXEC,
        {"command": body.command, "timeout": min(body.timeout, 60.0)},
        timeout=min(body.timeout, 60.0) + 5.0,
    )
    with session_scope() as session:
        reg.audit(session, actor, "app.exec", f"{app_id}: {body.command[:120]}")
        session.commit()
    return result
