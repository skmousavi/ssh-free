# ssh-free

Transparent SSH tunnel with TUN interface and tun2socks — route all traffic through an SSH server with one command.

```bash
sudo ssh-free root@YOUR_SERVER
```

```bash
sudo ssh-free-stop
```

---

## Features

| Feature | Description |
|---------|-------------|
| **One command** | `ssh-free user@host` sets up everything |
| **TUN + tun2socks** | System-wide transparent proxy |
| **Auto Detect** | Network interface, SOCKS5, v2rayN |
| **Auto Recovery** | Reconnects when SSH or internet drops |
| **TUI** | Interactive menu (`ssh-free --tui`) |
| **Traffic stats** | Live RX/TX with `status --watch` |
| **Rule routing** | Domain/IP/CIDR include & exclude |
| **Profiles** | Quick switch with `--profile` |
| **Doctor** | Pre-flight diagnostics |
| **Status** | Live session health |
| **Cleanup** | Full network restore on stop |
| **Logging** | Rotating logs in `logs/` |
| **systemd** | Optional monitor service |

---

## Requirements

- Linux with TUN/TAP (`/dev/net/tun`)
- Python 3.8+ with **PyYAML** (`sudo apt install python3-yaml`)
- root / sudo
- `ip`, `iptables`, `openssh-client`, `curl`

---

## Install

```bash
git clone https://github.com/YOUR_USERNAME/ssh-free.git
cd ssh-free
sudo ./install.sh
```

Or via Makefile:

```bash
make install
```

---

## Usage

## Two modes

| Mode | Command | What it does |
|------|---------|--------------|
| **server-proxy** (default) | `ssh-free user@host` | Server uses **your** v2rayN/internet for `apt`, `curl`, downloads |
| **client-tun** | `ssh-free --client-tun user@host` | **Your laptop** routes all traffic through the server (TUN) |

### server-proxy (your use case)

```
Laptop v2rayN :10808  ←──SSH -R──  Server :10809 (SOCKS)
```

After connect, **you are dropped into the server shell** — `apt update`, `curl`, and downloads work automatically.

```bash
# v2rayN must be running first
ssh-free root@YOUR_SERVER
# → opens SSH on server, proxy already active
```

Background only (no shell): `ssh-free --detach root@host`  
Stop tunnel: `ssh-free-stop`

### Connect

```bash
sudo ssh-free root@YOUR_SERVER
```

First run without config opens an **interactive wizard**.

**SSH keys under sudo:** `ssh-free` uses **your user's** `~/.ssh/` keys (not root's), even when run with `sudo`. If auth fails:

```bash
ssh-copy-id root@YOUR_SERVER    # once, as normal user
# or with ssh-agent:
sudo SSH_AUTH_SOCK=$SSH_AUTH_SOCK ssh-free root@YOUR_SERVER
```

Set a specific key in `config/user.yml`:

```yaml
ssh:
  identity_file: ~/.ssh/id_ed25519
```

### Stop

```bash
sudo ssh-free-stop
```

### Interactive TUI

```bash
sudo ssh-free --tui
# or
sudo tui
```

### Profiles

```bash
sudo ssh-free --profiles
sudo ssh-free --profile home
sudo ssh-free home          # shorthand if profile exists
```

### Live traffic

```bash
sudo status --watch
sudo status --watch --interval 1
```

### Rule-based routing

Edit `config/user.yml`:

```yaml
routing:
  mode: rules
  include:
    - github.com
    - gitlab.com
    - 142.250.0.0/15
  exclude:
    - 192.168.0.0/16
```

Modes: `full` | `split` | `rules`

### Diagnostics

```bash
sudo doctor
sudo status
```

### Force restart

```bash
sudo ssh-free --force root@YOUR_SERVER
```

---

## Configuration

Default settings: `config/default.yml`

User overrides: `config/user.yml` (created by wizard)

```yaml
default_server: home
servers:
  - name: home
    host: 203.0.113.10
    user: root
    port: 22
  - name: backup
    host: 10.0.0.2
    user: admin
    port: 22

ssh:
  reconnect: true
  keepalive: 30
  identity_file: ~/.ssh/id_rsa

socks:
  auto_detect: true
  prefer_external: false

routing:
  mode: full   # full | split

monitor:
  enabled: true
  interval: 10
```

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Apps/DNS   │────▶│  TUN (tun0)  │────▶│  tun2socks  │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │ SOCKS5
                                          ┌──────▼──────┐
                                          │SSH -D tunnel│
                                          └──────┬──────┘
                                                 │
                                          ┌──────▼──────┐
                                          │ Remote SSH  │
                                          └─────────────┘
```

1. SSH dynamic port forward creates local SOCKS5
2. TUN interface captures IP traffic
3. tun2socks sends TUN packets through SOCKS5
4. Policy routing sends default traffic to TUN
5. SSH server IP bypasses tunnel (no loop)

---

## Project Structure

```
ssh-free/
├── bin/           CLI entry points
├── config/        YAML configuration
├── lib/           Python modules
├── services/      systemd units
├── logs/          Application logs
├── runtime/       PIDs, session state
└── tests/         Unit tests
```

---

## Development

```bash
# Run from repo (no install)
export SSH_FREE_ROOT=$(pwd)
sudo -E python3 bin/ssh-free root@host

# Lint
make lint

# Tests
make test
```

---

## Version Roadmap

- **V1** — SSH, TUN, tun2socks, routing, NAT, cleanup ✅
- **V2** — Doctor, auto-detect, auto-recover, config, multi-server ✅
- **V3** — TUI, traffic stats, profiles, rule-based routing ✅

---

## License

MIT — see [LICENSE](LICENSE)
