"""Resource accounting.

Computes real quotas per block. Physical resources of different machines are
NEVER merged into a single fictional device - each block is accounted for on
its own.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from nexus.master.core.models_db import Block
from nexus.shared.models import (
    AppSpec,
    ResourceOffer,
    ResourceOfferSet,
    ResourceQuota,
    ResourceQuotas,
    ResourceSnapshot,
)


def _physical(snapshot: ResourceSnapshot) -> dict[str, float]:
    return {
        "cpu": float(snapshot.cpu_cores),
        "ram": float(snapshot.ram_total_mb),
        "disk": float(snapshot.disk_total_mb),
        "gpu": float(len(snapshot.gpus)),
    }


def offered_for(physical: float, offer: ResourceOffer) -> float:
    if not offer.enabled:
        return 0.0
    usable = max(physical - offer.reserved_for_host, 0.0)
    if offer.full:
        return usable
    if offer.amount is None:
        return 0.0
    return max(min(offer.amount, usable), 0.0)


def _allocated_for(kind: str, apps: Iterable[AppSpec]) -> float:
    total = 0.0
    for app in apps:
        if kind == "cpu" and app.cpu_limit:
            total += app.cpu_limit
        elif kind == "ram" and app.ram_limit_mb:
            total += app.ram_limit_mb
        elif kind == "disk" and app.disk_limit_mb:
            total += app.disk_limit_mb
    return total


def compute_quotas(
    offers: ResourceOfferSet,
    snapshot: ResourceSnapshot,
    apps: Iterable[AppSpec],
) -> ResourceQuotas:
    physical = _physical(snapshot)
    apps = list(apps)
    result = ResourceQuotas()
    for kind, offer in offers.as_map().items():
        phys = physical.get(kind, 0.0)
        offered = offered_for(phys, offer)
        allocated = _allocated_for(kind, apps)
        available = max(offered - allocated, 0.0)
        setattr(
            result,
            kind,
            ResourceQuota(
                physical=phys,
                offered=offered,
                allocated=allocated,
                available=available,
                reserved_for_host=offer.reserved_for_host,
            ),
        )
    return result


def can_host(quotas: ResourceQuotas, spec: AppSpec) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if spec.cpu_limit and quotas.cpu.available < spec.cpu_limit:
        reasons.append(f"cpu: need {spec.cpu_limit}, free {quotas.cpu.available}")
    if spec.ram_limit_mb and quotas.ram.available < spec.ram_limit_mb:
        reasons.append(f"ram: need {spec.ram_limit_mb}, free {quotas.ram.available}")
    if spec.disk_limit_mb and quotas.disk.available < spec.disk_limit_mb:
        reasons.append(f"disk: need {spec.disk_limit_mb}, free {quotas.disk.available}")
    return (len(reasons) == 0, reasons)


def quotas_from_block(block: Block, apps: list[AppSpec]) -> ResourceQuotas:
    offers = ResourceOfferSet(**json.loads(block.offers_json or "{}")) if block.offers_json else ResourceOfferSet()
    snapshot = ResourceSnapshot(**json.loads(block.snapshot_json or "{}")) if block.snapshot_json else ResourceSnapshot()
    return compute_quotas(offers, snapshot, apps)


def parse_snapshot(block: Block) -> ResourceSnapshot:
    if not block.snapshot_json:
        return ResourceSnapshot()
    try:
        return ResourceSnapshot(**json.loads(block.snapshot_json))
    except Exception:
        return ResourceSnapshot()
