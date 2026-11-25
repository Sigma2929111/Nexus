import json

from nexus.master.core import models_db as m
from nexus.master.core.db import session_scope
from nexus.master.scheduler import scheduler
from nexus.shared.models import AppSpec, ResourceOfferSet
from nexus.shared.security import hash_secret


def _add_block(block_id, name, cpu_cores, status="ONLINE", full=True):
    offers = ResourceOfferSet(
        cpu={"enabled": True, "full": full, "amount": None, "reserved_for_host": 0},
    )
    with session_scope() as session:
        session.add(
            m.Block(
                id=block_id,
                name=name,
                secret_hash=hash_secret("x"),
                status=status,
                approved=True,
                offers_json=offers.model_dump_json(),
                snapshot_json=json.dumps({"cpu_cores": cpu_cores}),
            )
        )
        session.commit()


def test_scheduler_picks_block_with_capacity(client):
    _add_block("b1", "small", 2)
    _add_block("b2", "big", 16)
    with session_scope() as session:
        chosen, reasons = scheduler.choose_block(session, AppSpec(name="app", cpu_limit=4))
    assert chosen == "b2"
    assert reasons == []


def test_scheduler_skips_offline(client):
    _add_block("b1", "offline", 16, status="OFFLINE")
    with session_scope() as session:
        chosen, reasons = scheduler.choose_block(session, AppSpec(name="app", cpu_limit=1))
    assert chosen is None
    assert reasons


def test_scheduler_reports_when_too_small(client):
    _add_block("b1", "small", 1)
    with session_scope() as session:
        chosen, reasons = scheduler.choose_block(session, AppSpec(name="app", cpu_limit=8))
    assert chosen is None
    assert reasons
