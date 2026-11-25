"""Real application process manager for a BLOCK agent.

Runs apps as unprivileged subprocesses of the current user. Hard CPU quotas
require cgroups (root); where unavailable we apply rlimits and report honestly.
Docker is used only when explicitly requested AND available.
"""
from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psutil

from nexus.shared.logging import get_logger
from nexus.shared.models import AppRuntimeState, AppSpec
from nexus.block_agent.runtime_env import runtime_path

log = get_logger("exec")

DOCKER = shutil.which("docker")


@dataclass
class ManagedApp:
    app_id: str
    spec: AppSpec
    workdir: Path
    log_path: Path
    proc: Optional[subprocess.Popen] = None
    status: str = "STOPPED"
    started_at: float = 0.0
    last_cpu_time: float = 0.0
    last_sample_at: float = 0.0

    @property
    def pid(self) -> Optional[int]:
        if self.proc and self.proc.poll() is None:
            return self.proc.pid
        return None


def _apply_limits(ram_limit_mb: Optional[float]) -> None:
    if ram_limit_mb and ram_limit_mb > 0:
        requested = int(ram_limit_mb * 1024 * 1024)
        # Runtimes (Node/Bun/Java) reserve large virtual address space even when
        # RSS is small, so a hard RLIMIT_AS equal to the RAM quota kills them.
        # Give generous headroom while still bounding runaway allocations.
        limit = max(requested * 4, 2 * 1024 * 1024 * 1024)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass


class ProcessManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.apps: dict[str, ManagedApp] = {}

    def _paths(self, app_id: str) -> tuple[Path, Path]:
        workdir = self.base_dir / app_id
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir, workdir / "app.log"

    def _load_existing(self) -> None:
        for spec_file in self.base_dir.glob("*/spec.json"):
            try:
                spec = AppSpec(**json.loads(spec_file.read_text()))
                app_id = spec_file.parent.name
                workdir, log_path = self._paths(app_id)
                self.apps[app_id] = ManagedApp(app_id=app_id, spec=spec, workdir=workdir, log_path=log_path)
            except Exception:
                continue

    def create(self, app_id: str, spec: AppSpec, start: bool = True) -> dict:
        workdir, log_path = self._paths(app_id)
        (workdir / "spec.json").write_text(spec.model_dump_json(indent=2))
        app = ManagedApp(app_id=app_id, spec=spec, workdir=workdir, log_path=log_path)
        self.apps[app_id] = app
        if not start:
            app.status = "CREATED"
            return {"ok": True, "status": "CREATED", "pid": None}
        return self.start(app_id)

    def _build_command(self, app: ManagedApp) -> tuple[list[str] | str, dict]:
        spec = app.spec
        env = os.environ.copy()
        env["PATH"] = runtime_path()
        env.update(spec.env)
        if spec.kind == "docker":
            if not DOCKER:
                raise RuntimeError("docker requested but not available on this block")
            if not spec.image:
                raise RuntimeError("docker app requires an image")
            cmd = [DOCKER, "run", "--rm", "-i", "--name", f"nexus-{app.app_id}"]
            for port in spec.ports:
                cmd += ["-p", f"{port}:{port}"]
            for k, v in spec.env.items():
                cmd += ["-e", f"{k}={v}"]
            if spec.ram_limit_mb:
                cmd += ["--memory", f"{int(spec.ram_limit_mb)}m"]
            if spec.cpu_limit:
                cmd += ["--cpus", str(spec.cpu_limit)]
            cmd.append(spec.image)
            if spec.command:
                cmd += spec.command.split()
            return cmd, env
        if not spec.command:
            raise RuntimeError("process app requires a command")
        return spec.command, env

    def start(self, app_id: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        if app.proc and app.proc.poll() is None:
            return {"ok": True, "status": "already_running", "pid": app.proc.pid}
        try:
            cmd, env = self._build_command(app)
        except RuntimeError as exc:
            app.status = "ERROR"
            return {"ok": False, "error": str(exc)}
        workdir = Path(app.spec.working_dir) if app.spec.working_dir else app.workdir
        workdir.mkdir(parents=True, exist_ok=True)
        log_file = open(app.log_path, "ab", buffering=0)  # noqa: SIM115
        log_file.write(f"\n=== start {time.ctime()} ===\n".encode())
        is_shell = isinstance(cmd, str)
        try:
            app.proc = subprocess.Popen(
                cmd,
                shell=is_shell,
                cwd=str(workdir),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=(lambda: _apply_limits(app.spec.ram_limit_mb)) if app.spec.kind != "docker" else None,
            )
        except Exception as exc:  # noqa: BLE001
            app.status = "ERROR"
            return {"ok": False, "error": str(exc)}
        app.status = "RUNNING"
        app.started_at = time.time()
        app.last_cpu_time = 0.0
        app.last_sample_at = 0.0
        return {"ok": True, "pid": app.proc.pid, "status": "RUNNING"}

    def stop(self, app_id: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        if app.proc and app.proc.poll() is None:
            try:
                os.killpg(os.getpgid(app.proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                app.proc.terminate()
            try:
                app.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(app.proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    app.proc.kill()
        app.status = "STOPPED"
        return {"ok": True, "status": "STOPPED"}

    def restart(self, app_id: str) -> dict:
        self.stop(app_id)
        return self.start(app_id)

    def delete(self, app_id: str) -> dict:
        self.stop(app_id)
        app = self.apps.pop(app_id, None)
        if app:
            shutil.rmtree(app.workdir, ignore_errors=True)
        return {"ok": True, "deleted": app_id}

    def logs(self, app_id: str, tail: int = 400) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        if not app.log_path.exists():
            return {"ok": True, "logs": ""}
        lines = app.log_path.read_text(errors="replace").splitlines()[-tail:]
        return {"ok": True, "logs": "\n".join(lines)}

    # ---------------------------- file manager ----------------------------

    MAX_READ = 512 * 1024
    MAX_OUTPUT = 128 * 1024

    def _root(self, app: ManagedApp) -> Path:
        root = Path(app.spec.working_dir) if app.spec.working_dir else app.workdir
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def _resolve(self, app: ManagedApp, rel: str) -> Path:
        root = self._root(app)
        target = (root / (rel or "")).resolve()
        if target != root and root not in target.parents:
            raise ValueError("path escapes the app directory")
        return target

    @staticmethod
    def _rel(root: Path, target: Path) -> str:
        return "" if target == root else str(target.relative_to(root))

    def _entry(self, path: Path) -> dict:
        st = path.stat()
        return {
            "name": path.name,
            "type": "dir" if path.is_dir() else "file",
            "size": st.st_size,
            "mtime": st.st_mtime,
        }

    def files_list(self, app_id: str, path: str = "") -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            root = self._root(app)
            target = self._resolve(app, path)
            if not target.exists():
                return {"ok": False, "error": "path not found"}
            if target.is_file():
                return {"ok": True, "path": self._rel(root, target), "entries": [self._entry(target)]}
            entries = [self._entry(p) for p in target.iterdir()]
            entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
            return {"ok": True, "path": self._rel(root, target), "entries": entries}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def file_read(self, app_id: str, path: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            root = self._root(app)
            target = self._resolve(app, path)
            if not target.is_file():
                return {"ok": False, "error": "not a file"}
            size = target.stat().st_size
            if size > self.MAX_READ:
                return {"ok": False, "error": f"file too large ({size} bytes, max {self.MAX_READ})"}
            data = target.read_bytes()
            binary = b"\x00" in data[:8192]
            return {
                "ok": True,
                "path": self._rel(root, target),
                "size": size,
                "binary": binary,
                "content": "" if binary else data.decode("utf-8", errors="replace"),
            }
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def file_write(self, app_id: str, path: str, content: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            target = self._resolve(app, path)
            if target.is_dir():
                return {"ok": False, "error": "target is a directory"}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"ok": True, "path": path, "size": target.stat().st_size}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def file_delete(self, app_id: str, path: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            root = self._root(app)
            target = self._resolve(app, path)
            if target == root:
                return {"ok": False, "error": "cannot delete the app root"}
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            else:
                return {"ok": False, "error": "path not found"}
            return {"ok": True, "deleted": path}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def file_mkdir(self, app_id: str, path: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            target = self._resolve(app, path)
            target.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "created": path}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def file_rename(self, app_id: str, path: str, new_path: str) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        try:
            root = self._root(app)
            source = self._resolve(app, path)
            target = self._resolve(app, new_path)
            if source == root:
                return {"ok": False, "error": "cannot move the app root"}
            if not source.exists():
                return {"ok": False, "error": "source not found"}
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            return {"ok": True, "path": self._rel(root, target)}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def exec(self, app_id: str, command: str, timeout: float = 20.0) -> dict:
        app = self.apps.get(app_id)
        if app is None:
            return {"ok": False, "error": "unknown app"}
        if not command.strip():
            return {"ok": False, "error": "empty command"}
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self._root(app)),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"command timed out after {timeout:.0f}s", "output": ""}
        except OSError as exc:
            return {"ok": False, "error": str(exc), "output": ""}
        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > self.MAX_OUTPUT:
            output = output[: self.MAX_OUTPUT] + "\n… (output truncated)"
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "output": output}

    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
        env: Optional[dict[str, str]] = None,
    ) -> dict:
        """Run a cluster task on this block (not tied to a managed app)."""
        if not command.strip():
            return {"ok": False, "error": "empty command", "output": ""}
        home = Path.home().resolve()
        workdir = Path(cwd).expanduser().resolve() if cwd else home
        if workdir != home and home not in workdir.parents:
            return {"ok": False, "error": "cwd must be inside the account home", "output": ""}
        if not workdir.is_dir():
            return {"ok": False, "error": f"cwd not found: {workdir}", "output": ""}
        full_env = os.environ.copy()
        full_env["PATH"] = runtime_path()
        full_env.update(env or {})
        started = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(workdir),
                env=full_env,
                capture_output=True,
                text=True,
                timeout=max(1.0, min(float(timeout), 600.0)),
            )
        except subprocess.TimeoutExpired as exc:
            partial = ""
            for stream in (exc.stdout, exc.stderr):
                if stream:
                    partial += stream if isinstance(stream, str) else stream.decode(errors="replace")
            return {
                "ok": False,
                "error": f"command timed out after {timeout:.0f}s",
                "output": partial[: self.MAX_OUTPUT],
                "duration_ms": int((time.time() - started) * 1000),
                "cwd": str(workdir),
            }
        except OSError as exc:
            return {"ok": False, "error": str(exc), "output": ""}
        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > self.MAX_OUTPUT:
            output = output[: self.MAX_OUTPUT] + "\n… (output truncated)"
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": output,
            "duration_ms": int((time.time() - started) * 1000),
            "cwd": str(workdir),
        }

    def _tree_usage(self, pid: int) -> Optional[tuple[float, float]]:
        try:
            root = psutil.Process(pid)
            procs = [root]
            procs += root.children(recursive=True)
        except psutil.Error:
            return None
        cpu = 0.0
        rss = 0.0
        for proc in procs:
            try:
                times = proc.cpu_times()
                cpu += times.user + times.system
                rss += proc.memory_info().rss
            except psutil.Error:
                continue
        return cpu, rss / (1024 * 1024)

    def _usage(self, app: ManagedApp) -> tuple[float, float]:
        pid = app.pid
        if pid is None:
            app.last_cpu_time = 0.0
            app.last_sample_at = 0.0
            return 0.0, 0.0
        usage = self._tree_usage(pid)
        if usage is None:
            return 0.0, 0.0
        cpu_total, ram = usage
        now = time.time()
        cpu_percent = 0.0
        if app.last_sample_at > 0 and now > app.last_sample_at:
            delta = max(0.0, cpu_total - app.last_cpu_time)
            cpu_percent = delta / (now - app.last_sample_at) * 100.0
        app.last_cpu_time = cpu_total
        app.last_sample_at = now
        return float(cpu_percent), float(ram)

    def states(self) -> list[AppRuntimeState]:
        out: list[AppRuntimeState] = []
        for app in self.apps.values():
            if app.proc is not None and app.proc.poll() is not None:
                app.status = "STOPPED"
                app.last_cpu_time = 0.0
                app.last_sample_at = 0.0
            cpu, ram = self._usage(app)
            out.append(
                AppRuntimeState(
                    app_id=app.app_id,
                    name=app.spec.name,
                    status=app.status,
                    pid=app.pid,
                    cpu_percent=cpu,
                    ram_mb=ram,
                )
            )
        return out

    def shutdown(self) -> None:
        for app_id in list(self.apps):
            self.stop(app_id)
