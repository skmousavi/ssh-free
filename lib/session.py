#!/usr/bin/env python3
"""Session state persistence."""

import json
from typing import Any, Dict

from lib.paths import RUNTIME_DIR, SESSION_FILE
from lib.utils import get_default_interface, now


def save_session(data: Dict[str, Any]):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    data["started_at"] = data.get("started_at") or now()
    SESSION_FILE.write_text(json.dumps(data, indent=2))


def load_session() -> Dict[str, Any]:
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def build_session(
    server: Dict,
    tun_name: str = "",
    socks_port: int = 0,
    socks_source: str = "ssh",
    ssh_pid: int = 0,
    tun2socks_pid: int = 0,
    physical_iface: str = None,
    profile: str = None,
    routing_mode: str = "full",
    tunnel_mode: str = "client-tun",
    remote_proxy_url: str = "",
    local_socks_port: int = 0,
) -> Dict[str, Any]:
    return {
        "server": server,
        "tunnel_mode": tunnel_mode,
        "tun_name": tun_name,
        "socks_port": socks_port,
        "socks_source": socks_source,
        "ssh_pid": ssh_pid,
        "tun2socks_pid": tun2socks_pid,
        "physical_iface": physical_iface or get_default_interface(),
        "profile": profile,
        "routing_mode": routing_mode,
        "remote_proxy_url": remote_proxy_url,
        "local_socks_port": local_socks_port,
        "started_at": now(),
    }
