from nexus.master.resource_manager import manager as rm
from nexus.shared.models import (
    AppSpec,
    ResourceOffer,
    ResourceOfferSet,
    ResourceSnapshot,
)


def test_offered_full_respects_reserved():
    offer = ResourceOffer(enabled=True, full=True, reserved_for_host=2)
    assert rm.offered_for(10, offer) == 8


def test_offered_capped_by_physical():
    offer = ResourceOffer(enabled=True, amount=100)
    assert rm.offered_for(10, offer) == 10


def test_offered_disabled_is_zero():
    assert rm.offered_for(10, ResourceOffer(enabled=False, amount=5)) == 0


def test_quotas_allocate_and_available():
    offers = ResourceOfferSet(
        cpu=ResourceOffer(enabled=True, amount=8),
        ram=ResourceOffer(enabled=True, amount=16000),
    )
    snapshot = ResourceSnapshot(cpu_cores=8, ram_total_mb=32000, disk_total_mb=100000)
    apps = [AppSpec(name="a", cpu_limit=2, ram_limit_mb=4000)]
    quotas = rm.compute_quotas(offers, snapshot, apps)
    assert quotas.cpu.offered == 8
    assert quotas.cpu.allocated == 2
    assert quotas.cpu.available == 6
    assert quotas.ram.available == 12000
    assert quotas.disk.offered == 0


def test_can_host_rejects_when_not_enough():
    offers = ResourceOfferSet(cpu=ResourceOffer(enabled=True, amount=1))
    snapshot = ResourceSnapshot(cpu_cores=8)
    quotas = rm.compute_quotas(offers, snapshot, [])
    ok, reasons = rm.can_host(quotas, AppSpec(name="x", cpu_limit=4))
    assert ok is False
    assert reasons


def test_physical_resources_not_merged_across_blocks():
    snap_a = ResourceSnapshot(cpu_cores=4, ram_total_mb=8000)
    snap_b = ResourceSnapshot(cpu_cores=16, ram_total_mb=64000)
    offers = ResourceOfferSet(
        cpu=ResourceOffer(enabled=True, full=True),
        ram=ResourceOffer(enabled=True, full=True),
    )
    qa = rm.compute_quotas(offers, snap_a, [])
    qb = rm.compute_quotas(offers, snap_b, [])
    assert qa.cpu.physical == 4 and qb.cpu.physical == 16
    assert qa.ram.physical == 8000 and qb.ram.physical == 64000
