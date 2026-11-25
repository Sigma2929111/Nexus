# NEXUS Cloud

A distributed multi-server control platform. Turn several independent Linux
servers (e.g. Plugged.host Code Servers) into one cluster with a single web
panel — directly connected, with no Connector or Relay server in between.

- **MASTER** — central controller: block registry, resources, scheduler, API,
  web dashboard, monitoring, logs.
- **BLOCK** — a worker server running a Block Agent that reports its hardware,
  sends heartbeats and runs applications.

The same package runs on every machine; the **role is chosen by a command**.

```
nexus up master                                   # this machine = MASTER
nexus up block --master https://IP:8787 --token T # this machine = BLOCK
```

## Highlights

- **Direct MASTER ↔ BLOCK** over TLS WebSocket (works behind NAT — the agent
  dials out). No intermediate server.
- **Honest resource accounting**: per-block quotas
  (`physical / offered / allocated / available / reserved`). Physical resources
  of different machines are **never** merged into one fictional device.
- **Real pairing & security**: single-use pairing tokens, per-block secrets
  (hashed at rest), self-signed TLS with certificate pinning, admin password,
  audit log, request validation.
- **Universal hosting**: web apps, APIs, bots, databases, game/code servers, AI
  services, background workers — process-based isolation with rlimits, Docker
  when available.
- **Distributed inference foundation**: a real feasibility planner for splitting
  one model across blocks (pipeline parallelism) that reports GPU/VRAM/network
  requirements honestly.
- **Dashboard**: React/Vite SPA (prebuilt) — Overview, Blocks, Applications,
  Containers, AI Infrastructure, Monitoring, Logs, Settings, Security.
- **No root required**; state lives in `~/.nexus`.

## Quick start

```bash
# 1. install (same on every server)
tar -xzf nexus-cloud-*.tar.gz && cd nexus-cloud-*
bash deployment/install.sh
export PATH="$HOME/.local/bin:$PATH"

# 2. MASTER
nexus up master            # set admin password, open https://SERVER:8787/

# 3. BLOCK (on another server)
#    panel -> Blocks -> + ADD BLOCK -> copy token
nexus up block --master https://MASTER_IP:8787 --token TOKEN --ca master.crt
```

Full instructions: [`deployment/INSTALL.md`](deployment/INSTALL.md).

## CLI

| Command | Purpose |
|---|---|
| `nexus up master [--port N] [--no-tls]` | start the MASTER + dashboard |
| `nexus up block --master URL --token T [--ca cert] [--discover]` | start a BLOCK agent |
| `nexus role` | show this machine's role |
| `nexus status` | check local MASTER health |
| `nexus discover` | find MASTERs on the LAN (mDNS) |
| `nexus down` | stop the local process |
| `nexus set-password` | change the admin password |

## Architecture

```
            ┌───────────────────────────┐
            │          MASTER           │
            │  FastAPI + SQLite + UI    │
            │  registry / scheduler /   │
            │  resource manager / auth  │
            └───────────┬───────────────┘
        TLS WebSocket   │   (agent dials out; NAT-friendly)
      ┌─────────────────┼──────────────────┐
      ▼                 ▼                  ▼
 ┌─────────┐      ┌─────────┐        ┌─────────┐
 │ BLOCK 1 │      │ BLOCK 2 │        │ BLOCK 3 │
 │ agent   │      │ agent   │        │ agent   │
 │ hosting │      │ hosting │        │ hosting │
 └─────────┘      └─────────┘        └─────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

## Project layout

```
nexus/
├── nexus/
│   ├── cli.py                 # nexus up master|block, role, discover...
│   ├── master/                # API, registry, scheduler, resources, security, UI
│   ├── block_agent/           # agent, monitoring, transport, execution
│   ├── shared/                # protocol models, config, security primitives
│   ├── hosting/               # (see block_agent/execution)
│   ├── inference/             # distributed inference planner
│   └── dashboard/             # React/Vite SPA (+ prebuilt dist/)
├── deployment/                # install/start/stop/update/health + PACKAGE_BUILDER
├── docs/  tests/  scripts/  configs/
```

## Testing

```bash
.venv/bin/python -m pytest -q          # unit + API + websocket tests
.venv/bin/python scripts/e2e_check.py  # real MASTER + real BLOCK end-to-end
```

The e2e check verifies: admin auth, unauthenticated rejection, single-use
pairing, invalid-token rejection, real block ONLINE with reported resources,
overview aggregation, and an honest "not feasible" inference plan without GPUs.

## Honest limitations

- **CPU hard quotas** need cgroups (root). Without root we apply `rlimit` for
  memory and report that hard CPU limits are unavailable.
- **mDNS discovery** works only on the same LAN. Across the internet use an
  explicit MASTER address. There is no public rendezvous service.
- **Distributed inference** is a *planner/foundation*. Actually running a split
  model requires a compatible backend (e.g. Petals or a PyTorch pipeline
  runtime) installed on the blocks; the planner does not download models.
- **GPU/CUDA** are used only when actually present (`nvidia-smi`).
- Blocks behind strict firewalls that block all outbound traffic cannot connect.

## Design decision

This project uses **one package** for both roles (role selected via CLI),
per the owner's choice, instead of fully separate MASTER/BLOCK packages. The
code is still organized in separate modules internally.

## License

Personal project. Add a license before public distribution.
