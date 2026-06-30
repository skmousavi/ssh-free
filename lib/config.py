#!/usr/bin/env python3
"""Configuration loading, merging, and interactive wizard."""

import copy
import getpass
import sys
from typing import Any, Dict, List, Optional

from lib.logger import log
from lib.paths import DEFAULT_CONFIG, USER_CONFIG
from lib.utils import read_yaml, write_yaml


def deep_merge(base: Dict, override: Dict) -> Dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config() -> Dict[str, Any]:
    if not DEFAULT_CONFIG.exists():
        raise FileNotFoundError(f"Default config missing: {DEFAULT_CONFIG}")

    config = read_yaml(str(DEFAULT_CONFIG)) or {}

    if USER_CONFIG.exists():
        user = read_yaml(str(USER_CONFIG)) or {}
        config = deep_merge(config, user)

    return config


def save_user_config(data: Dict[str, Any]):
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(str(USER_CONFIG), data)


def parse_ssh_target(target: str) -> Dict[str, str]:
    """Parse user@host:port into components."""
    port = 22
    user = ""

    if "@" in target:
        user, rest = target.rsplit("@", 1)
    else:
        rest = target

    if ":" in rest:
        host, port_str = rest.rsplit(":", 1)
        if port_str.isdigit():
            port = int(port_str)
        else:
            host = rest
    else:
        host = rest

    return {"user": user, "host": host, "port": port}


def resolve_server(
    config: Dict,
    cli_target: Optional[str],
    profile_name: Optional[str] = None,
) -> Dict[str, Any]:
    if profile_name:
        from lib.profiles import resolve_server_by_profile
        return resolve_server_by_profile(config, profile_name)

    if cli_target and "@" not in cli_target and not cli_target[0].isdigit():
        # Might be profile name only: ssh-free home
        from lib.profiles import get_profile
        profile = get_profile(config, cli_target)
        if profile:
            from lib.profiles import resolve_server_by_profile
            return resolve_server_by_profile(config, cli_target)

    if cli_target:
        parsed = parse_ssh_target(cli_target)
        return {
            "user": parsed["user"] or config.get("ssh", {}).get("user", "root"),
            "host": parsed["host"],
            "port": parsed["port"],
            "source": "cli",
        }

    servers = config.get("servers") or []
    if not servers:
        ssh_cfg = config.get("ssh", {})
        if ssh_cfg.get("host"):
            return {
                "user": ssh_cfg.get("user", "root"),
                "host": ssh_cfg["host"],
                "port": ssh_cfg.get("port", 22),
                "source": "config",
            }
        return {}

    default_name = config.get("default_server")
    if default_name:
        for srv in servers:
            if srv.get("name") == default_name:
                return {**srv, "source": "config"}

    return {**servers[0], "source": "config"}


def run_wizard() -> Dict[str, Any]:
    """Interactive first-run configuration."""
    print()
    print("\033[1;33mNo configuration found.\033[0m")
    print()
    answer = input("Would you like to create one? [Y/n]: ").strip().lower()
    if answer in ("n", "no"):
        print("Aborted.")
        sys.exit(0)

    print()
    host = input("SSH server host/IP: ").strip()
    user = input("SSH username [root]: ").strip() or "root"
    port_str = input("SSH port [22]: ").strip() or "22"
    port = int(port_str) if port_str.isdigit() else 22

    name = input("Profile name [default]: ").strip() or "default"

    use_v2ray = input("Use v2rayN SOCKS if available? [Y/n]: ").strip().lower()
    auto_socks = use_v2ray not in ("n", "no")

    data = {
        "default_server": name,
        "servers": [
            {
                "name": name,
                "host": host,
                "user": user,
                "port": port,
            }
        ],
        "socks": {
            "auto_detect": auto_socks,
        },
        "ssh": {
            "reconnect": True,
            "keepalive": 30,
        },
    }

    save_user_config(data)
    log.info(f"Configuration saved to {USER_CONFIG}")
    return data


def ensure_config(cli_target: Optional[str]) -> Dict[str, Any]:
    config = load_config()

    has_server = bool(resolve_server(config, cli_target))
    if not has_server and not USER_CONFIG.exists():
        run_wizard()
        config = load_config()

    return config
