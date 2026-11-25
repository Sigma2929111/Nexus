"""Database engine and session helpers for the MASTER."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine

from nexus.shared.config import Paths

_engine = None
_engine_path: Optional[Path] = None


def get_engine(db_path: Optional[Path] = None):
    global _engine, _engine_path
    db_path = db_path or Paths.build().db
    if _engine is None or _engine_path != db_path:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        _engine_path = db_path
        from nexus.master.core import models_db  # noqa: F401  (register tables)

        SQLModel.metadata.create_all(_engine)
    return _engine


def init_db(db_path: Optional[Path] = None) -> None:
    get_engine(db_path)


@contextmanager
def session_scope(db_path: Optional[Path] = None) -> Iterator[Session]:
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session


def reset_engine() -> None:
    """Used by tests to drop the cached engine."""
    global _engine, _engine_path
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_path = None
