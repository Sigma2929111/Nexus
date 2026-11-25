"""Hosting layer.

Application execution lives in ``nexus.block_agent.execution.manager`` because
apps run on BLOCK agents. This module exposes the shared vocabulary and the
manager for convenience.
"""
from nexus.block_agent.execution.manager import ProcessManager  # noqa: F401

APP_KINDS = [
    "process",
    "docker",
]

APP_CATEGORIES = [
    "web",
    "website",
    "api",
    "discord_bot",
    "telegram_bot",
    "game_server",
    "database",
    "custom_container",
    "code_server",
    "ai_service",
    "worker",
]
