#!/usr/bin/env python3
"""Detect local Linux routing capabilities."""

import os
from pathlib import Path
from typing import Dict

from lib.utils import command_exists, run_command

RT_TABLES = Path("/etc/iproute2/rt_tables")


def detect_routing_backend() -> Dict:
    """
    Probe how routing can be configured on this host.

    Note: ssh-free configures routing on the LOCAL machine (the client),
    not on the remote SSH server.
    """
    ip_ok = command_exists("ip")
    policy_ok = False
    rt_tables_exists = RT_TABLES.is_file()
    rt_tables_writable = os.access(str(RT_TABLES.parent), os.W_OK) if RT_TABLES.parent.exists() else False

    if ip_ok:
        code, _, _ = run_command(["ip", "rule", "show"])
        policy_ok = code == 0

    if ip_ok:
        backend = "linux-iproute2"
    elif command_exists("route"):
        backend = "legacy-route"
    else:
        backend = "unknown"

    supports_full = ip_ok
    supports_policy = ip_ok and policy_ok
    supports_split = supports_policy
    supports_rules = supports_policy

    return {
        "backend": backend,
        "ip_available": ip_ok,
        "policy_routing": policy_ok,
        "rt_tables_exists": rt_tables_exists,
        "rt_tables_writable": rt_tables_writable,
        "supports_full": supports_full,
        "supports_policy": supports_policy,
        "supports_split": supports_split,
        "supports_rules": supports_rules,
    }


def resolve_effective_mode(requested: str, backend: Dict) -> str:
    """Pick a routing mode that works on this system."""
    if requested == "full":
        return "full" if backend["supports_full"] else requested

    if requested in ("split", "rules") and not backend["supports_policy"]:
        return "full"

    return requested


def ensure_rt_tables_entry(table_id: int, table_name: str) -> bool:
    """
    Register a named routing table if /etc/iproute2 is available.
    Returns True if registered or already present; False if skipped.
    """
    rt_dir = RT_TABLES.parent
    if not rt_dir.exists():
        try:
            rt_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

    content = ""
    if RT_TABLES.exists():
        content = RT_TABLES.read_text()
        if table_name in content or f" {table_id} " in content:
            return True

    try:
        with open(RT_TABLES, "a") as f:
            f.write(f"\n{table_id} {table_name}\n")
        return True
    except OSError:
        return False
