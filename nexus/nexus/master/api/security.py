"""Security endpoints: pairing tokens and admin password."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import select

from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from nexus.master.core.state import get_config
from nexus.master.registry import registry as reg
from nexus.master.security.auth import require_admin
from nexus.shared.security import hash_password

router = APIRouter(prefix="/api/v1/security", tags=["security"])


class TokenRequest(BaseModel):
    note: Optional[str] = None


class PasswordRequest(BaseModel):
    password: str


@router.post("/tokens")
def create_token(body: TokenRequest, actor: str = Depends(require_admin)) -> dict:
    with session_scope() as session:
        token = reg.create_pairing_token(session, body.note)
        return {"pairing_token": token, "note": body.note}


@router.get("/tokens")
def list_tokens(actor: str = Depends(require_admin)) -> list[dict]:
    with session_scope() as session:
        rows = session.exec(select(m.PairingToken).order_by(m.PairingToken.created_at.desc())).all()
        return [
            {"id": r.id, "note": r.note, "created_at": r.created_at, "used": r.used}
            for r in rows
        ]


@router.post("/password")
def change_password(body: PasswordRequest, actor: str = Depends(require_admin)) -> dict:
    config = get_config()
    digest, salt = hash_password(body.password)
    config.admin_password_hash = digest
    config.admin_password_salt = salt
    config.save()
    return {"changed": True}
