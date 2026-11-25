# NEXUS Architecture

## Roles

### MASTER (`nexus/master`)
Central controller. Runs a FastAPI app (ASGI) with:

- **`core/db.py`** — SQLite engine (SQLModel). State in `~/.nexus/nexus.db`.
- **`core/models_db.py`** — tables: `Block`, `PairingToken`, `Application`,
  `Metric`, `AuditLog`.
- **`core/app.py`** — app factory, router wiring, SPA serving, offline watchdog,
  mDNS advertising.
- **`core/state.py`** — runtime config + live WebSocket connections + pending
  request futures.
- **`core/commands.py`** — request/response RPC to an agent over its WebSocket.
- **`registry/registry.py`** — pairing, authentication, heartbeat, lifecycle,
  metrics, audit.
- **`resource_manager/manager.py`** — quota math (physical/offered/allocated/
  available/reserved) and `can_host`.
- **`scheduler/scheduler.py`** — placement of apps onto blocks.
- **`security/auth.py`** — admin JWT (HS256, minimal implementation).
- **`api/*`** — auth, blocks, apps, monitoring, security, inference, agent WS.

### BLOCK (`nexus/block_agent`)
Worker agent. Runs as the unprivileged user:

- **`transport/client.py`** — WebSocket client (TLS, optional CA pinning).
- **`monitoring/collector.py`** — psutil-based CPU/RAM/Disk/Net + `nvidia-smi`.
- **`resource_reporter/reporter.py`** — heartbeat construction.
- **`execution/manager.py`** — process manager (subprocess, rlimit, Docker opt.).
- **`agent/agent.py`** — pairing, reconnect loop, heartbeat, command dispatch.

## Connection & pairing

1. Admin creates a **single-use pairing token** in the panel
   (`POST /api/v1/blocks`). Only its SHA-256 hash is stored.
2. The agent calls `POST /api/v1/blocks/pair` with the token, its name, IP and a
   resource snapshot.
3. MASTER validates and consumes the token, creates the block with a fresh
   random secret (stored hashed), and returns `block_id` + `block_secret` once.
4. The agent saves the secret and opens a **WebSocket** to
   `/api/v1/agent/ws`, sending `hello {block_id, secret}`.
5. Heartbeats flow over the same socket. MASTER marks the block `ONLINE`; the
   watchdog marks it `OFFLINE` if heartbeats stop (`offline_after`).

The agent always **dials out** to the MASTER, so NAT/CGNAT does not require
inbound access. There is no Connector or Relay server.

### Message types (`nexus/shared/protocol.py`)

`hello`, `hello_ok`, `heartbeat`, `heartbeat_ack`, `command`, `command_result`,
`log`, `error`.

Commands: `app.create|start|stop|restart|delete|logs`, `agent.restart`.
Each command carries a `request_id`; the agent replies with `command_result`,
which MASTER resolves to the waiting REST call.

## Resource model

For each block and each resource kind (`cpu`, `ram`, `disk`, `gpu`):

```
physical   - what the machine reports (via heartbeat snapshot)
offered    - what the owner enabled for NEXUS (amount or full, minus reserved)
allocated  - sum of limits of active apps placed on the block
available  - max(offered - allocated, 0)
reserved   - kept for the host machine
```

Physical resources are **per block**. The platform never sums VRAM/RAM of
different machines into one device. Aggregate numbers in the Overview are sums
of quotas, clearly not a single device.

## Hosting

`ProcessManager` on each block runs apps as subprocesses in their own directory
under `~/.nexus/apps/<app_id>`, with logs in `app.log`.

- Process apps: shell command, environment, working dir, memory rlimit.
- Docker apps: used only if `docker` exists; otherwise a clear error.
- Hard CPU quotas require cgroups (root) — unavailable without root, reported
  honestly.

## Distributed inference (`nexus/inference/engine.py`)

`plan_pipeline(model, blocks)` computes whether a model's layers fit across the
blocks' usable VRAM, distributes layers proportionally, and returns a plan with
per-stage VRAM needs plus warnings about network latency. It is a **planner**,
not a fake executor: it explicitly states that running the split model needs a
compatible backend on the blocks.

## Security

- Admin: password hashed with PBKDF2-SHA256; JWT session tokens (12h).
- Blocks: unique random secrets, stored as SHA-256 hashes; revoke rotates them.
- Pairing tokens: single-use, hashed.
- TLS: self-signed certificate generated on first MASTER start; agents may pin
  the CA certificate (`--ca`).
- API: bearer auth required for all management endpoints; `/health` is public.
- Audit log of administrative actions.
- No secrets in source; state under `~/.nexus` with restrictive permissions.

## Known constraints

- SQLite is single-node state (MASTER only). Blocks keep no cluster state.
- mDNS is LAN-only.
- Without root, isolation is process-level, not kernel-enforced containers.
