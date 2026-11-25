"""Ready-to-use server presets shown in the 'Create server' dialog."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Preset(BaseModel):
    id: str
    name: str
    category: str
    kind: str = "process"
    image: Optional[str] = None
    command: str = ""
    description: str = ""
    cpu: float = 1.0
    ram_mb: float = 512
    disk_mb: float = 2048
    ports: list[int] = []
    env: dict[str, str] = {}
    color: str = "#4f8cff"


PRESETS: list[Preset] = [
    Preset(
        id="nodejs",
        name="Node.js",
        category="Application",
        command="node index.js",
        description="JavaScript / TypeScript runtime for web apps and bots.",
        cpu=1,
        ram_mb=512,
        disk_mb=2048,
        ports=[3000],
        color="#68a063",
    ),
    Preset(
        id="python",
        name="Python",
        category="Application",
        command="python3 main.py",
        description="Python app, script or worker.",
        cpu=1,
        ram_mb=512,
        disk_mb=2048,
        ports=[8000],
        color="#3572A5",
    ),
    Preset(
        id="api",
        name="FastAPI / API",
        category="Application",
        command="uvicorn main:app --host 0.0.0.0 --port 8000",
        description="HTTP API server.",
        cpu=1,
        ram_mb=768,
        disk_mb=2048,
        ports=[8000],
        color="#059669",
    ),
    Preset(
        id="discord-bot",
        name="Discord Bot",
        category="Bot",
        command="python3 bot.py",
        description="Long-running Discord bot process.",
        cpu=0.5,
        ram_mb=256,
        disk_mb=1024,
        color="#5865F2",
    ),
    Preset(
        id="telegram-bot",
        name="Telegram Bot",
        category="Bot",
        command="python3 bot.py",
        description="Long-running Telegram bot process.",
        cpu=0.5,
        ram_mb=256,
        disk_mb=1024,
        color="#229ED9",
    ),
    Preset(
        id="nginx",
        name="Nginx / Website",
        category="Web",
        kind="docker",
        image="nginx:alpine",
        description="Static website / reverse proxy via Docker.",
        cpu=0.5,
        ram_mb=128,
        disk_mb=1024,
        ports=[80],
        color="#009639",
    ),
    Preset(
        id="postgres",
        name="PostgreSQL",
        category="Database",
        kind="docker",
        image="postgres:16-alpine",
        description="PostgreSQL database (set POSTGRES_PASSWORD in env).",
        cpu=2,
        ram_mb=2048,
        disk_mb=10240,
        ports=[5432],
        color="#336791",
    ),
    Preset(
        id="redis",
        name="Redis",
        category="Database",
        kind="docker",
        image="redis:7-alpine",
        description="In-memory key/value store.",
        cpu=1,
        ram_mb=512,
        disk_mb=1024,
        ports=[6379],
        color="#DC382D",
    ),
    Preset(
        id="minecraft",
        name="Minecraft Server",
        category="Game",
        kind="docker",
        image="itzg/minecraft-server",
        description="Minecraft Java server via Docker.",
        cpu=2,
        ram_mb=4096,
        disk_mb=20480,
        ports=[25565],
        color="#62B47A",
    ),
    Preset(
        id="code-server",
        name="VS Code Server",
        category="IDE",
        kind="docker",
        image="codercom/code-server:latest",
        command="--auth none",
        description="VS Code в браузере на блоке. Без пароля (--auth none); для доступа извне задай PASSWORD и убери --auth none.",
        cpu=1,
        ram_mb=1024,
        disk_mb=4096,
        ports=[8080],
        color="#007ACC",
    ),
    Preset(
        id="opencode",
        name="OpenCode",
        category="IDE",
        command="opencode serve --hostname 0.0.0.0 --port 4096",
        description="Headless OpenCode server на блоке (нужен установленный opencode; команду можно изменить).",
        cpu=1,
        ram_mb=2048,
        disk_mb=4096,
        ports=[4096],
        color="#7c3aed",
    ),
    Preset(
        id="custom",
        name="Custom",
        category="Custom",
        command="",
        description="Bring your own command or Docker image.",
        cpu=1,
        ram_mb=512,
        disk_mb=2048,
        color="#8b97b8",
    ),
]


def get_preset(preset_id: str) -> Optional[Preset]:
    return next((p for p in PRESETS if p.id == preset_id), None)
