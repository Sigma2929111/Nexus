"""SQLModel table definitions for the MASTER."""
from __future__ import annotations

import time
from typing import Optional

from sqlmodel import Field, SQLModel


def now() -> float:
    return time.time()


class Block(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    ip: Optional[str] = None
    port: Optional[int] = None
    description: Optional[str] = None
    secret_hash: str
    status: str = "PENDING"
    approved: bool = False
    last_heartbeat: Optional[float] = None
    agent_version: Optional[str] = None
    offers_json: str = "{}"
    physical_json: str = "{}"
    snapshot_json: str = "{}"
    created_at: float = Field(default_factory=now)
    updated_at: float = Field(default_factory=now)


class PairingToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True)
    note: Optional[str] = None
    created_at: float = Field(default_factory=now)
    used: bool = False


class Application(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    kind: str = "process"
    block_id: Optional[str] = Field(default=None, index=True)
    spec_json: str = "{}"
    status: str = "CREATED"
    created_at: float = Field(default_factory=now)
    updated_at: float = Field(default_factory=now)


class AppRuntime(SQLModel, table=True):
    app_id: str = Field(primary_key=True)
    block_id: Optional[str] = Field(default=None, index=True)
    status: str = "UNKNOWN"
    pid: Optional[int] = None
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    updated_at: float = Field(default_factory=now)


class Metric(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: str = Field(index=True)
    captured_at: float = Field(default_factory=now)
    data_json: str = "{}"


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: float = Field(default_factory=now)
    actor: str = "system"
    action: str
    detail: str = ""
