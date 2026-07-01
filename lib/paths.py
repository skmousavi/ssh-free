#!/usr/bin/env python3
"""Project path constants."""

import os
import sys
from pathlib import Path


def _default_installed_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "ssh-free"
    return Path("/opt/ssh-free")


def _resolve_root() -> Path:
    if os.environ.get("SSH_FREE_ROOT"):
        return Path(os.environ["SSH_FREE_ROOT"])

    installed = _default_installed_root()
    if (installed / "lib" / "logger.py").exists():
        return installed

    return Path(__file__).resolve().parent.parent


ROOT = _resolve_root()

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
TUN2SOCKS_BIN = BIN_DIR / ("tun2socks.exe" if sys.platform == "win32" else "tun2socks")
