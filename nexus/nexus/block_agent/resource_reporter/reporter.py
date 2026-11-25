"""Heartbeat construction."""
from __future__ import annotations

from nexus.block_agent.monitoring.collector import ResourceCollector
from nexus.shared.models import AppRuntimeState, HeartbeatPayload, ResourceSnapshot


class ResourceReporter:
    def __init__(self, block_id: str, secret: str, collector: ResourceCollector) -> None:
        self.block_id = block_id
        self.secret = secret
        self.collector = collector

    def snapshot(self) -> ResourceSnapshot:
        return self.collector.collect()

    def heartbeat(self, apps: list[AppRuntimeState], agent_version: str = "0.1.0") -> HeartbeatPayload:
        return HeartbeatPayload(
            block_id=self.block_id,
            secret=self.secret,
            snapshot=self.snapshot(),
            apps=apps,
            agent_version=agent_version,
        )
