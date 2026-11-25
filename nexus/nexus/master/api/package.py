"""Serve the latest built NEXUS installer package for download."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from nexus.master.security.auth import require_admin

router = APIRouter(prefix="/api/v1/package", tags=["package"])

PACKAGE_DIR = Path(__file__).resolve().parents[3] / "dist_packages"


def _package_dir() -> Path:
    if PACKAGE_DIR.is_dir():
        return PACKAGE_DIR
    fallback = Path.cwd() / "dist_packages"
    return fallback


def _latest() -> Optional[Path]:
    directory = _package_dir()
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("nexus-cloud-*.tar.gz") if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


@router.get("/info")
def package_info(actor: str = Depends(require_admin)) -> dict:
    path = _latest()
    if path is None:
        return {"available": False}
    stat = path.stat()
    return {
        "available": True,
        "name": path.name,
        "size": stat.st_size,
        "updated_at": stat.st_mtime,
    }


@router.get("/latest")
def package_latest(actor: str = Depends(require_admin)) -> FileResponse:
    path = _latest()
    if path is None:
        raise HTTPException(404, "no package built yet")
    return FileResponse(path, media_type="application/gzip", filename=path.name)
