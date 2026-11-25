"""BLOCK agent runtime: pairing, heartbeat and command execution."""
from __future__ import annotations

import asyncio
import json
import socket
from typing import Optional

import httpx

from nexus.block_agent.execution.manager import ProcessManager
from nexus.block_agent.monitoring.collector import ResourceCollector
from nexus.block_agent.resource_reporter.reporter import ResourceReporter
from nexus.block_agent.transport.client import AgentTransport
from nexus.block_agent.runtime_env import apply_runtime_path
from nexus.shared.config import NexusConfig, Paths
from nexus.shared.logging import get_logger
from nexus.shared.models import AppSpec, PairRequest
from nexus.shared.protocol import (
    CMD_AGENT_RESTART,
    CMD_APP_CREATE,
    CMD_APP_DELETE,
    CMD_APP_EXEC,
    CMD_APP_LOGS,
    CMD_APP_RESTART,
    CMD_APP_START,
    CMD_APP_STOP,
    CMD_CLUSTER_EXEC,
    CMD_FS_DELETE,
    CMD_FS_LIST,
    CMD_FS_MKDIR,
    CMD_FS_READ,
    CMD_FS_RENAME,
    CMD_FS_WRITE,
    MSG_COMMAND,
    MSG_COMMAND_RESULT,
    MSG_ERROR,
    MSG_HEARTBEAT,
    MSG_HELLO,
    MSG_HELLO_OK,
)

log = get_logger("agent")
AGENT_VERSION = "0.1.0"


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class BlockAgent:
    def __init__(
        self,
        config: NexusConfig,
        pairing_token: Optional[str] = None,
        ca_path: Optional[str] = None,
    ) -> None:
        self.config = config
        self.pairing_token = pairing_token
        self.ca_path = ca_path
        apply_runtime_path()
        self.collector = ResourceCollector()
        self.pm = ProcessManager(Paths.build().apps)
        self.pm._load_existing()
        self._restart_requested = False

    async def _pair(self) -> None:
        if not self.pairing_token:
            raise RuntimeError("block is not paired and no --token was provided")
        if not self.config.master_url:
            raise RuntimeError("no MASTER url configured (use --master)")
        url = self.config.master_url.rstrip("/") + "/api/v1/blocks/pair"
        payload = PairRequest(
            token=self.pairing_token,
            name=self.config.block_name or socket.gethostname(),
            ip=_local_ip(),
            port=self.config.port,
            agent_version=AGENT_VERSION,
            snapshot=self.collector.collect(),
        )
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            resp = await client.post(url, json=payload.model_dump())
        if resp.status_code >= 400:
            raise RuntimeError(f"pairing failed ({resp.status_code}): {resp.text}")
        data = resp.json()
        self.config.block_id = data["block_id"]
        self.config.block_secret = data["block_secret"]
        self.config.role = "block"
        self.config.save()
        log.info("paired as %s", self.config.block_id)

    async def run(self) -> None:
        backoff = 3
        while True:
            try:
                if not (self.config.block_id and self.config.block_secret):
                    await self._pair()
                await self._session()
                backoff = 3
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("connection error: %s (retry in %ss)", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            if self._restart_requested:
                log.info("agent restart requested; exiting for supervisor restart")
                return

    async def _session(self) -> None:
        assert self.config.master_url
        transport = AgentTransport(self.config.master_url, self.ca_path)
        ws = await transport.connect()
        try:
            await ws.send(
                json.dumps(
                    {"type": MSG_HELLO, "data": {"block_id": self.config.block_id, "secret": self.config.block_secret}}
                )
            )
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if first.get("type") != MSG_HELLO_OK:
                raise RuntimeError(f"handshake rejected: {first}")
            log.info("connected to MASTER, sending heartbeats every %ss", self.config.heartbeat_interval)
            reporter = ResourceReporter(self.config.block_id, self.config.block_secret, self.collector)
            tasks = [
                asyncio.create_task(self._heartbeat_loop(ws, reporter)),
                asyncio.create_task(self._receive_loop(ws)),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc
        finally:
            await transport.close()

    async def _heartbeat_loop(self, ws, reporter: ResourceReporter) -> None:
        while True:
            payload = reporter.heartbeat(self.pm.states(), AGENT_VERSION)
            await ws.send(json.dumps({"type": MSG_HEARTBEAT, "data": payload.model_dump()}))
            await asyncio.sleep(self.config.heartbeat_interval)

    async def _receive_loop(self, ws) -> None:
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("type") == MSG_COMMAND:
                data = msg.get("data", {})
                request_id = data.get("request_id")
                result = await asyncio.to_thread(self._dispatch, data.get("action", ""), data.get("payload", {}))
                await ws.send(
                    json.dumps({"type": MSG_COMMAND_RESULT, "data": {"request_id": request_id, "result": result}})
                )
            elif msg.get("type") == MSG_ERROR:
                log.warning("master reported error: %s", msg.get("data"))

    def _dispatch(self, action: str, payload: dict) -> dict:
        try:
            if action == CMD_APP_CREATE:
                spec = AppSpec(**payload["spec"])
                return self.pm.create(payload["app_id"], spec, start=payload.get("start", True))
            if action == CMD_APP_START:
                return self.pm.start(payload["app_id"])
            if action == CMD_APP_STOP:
                return self.pm.stop(payload["app_id"])
            if action == CMD_APP_RESTART:
                return self.pm.restart(payload["app_id"])
            if action == CMD_APP_DELETE:
                return self.pm.delete(payload["app_id"])
            if action == CMD_APP_LOGS:
                return self.pm.logs(payload["app_id"])
            if action == CMD_APP_EXEC:
                return self.pm.exec(
                    payload["app_id"],
                    payload.get("command", ""),
                    float(payload.get("timeout", 20)),
                )
            if action == CMD_CLUSTER_EXEC:
                return self.pm.run_command(
                    payload.get("command", ""),
                    cwd=payload.get("cwd") or None,
                    timeout=float(payload.get("timeout", 60)),
                    env=payload.get("env") or None,
                )
            if action == CMD_FS_LIST:
                return self.pm.files_list(payload["app_id"], payload.get("path", ""))
            if action == CMD_FS_READ:
                return self.pm.file_read(payload["app_id"], payload.get("path", ""))
            if action == CMD_FS_WRITE:
                return self.pm.file_write(
                    payload["app_id"], payload.get("path", ""), payload.get("content", "")
                )
            if action == CMD_FS_DELETE:
                return self.pm.file_delete(payload["app_id"], payload.get("path", ""))
            if action == CMD_FS_MKDIR:
                return self.pm.file_mkdir(payload["app_id"], payload.get("path", ""))
            if action == CMD_FS_RENAME:
                return self.pm.file_rename(
                    payload["app_id"], payload.get("path", ""), payload.get("new_path", "")
                )
            if action == CMD_AGENT_RESTART:
                self._restart_requested = True
                return {"ok": True, "status": "restarting"}
            return {"ok": False, "error": f"unknown action {action}"}
        except Exception as exc:  # noqa: BLE001
            log.warning("command %s failed: %s", action, exc)
            return {"ok": False, "error": str(exc)}
