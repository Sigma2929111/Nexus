"""Placement scheduler: chooses a block for an application."""
from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from nexus.master.core import models_db as m
from nexus.master.registry import registry as reg
from nexus.master.resource_manager import manager as rm
from nexus.shared.models import AppSpec, BlockStatus


def block_capabilities(block: m.Block) -> dict[str, str]:
    try:
        return json.loads(block.snapshot_json or "{}").get("capabilities", {}) or {}
    except (ValueError, TypeError):
        return {}


def missing_capabilities(spec: AppSpec, block: m.Block) -> list[str]:
    """Which runtimes/tools required by the app are absent on this block."""
    caps = block_capabilities(block)
    missing: list[str] = []
    if spec.kind == "docker":
        if not caps.get("docker"):
            missing.append("docker")
        return missing
    command = (spec.command or "").lower()
    if re.search(r"(^|[\s;|&])python3?(\s|$)", command) and not caps.get("python"):
        missing.append("python")
    if re.search(r"(^|[\s;|&])node(\s|$)", command) and not caps.get("node"):
        missing.append("node")
    if re.search(r"(^|[\s;|&])npm(\s|$)", command) and not caps.get("npm"):
        missing.append("npm")
    if re.search(r"(^|[\s;|&])npx(\s|$)", command) and not caps.get("npm"):
        missing.append("npm")
    if "code-server" in command and not caps.get("code-server"):
        missing.append("code-server")
    if re.search(r"(^|[\s;|&])opencode(\s|$)", command) and not caps.get("opencode"):
        missing.append("opencode")
    return missing


def choose_block(session: Session, spec: AppSpec) -> tuple[str | None, list[str]]:
    """Return (block_id, reasons). block_id is None when nothing fits."""
    rows = session.exec(select(m.Block)).all()
    candidates: list[tuple[float, str]] = []
    rejection_notes: list[str] = []
    for block in rows:
        if block.status != BlockStatus.ONLINE.value:
            continue
        missing = missing_capabilities(spec, block)
        if missing:
            rejection_notes.append(f"{block.name}: missing {', '.join(missing)}")
            continue
        apps = reg._apps_for(session, block.id)
        quotas = rm.quotas_from_block(block, apps)
        ok, reasons = rm.can_host(quotas, spec)
        if not ok:
            rejection_notes.append(f"{block.name}: " + "; ".join(reasons))
            continue
        score = (
            quotas.cpu.available / (spec.cpu_limit or 1)
            + quotas.ram.available / (spec.ram_limit_mb or 1)
            + quotas.disk.available / (spec.disk_limit_mb or 1)
        )
        candidates.append((score, block.id))
    if not candidates:
        return None, rejection_notes or ["no online blocks available"]
    candidates.sort(reverse=True)
    return candidates[0][1], []
