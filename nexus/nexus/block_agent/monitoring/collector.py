"""System resource collection for a BLOCK.

Reads real limits from cgroups (v2 then v1) so containers report the CPU/RAM
they can actually use instead of the host's total. Falls back to psutil when
no cgroup limits are present.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

from nexus.shared.config import Paths
from nexus.shared.models import GpuInfo, ResourceSnapshot

CGROUP = Path("/sys/fs/cgroup")


def _version(exe: str, *args: str) -> Optional[str]:
    path = shutil.which(exe)
    if not path:
        return None
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "installed"
    text = (out.stdout or out.stderr).strip().splitlines()
    line = text[0] if text else ""
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", line)
    return match.group(1) if match else (line[:40] or "installed")


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None


def _num(value: Optional[str]) -> Optional[float]:
    if not value or value == "max":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _cpu_limit() -> Optional[float]:
    v2 = _read(CGROUP / "cpu.max")
    if v2:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            quota, period = _num(parts[0]), _num(parts[1])
            if quota and period:
                return quota / period
    quota = _num(_read(CGROUP / "cpu" / "cpu.cfs_quota_us"))
    period = _num(_read(CGROUP / "cpu" / "cpu.cfs_period_us"))
    if quota and quota > 0 and period and period > 0:
        return quota / period
    return None


def _mem_limit() -> Optional[float]:
    limit = _num(_read(CGROUP / "memory.max"))
    if limit is None:
        limit = _num(_read(CGROUP / "memory" / "memory.limit_in_bytes"))
    if limit and limit < (1 << 62):
        return limit
    return None


def _mem_current() -> Optional[float]:
    used = _num(_read(CGROUP / "memory.current"))
    if used is None:
        used = _num(_read(CGROUP / "memory" / "memory.usage_in_bytes"))
    return used


def _cpu_usage_usec() -> Optional[float]:
    stat = _read(CGROUP / "cpu.stat")
    if stat:
        for line in stat.splitlines():
            if line.startswith("usage_usec "):
                try:
                    return float(line.split()[1])
                except (IndexError, ValueError):
                    return None
    v1 = _num(_read(CGROUP / "cpuacct" / "cpuacct.usage"))
    if v1 is not None:
        return v1 / 1000.0
    return None


class ResourceCollector:
    def __init__(self) -> None:
        self._last_net = psutil.net_io_counters()
        self._last_net_ts = time.time()
        self._last_cpu_usec = _cpu_usage_usec()
        self._last_cpu_ts = time.time()
        self._host_cpu = float(psutil.cpu_count(logical=True) or 1)
        self._caps = self._detect_capabilities()
        self._home_used_mb: Optional[float] = None
        self._home_used_ts = 0.0

    def _home_usage_mb(self) -> Optional[float]:
        """Disk used by the NEXUS platform (apps/files), not the whole host fs."""
        now = time.time()
        if self._home_used_mb is not None and now - self._home_used_ts < 60:
            return self._home_used_mb
        try:
            out = subprocess.run(
                ["du", "-sb", str(Paths.build().home)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            value = float(out.stdout.split()[0])
            self._home_used_mb = value / (1024 * 1024)
            self._home_used_ts = now
            return self._home_used_mb
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

    def _detect_capabilities(self) -> dict[str, str]:
        caps: dict[str, str] = {}
        checks = {
            "docker": ("docker", "--version"),
            "python": ("python3", "--version"),
            "node": ("node", "--version"),
            "npm": ("npm", "--version"),
            "git": ("git", "--version"),
            "code-server": ("code-server", "--version"),
            "opencode": ("opencode", "--version"),
        }
        for key, (exe, arg) in checks.items():
            version = _version(exe, arg)
            if version:
                caps[key] = version
        if not caps.get("python"):
            fallback = _version("python", "--version")
            if fallback:
                caps["python"] = fallback
        gpu = self._gpus()
        if gpu:
            caps["gpu"] = gpu[0].name
        return caps

    def _gpus(self) -> list[GpuInfo]:
        if not shutil.which("nvidia-smi"):
            return []
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            gpus: list[GpuInfo] = []
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append(
                        GpuInfo(
                            index=int(parts[0]),
                            name=parts[1],
                            vram_total_mb=float(parts[2]),
                            vram_used_mb=float(parts[3]),
                        )
                    )
            return gpus
        except Exception:
            return []

    def _cpu_percent(self, cores: float) -> float:
        now = time.time()
        usec = _cpu_usage_usec()
        if usec is not None and self._last_cpu_usec is not None:
            dt = max(now - self._last_cpu_ts, 1e-6)
            cores_used = (usec - self._last_cpu_usec) / 1e6 / dt
            self._last_cpu_usec, self._last_cpu_ts = usec, now
            pct = cores_used / max(cores, 1e-6) * 100.0
            return max(0.0, min(pct, 100.0))
        return float(psutil.cpu_percent(interval=None))

    def collect(self) -> ResourceSnapshot:
        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(str(Paths.build().home))
        except OSError:
            disk = psutil.disk_usage("/")
        now = time.time()
        net = psutil.net_io_counters()
        dt = max(now - self._last_net_ts, 1e-6)
        rx_kbps = (net.bytes_recv - self._last_net.bytes_recv) / 1024 / dt
        tx_kbps = (net.bytes_sent - self._last_net.bytes_sent) / 1024 / dt
        self._last_net, self._last_net_ts = net, now

        cores = min(_cpu_limit() or self._host_cpu, self._host_cpu)
        mem_limit = _mem_limit()
        limits = [vm.total]
        plan_mb = os.environ.get("SERVER_MEMORY")
        if plan_mb:
            try:
                limits.append(float(plan_mb) * 1024 * 1024)
            except ValueError:
                pass
        if mem_limit:
            limits.append(mem_limit)
        ram_total = min(limits)
        ram_used = _mem_current()
        if ram_used is None:
            ram_used = vm.used
        ram_used = min(ram_used, ram_total)

        try:
            load1 = psutil.getloadavg()[0]
        except (AttributeError, OSError):
            load1 = 0.0
        return ResourceSnapshot(
            cpu_cores=float(cores),
            cpu_usage_percent=self._cpu_percent(cores),
            load_1=float(load1),
            ram_total_mb=ram_total / (1024 * 1024),
            ram_used_mb=ram_used / (1024 * 1024),
            disk_total_mb=disk.total / (1024 * 1024),
            disk_used_mb=self._home_usage_mb() or (disk.used / (1024 * 1024)),
            net_rx_kbps=max(rx_kbps, 0.0),
            net_tx_kbps=max(tx_kbps, 0.0),
            gpus=self._gpus(),
            capabilities=self._caps,
            captured_at=now,
        )
