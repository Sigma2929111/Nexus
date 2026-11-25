"""MASTER authentication helpers: admin password + JWT session tokens."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nexus.shared.config import NexusConfig
from nexus.shared.security import issue_jwt, verify_jwt

_bearer = HTTPBearer(auto_error=False)


def make_token(config: NexusConfig) -> str:
    return issue_jwt("admin", config.jwt_secret, ttl_hours=12)


def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    payload = verify_jwt(creds.credentials, _current_config().jwt_secret)
    if not payload or payload.get("sub") != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return "admin"


def _current_config() -> NexusConfig:
    from nexus.master.core.state import get_config

    return get_config()
