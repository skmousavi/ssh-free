#!/usr/bin/env python3
"""Server profile management."""

import copy
from typing import Any, Dict, List, Optional

from lib.config import deep_merge, load_config, save_user_config
from lib.paths import USER_CONFIG


def list_profiles(config: Optional[Dict] = None) -> List[Dict[str, Any]]:
    config = config or load_config()
    servers = config.get("servers") or []

    if not servers:
        ssh_cfg = config.get("ssh", {})
        if ssh_cfg.get("host"):
            return [
                {
                    "name": config.get("default_server", "default"),
                    "host": ssh_cfg["host"],
                    "user": ssh_cfg.get("user", "root"),
                    "port": ssh_cfg.get("port", 22),
                    "default": True,
                }
            ]
        return []

    default_name = config.get("default_server")
    result = []
    for srv in servers:
        result.append(
            {
                **srv,
                "default": srv.get("name") == default_name,
            }
        )
    return result


def get_profile(config: Dict, name: str) -> Optional[Dict[str, Any]]:
    for profile in list_profiles(config):
        if profile.get("name") == name:
            return profile
    return None


def set_default_profile(name: str):
    config = load_config()
    if not get_profile(config, name):
        raise ValueError(f"Profile not found: {name}")

    user_data = {}
    if USER_CONFIG.exists():
        from lib.utils import read_yaml
        user_data = read_yaml(str(USER_CONFIG)) or {}

    user_data["default_server"] = name
    save_user_config(user_data)


def add_profile(profile: Dict[str, Any]):
    config = load_config()
    user_data = {}
    if USER_CONFIG.exists():
        from lib.utils import read_yaml
        user_data = read_yaml(str(USER_CONFIG)) or {}

    servers = user_data.get("servers") or list_profiles(config)
    name = profile["name"]

    servers = [s for s in servers if s.get("name") != name]
    servers.append(profile)
    user_data["servers"] = servers

    if not user_data.get("default_server"):
        user_data["default_server"] = name

    save_user_config(user_data)


def remove_profile(name: str):
    from lib.utils import read_yaml

    if not USER_CONFIG.exists():
        raise ValueError("No user profiles configured")

    user_data = read_yaml(str(USER_CONFIG)) or {}
    servers = user_data.get("servers", [])
    servers = [s for s in servers if s.get("name") != name]

    if not servers:
        raise ValueError("Cannot remove last profile")

    user_data["servers"] = servers
    if user_data.get("default_server") == name:
        user_data["default_server"] = servers[0]["name"]

    save_user_config(user_data)


def resolve_server_by_profile(config: Dict, profile_name: str) -> Dict[str, Any]:
    profile = get_profile(config, profile_name)
    if not profile:
        raise ValueError(f"Profile not found: {profile_name}")

    return {
        "user": profile.get("user", "root"),
        "host": profile["host"],
        "port": profile.get("port", 22),
        "name": profile.get("name"),
        "source": "profile",
    }


def apply_profile_overrides(config: Dict, server: Dict) -> Dict:
    """Merge per-profile routing/dns settings into active config."""
    merged = copy.deepcopy(config)
    profile = None

    if server.get("name"):
        profile = get_profile(config, server["name"])

    if not profile:
        return merged

    for key in ("routing", "dns", "nat", "monitor"):
        if key in profile:
            merged[key] = deep_merge(merged.get(key, {}), profile[key])

    return merged


def profile_target(server: Dict) -> str:
    user = server.get("user", "root")
    host = server["host"]
    port = server.get("port", 22)
    if port != 22:
        return f"{user}@{host}:{port}"
    return f"{user}@{host}"
