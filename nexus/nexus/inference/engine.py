"""Distributed inference foundation.

This module implements *real* planning math for splitting one model across
several blocks (pipeline parallelism). It does NOT pretend that VRAM of
different machines becomes one GPU. Execution backends are intentionally
separated and honest about their requirements.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

DTYPE_BYTES = {"fp32": 4, "fp16": 2, "bf16": 2, "int8": 1, "int4": 0.5}


class ModelProfile(BaseModel):
    name: str
    layers: int
    params_billion: float
    dtype: str = "fp16"
    context_len: int = 2048
    kv_cache_mb_per_1k_ctx: float = 0.0
    overhead_factor: float = 1.15

    @property
    def bytes_per_param(self) -> float:
        return DTYPE_BYTES.get(self.dtype, 2)

    def weights_gb(self) -> float:
        return self.params_billion * 1e9 * self.bytes_per_param / (1024**3)

    def kv_cache_gb(self) -> float:
        return self.kv_cache_mb_per_1k_ctx * (self.context_len / 1000) / 1024

    def total_vram_gb(self) -> float:
        return (self.weights_gb() + self.kv_cache_gb()) * self.overhead_factor

    def per_layer_vram_mb(self) -> float:
        return self.total_vram_gb() * 1024 / max(self.layers, 1)


class BlockCapacity(BaseModel):
    block_id: str
    name: str
    online: bool
    gpu_count: int = 0
    vram_total_mb: float = 0.0
    vram_free_mb: float = 0.0
    net_rx_kbps: float = 0.0
    net_tx_kbps: float = 0.0

    @property
    def usable_vram_mb(self) -> float:
        if self.vram_total_mb <= 0:
            return 0.0
        return self.vram_free_mb if self.vram_free_mb > 0 else self.vram_total_mb


class PipelineStage(BaseModel):
    block_id: str
    block_name: str
    layer_start: int
    layer_end: int
    layers: int
    vram_needed_mb: float


class PipelinePlan(BaseModel):
    feasible: bool
    model: str
    strategy: str = "pipeline"
    stages: list[PipelineStage] = Field(default_factory=list)
    required_vram_gb: float = 0.0
    available_vram_gb: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: str = ""


def plan_pipeline(model: ModelProfile, blocks: list[BlockCapacity]) -> PipelinePlan:
    required_mb = model.total_vram_gb() * 1024
    usable = [b for b in blocks if b.online and b.usable_vram_mb > 0]
    available_mb = sum(b.usable_vram_mb for b in usable)
    plan = PipelinePlan(
        feasible=False,
        model=model.name,
        required_vram_gb=round(required_mb / 1024, 2),
        available_vram_gb=round(available_mb / 1024, 2),
    )

    if not usable:
        plan.reasons.append("no online blocks with usable GPU/VRAM were found")
        plan.notes = "Distributed inference needs GPU-backed blocks. CPU-only blocks cannot host model shards."
        return plan
    if available_mb < required_mb:
        plan.reasons.append(
            f"insufficient aggregate VRAM: need {required_mb/1024:.2f} GB, have {available_mb/1024:.2f} GB"
        )
        plan.notes = "Aggregate VRAM across blocks is only usable with model partitioning; here it is still too small."
        return plan

    total_layers = model.layers
    assigned = 0
    stages: list[PipelineStage] = []
    for idx, block in enumerate(usable):
        remaining_blocks = len(usable) - idx
        remaining_layers = total_layers - assigned
        if remaining_blocks == 1:
            take = remaining_layers
        else:
            share = block.usable_vram_mb / available_mb
            take = max(1, round(total_layers * share))
            take = min(take, remaining_layers - (remaining_blocks - 1))
        if take <= 0:
            continue
        stages.append(
            PipelineStage(
                block_id=block.block_id,
                block_name=block.name,
                layer_start=assigned,
                layer_end=assigned + take - 1,
                layers=take,
                vram_needed_mb=round(take * model.per_layer_vram_mb(), 1),
            )
        )
        assigned += take
    if assigned < total_layers:
        plan.reasons.append(f"could not place all layers ({assigned}/{total_layers})")
        return plan

    for block in usable:
        stage = next((s for s in stages if s.block_id == block.block_id), None)
        if stage and stage.vram_needed_mb > block.usable_vram_mb:
            plan.reasons.append(
                f"block {block.name}: stage needs {stage.vram_needed_mb:.0f} MB > {block.usable_vram_mb:.0f} MB available"
            )

    slow = [b.name for b in usable if b.net_rx_kbps and b.net_rx_kbps < 1024]
    if slow:
        plan.warnings.append(
            "pipeline parallelism transfers activations between stages every token; "
            f"low-throughput links detected on: {', '.join(slow)}. Expect high latency."
        )
    if len(usable) > 1:
        plan.warnings.append(
            "pipeline parallelism adds per-token network latency between stages; it is slower than a single big GPU."
        )
        plan.warnings.append(
            "tensor parallelism would need very fast interconnects (NVLink/InfiniBand) and is not assumed here."
        )

    plan.stages = stages
    plan.feasible = len(plan.reasons) == 0
    plan.notes = (
        "Plan is feasible. Actual execution requires a compatible backend "
        "(e.g. Petals or a PyTorch pipeline runtime) installed on each block; "
        "this planner does not download or run models by itself."
    )
    return plan


def capacities_from_blocks(blocks) -> list[BlockCapacity]:
    """Build capacities from registry BlockPublic objects (duck-typed)."""
    caps: list[BlockCapacity] = []
    for b in blocks:
        snapshot = getattr(b, "_snapshot", None)
        gpus = getattr(snapshot, "gpus", []) if snapshot else []
        vram_total = sum(g.vram_total_mb for g in gpus)
        vram_used = sum(g.vram_used_mb for g in gpus)
        caps.append(
            BlockCapacity(
                block_id=b.id,
                name=b.name,
                online=b.available,
                gpu_count=len(gpus),
                vram_total_mb=vram_total,
                vram_free_mb=max(vram_total - vram_used, 0.0),
                net_rx_kbps=getattr(snapshot, "net_rx_kbps", 0.0) if snapshot else 0.0,
                net_tx_kbps=getattr(snapshot, "net_tx_kbps", 0.0) if snapshot else 0.0,
            )
        )
    return caps
