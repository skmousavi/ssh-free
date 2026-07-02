#!/usr/bin/env python3

import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.utils import run_command


def installed_root() -> Path:
    return Path("/opt/ssh-free")


def is_elevated() -> bool:
    return os.geteuid() == 0


def pid_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError, OSError):
        return False


def terminate_pid(pid: int) -> None:
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError, OSError):
        return
    try:
        os.kill(int(pid), signal.SIGKILL)
    except (ProcessLookupError, ValueError, OSError):
        pass


def kill_processes_matching(pattern: str) -> None:
    run_command(["pkill", "-f", pattern])


def find_pid_by_pattern(pattern: str) -> Optional[int]:
    code, out, _ = run_command(["pgrep", "-f", pattern])
    if code == 0 and out:
        try:
            return int(out.splitlines()[0])
        except ValueError:
            pass
    return None


def wrap_ssh_command(cmd: list) -> list:
    if not is_elevated() or not os.environ.get("SUDO_USER"):
        return cmd

    from lib.ssh_context import build_ssh_env, get_invoking_user

    _, home = get_invoking_user()
    env = build_ssh_env()
    sudo_user = os.environ["SUDO_USER"]
    try:
        idx = next(
            i for i, p in enumerate(cmd)
            if os.path.basename(str(p)).lower() in ("ssh", "ssh.exe")
        )
    except StopIteration:
        return cmd

    return (
        cmd[:idx]
        + [
            "sudo",
            "-u",
            sudo_user,
            "env",
            f"HOME={env.get('HOME', home)}",
            f"USER={sudo_user}",
            f"SSH_AUTH_SOCK={env.get('SSH_AUTH_SOCK', '')}",
        ]
        + cmd[idx:]
    )


def get_user_home() -> Tuple[str, str]:
    import pwd

    if is_elevated() and os.environ.get("SUDO_USER"):
        user = os.environ["SUDO_USER"]
        try:
            home = pwd.getpwnam(user).pw_dir
        except KeyError:
            home = f"/home/{user}"
        return user, home

    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "root"
    try:
        home = os.environ.get("HOME") or pwd.getpwnam(user).pw_dir
    except KeyError:
        home = os.path.expanduser("~")
    return user, home


def get_default_interface() -> Optional[str]:
    from lib.utils import run_json

    data = run_json(["ip", "-j", "route", "show", "default"])
    if not data:
        return None
    return data[0].get("dev")


def get_default_gateway() -> Optional[str]:
    from lib.utils import run_json

    data = run_json(["ip", "-j", "route", "show", "default"])
    if not data:
        return None
    for route in data:
        gw = route.get("gateway")
        if gw:
            return gw
    return None


def find_process_in_list(names: List[str]) -> Optional[str]:
    code, out, _ = run_command(["ps", "aux"])
    if code != 0:
        return None
    for line in out.splitlines():
        lower = line.lower()
        if "grep" in lower:
            continue
        for name in names:
            if name.lower() in lower:
                return name
    return None


def start_detached(args: list, env: dict, cwd: str = None) -> int:
    pid = os.fork()
    if pid > 0:
        return pid

    os.setsid()
    sys.stdin = open(os.devnull)
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")
    os.execve(args[0], args, env)
    sys.exit(1)


def ssh_executable() -> str:
    return "ssh"


def supports_client_tun() -> bool:
    return True


def enable_console_colors() -> None:
    pass
