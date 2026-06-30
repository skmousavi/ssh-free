#!/usr/bin/env python3
"""Project path constants."""

import os
from pathlib import Path

# Installed layout: /opt/ssh-free/...  |  Dev layout: repo root
if os.environ.get("SSH_FREE_ROOT"):
    ROOT = Path(os.environ["SSH_FREE_ROOT"])
elif Path("/opt/ssh-free/lib/logger.py").exists():
    ROOT = Path("/opt/ssh-free")
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = ROOT / "logs"
BIN_DIR = ROOT / "bin"

DEFAULT_CONFIG = CONFIG_DIR / "default.yml"
USER_CONFIG = CONFIG_DIR / "user.yml"
SESSION_FILE = RUNTIME_DIR / "session.json"
STATUS_FILE = RUNTIME_DIR / "status.json"
LOCK_FILE = RUNTIME_DIR / "lock"
SSH_PID_FILE = RUNTIME_DIR / "ssh.pid"
TUN2SOCKS_PID_FILE = RUNTIME_DIR / "tun2socks.pid"
MONITOR_PID_FILE = RUNTIME_DIR / "monitor.pid"
TRAFFIC_FILE = RUNTIME_DIR / "traffic.json"
TUN2SOCKS_BIN = BIN_DIR / "tun2socks"
