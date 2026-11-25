"""Wire protocol and domain models shared by MASTER and BLOCK agents."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BlockStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    MAINTENANCE = "MAINTENANCE"
    PENDING = "PENDING"


class ResourceKind(str, Enum):
    CPU = "cpu"
    RAM = "ram"
    DISK = "disk"
    GPU = "gpu"


class ResourceOffer(BaseModel):
    """What a block owner chooses to hand over to NEXUS for one resource kind."""

    enabled: bool = False
    full: bool = False
    amount: Optional[float] = None
    reserved_for_host: float = 0.0


class ResourceOfferSet(BaseModel):
    cpu: ResourceOffer = Field(default_factory=ResourceOffer)
    ram: ResourceOffer = Field(default_factory=ResourceOffer)
    disk: ResourceOffer = Field(default_factory=ResourceOffer)
    gpu: ResourceOffer = Field(default_factory=ResourceOffer)

    def as_map(self) -> dict[str, ResourceOffer]:
        return {"cpu": self.cpu, "ram": self.ram, "disk": self.disk, "gpu": self.gpu}


class ResourceQuota(BaseModel):
    physical: float = 0.0
    offered: float = 0.0
    allocated: float = 0.0
    available: float = 0.0
    reserved_for_host: float = 0.0


class ResourceQuotas(BaseModel):
    cpu: ResourceQuota = Field(default_factory=ResourceQuota)
    ram: ResourceQuota = Field(default_factory=ResourceQuota)
    disk: ResourceQuota = Field(default_factory=ResourceQuota)
    gpu: ResourceQuota = Field(default_factory=ResourceQuota)


class GpuInfo(BaseModel):
    index: int
    name: str
    vram_total_mb: float = 0.0
    vram_used_mb: float = 0.0


class ResourceSnapshot(BaseModel):
    cpu_cores: float = 0.0
    cpu_usage_percent: float = 0.0
    load_1: float = 0.0
    ram_total_mb: float = 0.0
    ram_used_mb: float = 0.0
    disk_total_mb: float = 0.0
    disk_used_mb: float = 0.0
    net_rx_kbps: float = 0.0
    net_tx_kbps: float = 0.0
    gpus: list[GpuInfo] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)
    captured_at: float = Field(default_factory=time.time)


class AppRuntimeState(BaseModel):
    app_id: str
    name: str
    status: str
    pid: Optional[int] = None
    cpu_percent: float = 0.0
    ram_mb: float = 0.0


class HeartbeatPayload(BaseModel):
    block_id: str
    secret: str
    snapshot: ResourceSnapshot
    apps: list[AppRuntimeState] = Field(default_factory=list)
    agent_version: str = "0.1.0"
    sent_at: float = Field(default_factory=time.time)


class PairRequest(BaseModel):
    token: str
    name: str
    ip: Optional[str] = None
    port: Optional[int] = None
    description: Optional[str] = None
    agent_version: str = "0.1.0"
    snapshot: Optional[ResourceSnapshot] = None


class PairResponse(BaseModel):
    block_id: str
    block_secret: str
    master_name: str
    heartbeat_interval: int = 10


class BlockCreate(BaseModel):
    name: str
    ip: Optional[str] = None
    port: Optional[int] = None
    pairing_token: Optional[str] = None
    description: Optional[str] = None


class ResourceUpdate(BaseModel):
    offers: ResourceOfferSet


class AppSpec(BaseModel):
    name: str
    kind: str = "process"
    preset: Optional[str] = None
    command: str = ""
    working_dir: Optional[str] = None
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    block_id: Optional[str] = None
    cpu_limit: Optional[float] = None
    ram_limit_mb: Optional[float] = None
    disk_limit_mb: Optional[float] = None
    image: Optional[str] = None


class AppCommand(BaseModel):
    action: str
    app: Optional[AppSpec] = None
    app_id: Optional[str] = None


class WsMessage(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class BlockPublic(BaseModel):
    id: str
    name: str
    ip: Optional[str] = None
    port: Optional[int] = None
    status: BlockStatus
    description: Optional[str] = None
    last_heartbeat: Optional[float] = None
    agent_version: Optional[str] = None
    quotas: ResourceQuotas = Field(default_factory=ResourceQuotas)
    offers: ResourceOfferSet = Field(default_factory=ResourceOfferSet)
    capabilities: dict[str, str] = Field(default_factory=dict)
    app_count: int = 0
    available: bool = False


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int
