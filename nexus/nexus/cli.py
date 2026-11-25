"""NEXUS command line interface.

Usage:
  nexus up master                 # start the MASTER + dashboard
  nexus up block --master URL --token TOKEN
  nexus role | status | discover | down
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer

from nexus.shared.config import NexusConfig, Paths
from nexus.shared.logging import setup_logging
from nexus.shared.security import generate_tls_pair, hash_password, cert_fingerprint

app = typer.Typer(add_completion=False, help="NEXUS Cloud control CLI")
up_app = typer.Typer(help="Start this machine as MASTER or BLOCK")
app.add_typer(up_app, name="up")


def _paths() -> Paths:
    paths = Paths.build()
    paths.ensure()
    return paths


def _pid_file() -> Path:
    return Paths.build().home / "nexus.pid"


def _normalize_master(master: str) -> str:
    if "://" not in master:
        return f"https://{master}"
    return master


@up_app.command("master")
def up_master(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8787, help="Port"),
    no_tls: bool = typer.Option(False, "--no-tls", help="Disable TLS (not recommended)"),
    password: Optional[str] = typer.Option(None, help="Admin password (or set NEXUS_ADMIN_PASSWORD)"),
    log_level: str = typer.Option("INFO", help="Log level"),
) -> None:
    """Run this machine as the central MASTER server."""
    setup_logging(log_level, "nexus")
    paths = _paths()
    config = NexusConfig.load()
    config.role = "master"
    config.host = host
    config.port = port
    if not config.admin_password_hash:
        pw = password or os.environ.get("NEXUS_ADMIN_PASSWORD") or typer.prompt(
            "Set admin password", hide_input=True, confirmation_prompt=True
        )
        digest, salt = hash_password(pw)
        config.admin_password_hash = digest
        config.admin_password_salt = salt
    config.save()

    ssl_cert = ssl_key = None
    if not no_tls:
        cert, key = generate_tls_pair(paths.tls_dir)
        ssl_cert, ssl_key = str(cert), str(key)
        typer.echo(f"TLS certificate: {cert}")
        typer.echo(f"TLS fingerprint: {cert_fingerprint(cert)}")

    _pid_file().write_text(str(os.getpid()))

    from nexus.master.core.app import create_app

    fastapi_app = create_app(config)
    scheme = "http" if no_tls else "https"
    typer.echo(f"NEXUS MASTER listening on {scheme}://{host}:{port}")
    typer.echo(f"Dashboard: {scheme}://127.0.0.1:{port}/")

    import uvicorn

    try:
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            ssl_certfile=ssl_cert,
            ssl_keyfile=ssl_key,
        )
    finally:
        if _pid_file().exists():
            _pid_file().unlink()


@up_app.command("block")
def up_block(
    master: Optional[str] = typer.Option(None, help="MASTER url or host:port"),
    token: Optional[str] = typer.Option(None, help="One-time pairing token"),
    name: Optional[str] = typer.Option(None, help="Block display name"),
    ca: Optional[str] = typer.Option(None, help="MASTER TLS certificate to pin"),
    discover: bool = typer.Option(False, "--discover", help="Find MASTER via mDNS on LAN"),
    log_level: str = typer.Option("INFO", help="Log level"),
) -> None:
    """Run this machine as a BLOCK agent and connect it to a MASTER."""
    setup_logging(log_level, "nexus")
    _paths()
    config = NexusConfig.load()
    config.role = "block"
    if name:
        config.block_name = name
    if master:
        config.master_url = _normalize_master(master)
    elif discover:
        from nexus.master.core.mdns import discover_masters

        typer.echo("Searching for MASTER via mDNS...")
        found = discover_masters()
        if not found:
            typer.echo("No MASTER found on the local network.", err=True)
            raise typer.Exit(1)
        addr = found[0]["addresses"][0]
        config.master_url = f"https://{addr}:{found[0]['port']}"
        typer.echo(f"Found MASTER: {config.master_url}")
    config.save()

    from nexus.block_agent.agent.agent import BlockAgent

    agent = BlockAgent(config, pairing_token=token, ca_path=ca)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        typer.echo("stopping block agent")


@app.command()
def role() -> None:
    """Show this machine's configured role."""
    config = NexusConfig.load()
    typer.echo(f"role: {config.role}")
    if config.role == "master":
        typer.echo(f"bind: {config.host}:{config.port}")
    elif config.role == "block":
        typer.echo(f"master: {config.master_url}")
        typer.echo(f"block_id: {config.block_id}")


@app.command()
def discover(timeout: float = typer.Option(4.0, help="Search duration (s)")) -> None:
    """Discover MASTER servers on the local network via mDNS."""
    from nexus.master.core.mdns import discover_masters

    found = discover_masters(timeout)
    if not found:
        typer.echo("No MASTER found.")
        return
    for item in found:
        typer.echo(f"{item['name']} -> {', '.join(item['addresses'])}:{item['port']}")


@app.command()
def status() -> None:
    """Check the local MASTER health (if this machine is a MASTER)."""
    config = NexusConfig.load()
    if config.role != "master":
        role()
        return
    import httpx

    last_error = None
    for scheme in ("https", "http"):
        url = f"{scheme}://127.0.0.1:{config.port}/api/v1/health"
        try:
            resp = httpx.get(url, verify=False, timeout=5)
            typer.echo(f"{url} -> {resp.status_code} {resp.text}")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    typer.echo(f"MASTER not reachable: {last_error}", err=True)
    raise typer.Exit(1)


@app.command()
def down() -> None:
    """Stop the locally running NEXUS process."""
    pid_file = _pid_file()
    if not pid_file.exists():
        typer.echo("No running NEXUS process found.")
        return
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"Sent SIGTERM to {pid}")
    except ProcessLookupError:
        typer.echo("Process already gone.")
    finally:
        pid_file.unlink(missing_ok=True)


@app.command("set-password")
def set_password(password: Optional[str] = typer.Option(None, help="New admin password")) -> None:
    """Set or change the MASTER admin password."""
    _paths()
    config = NexusConfig.load()
    pw = password or typer.prompt("New admin password", hide_input=True, confirmation_prompt=True)
    digest, salt = hash_password(pw)
    config.admin_password_hash = digest
    config.admin_password_salt = salt
    config.save()
    typer.echo("Admin password updated.")


if __name__ == "__main__":
    app()
