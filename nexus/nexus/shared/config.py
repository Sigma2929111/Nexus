"""Runtime configuration and filesystem layout.

All state lives under ``NEXUS_HOME`` (default ``~/.nexus``) so the platform
never needs root and never writes outside the user's home directory.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


def nexus_home() -> Path:
    return Path(os.environ.get("NEXUS_HOME", Path.home() / ".nexus")).expanduser()


class Paths(BaseModel):
    home: Path
    config: Path
    db: Path
    tls_dir: Path
    logs: Path
    apps: Path
    secrets: Path

    @classmethod
    def build(cls) -> "Paths":
        home = nexus_home()
        return cls(
            home=home,
            config=home / "config.json",
            db=home / "nexus.db",
            tls_dir=home / "tls",
            logs=home / "logs",
            apps=home / "apps",
            secrets=home / "secrets",
        )

    def ensure(self) -> None:
        for d in (self.home, self.tls_dir, self.logs, self.apps, self.secrets):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.secrets, 0o700)
        except OSError:
            pass


class NexusConfig(BaseModel):
    """Persisted configuration for a single machine."""

    role: str = Field(default="unset", description="unset | master | block")
    host: str = "0.0.0.0"
    port: int = 8787
    public_url: Optional[str] = None
    cluster_name: str = "NEXUS Cloud"
    admin_password_hash: Optional[str] = None
    admin_password_salt: Optional[str] = None
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    master_url: Optional[str] = None
    block_id: Optional[str] = None
    block_secret: Optional[str] = None
    block_name: Optional[str] = None
    seed_masters: list[str] = Field(default_factory=list)
    heartbeat_interval: int = 10
    offline_after: int = 45
    mdns_enabled: bool = True

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "NexusConfig":
        path = path or Paths.build().config
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return cls()

    def save(self, path: Optional[Path] = None) -> None:
        path = path or Paths.build().config
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(), indent=2))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}
