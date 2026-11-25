"""Authentication endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from nexus.master.core.state import get_config
from nexus.master.security.auth import make_token, require_admin
from nexus.shared.models import LoginRequest, LoginResponse
from nexus.shared.security import verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    config = get_config()
    ok = False
    if config.admin_password_hash and config.admin_password_salt:
        ok = verify_password(body.password, config.admin_password_hash, config.admin_password_salt)
    env_pw = os.environ.get("NEXUS_ADMIN_PASSWORD")
    if not ok and env_pw and body.password == env_pw:
        ok = True
    if not ok:
        raise HTTPException(401, "invalid password")
    return LoginResponse(token=make_token(config), expires_in=12 * 3600)


@router.get("/me")
def me(actor: str = Depends(require_admin)) -> dict:
    return {"actor": actor}
