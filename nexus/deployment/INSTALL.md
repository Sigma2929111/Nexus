# NEXUS — Installation Guide

NEXUS is a **single package**. The same files run on every server; you choose
the role with a command:

- `nexus up master` — this server becomes the central controller (panel + API).
- `nexus up block`  — this server becomes a worker that connects to a MASTER.

No root, Docker, systemd, CUDA or GPU are required. If a feature needs them,
NEXUS tells you honestly instead of failing silently.

---

## 0. Requirements

- Linux server with a terminal (Plugged.host Code Server works).
- `python3` >= 3.10 **or** internet access so the installer can fetch Python via `uv`.
- Internet access for the first install (to download Python packages).
- The dashboard is shipped **prebuilt**, so `npm`/Node is NOT needed on servers.

---

## 1. Install (both roles)

Copy the archive to the server, extract it, and run the installer:

```bash
tar -xzf nexus-cloud-YYYYMMDD-HHMM.tar.gz
cd nexus-cloud-YYYYMMDD-HHMM
bash deployment/install.sh
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc to persist
```

The installer:
- finds or bootstraps Python,
- creates a local `.venv`,
- installs NEXUS,
- creates the `nexus` launcher in `~/.local/bin`,
- keeps all state in `~/.nexus`.

---

## 2. Start the MASTER

```bash
# foreground (Ctrl+C to stop)
nexus up master

# or background
bash deployment/start.sh master
```

On first run you will set an **admin password**. NEXUS then:
- generates a self-signed TLS certificate (`~/.nexus/tls/`),
- prints the certificate fingerprint,
- starts the panel and API on port `8787`,
- advertises itself via mDNS on the local network.

Open the panel: `https://SERVER_IP:8787/`
(Browsers warn about the self-signed certificate — accept it once.)

Check health:

```bash
bash deployment/health_check.sh
# or
nexus status
```

---

## 3. Add a BLOCK

### 3a. Create a pairing token (in the panel)

Panel → **Blocks** → **+ ADD BLOCK** → enter a name → copy the one-time token.

### 3b. On the BLOCK server

Install NEXUS the same way (step 1), then:

```bash
nexus up block --master https://MASTER_IP:8787 --token TOKEN --name "my-block"
```

If the MASTER uses a self-signed certificate, pin it (recommended):

```bash
# copy ~/.nexus/tls/master.crt from the MASTER to the BLOCK, then:
nexus up block --master https://MASTER_IP:8787 --token TOKEN --ca ./master.crt
```

Or, on the **same LAN**, let the block find the MASTER automatically:

```bash
nexus discover
nexus up block --discover --token TOKEN
```

After connecting, the block appears in the panel as **ONLINE** with its real
CPU / RAM / Disk / GPU and a live heartbeat.

---

## 4. Configure block resources

Panel → **Blocks** → **Resources** for a block. Choose per resource:

- **Enabled** — hand this resource to NEXUS,
- **Full** — offer everything physically available,
- **Amount** — offer a specific amount,
- **Reserved for host** — keep some for the machine itself.

Physical resources of different blocks are **never merged** into one device.

---

## 5. Run applications

Panel → **Applications** → **+ NEW APPLICATION**:

- **process** — run a shell command (e.g. `python3 app.py`),
- **docker** — run a Docker image (only if Docker is available on that block).

Choose a block or let the **scheduler** pick one with enough free resources.
You can Start / Stop / Restart / Delete and view logs.

---

## 6. Stop / update

```bash
bash deployment/stop.sh          # stop the background process
bash deployment/update.sh        # git pull + reinstall
```

---

## 7. Networking & NAT

- MASTER ↔ BLOCK is a **direct** TLS WebSocket connection. There is **no**
  Connector or Relay server.
- The agent opens an **outgoing** connection to the MASTER, so it works behind
  NAT/CGNAT where inbound connections are impossible.
- mDNS discovery works only on the **same LAN**. Across the internet, use the
  MASTER address explicitly (`--master https://IP:8787`).
- If a direct connection is impossible, NEXUS shows a clear error instead of
  pretending it works.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `nexus: command not found` | `export PATH="$HOME/.local/bin:$PATH"` |
| Browser TLS warning | Expected (self-signed). Accept once, or use `--ca` on blocks. |
| Block stays OFFLINE | Check the MASTER URL/port, firewall, and that the token was not used twice. |
| `invalid pairing token` | Tokens are single-use; create a new one in the panel. |
| Dashboard missing | Rebuild with `npm install && npm run build` in `nexus/dashboard`, or use the API. |
| GPU not detected | Ensure `nvidia-smi` is available; otherwise blocks report CPU/RAM/Disk only. |
