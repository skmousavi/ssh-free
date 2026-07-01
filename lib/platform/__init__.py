#!/usr/bin/env python3
"""OS-specific helpers (Linux + Windows client)."""

import sys

from lib.platform import linux as _linux
from lib.platform import windows as _windows


def _mod():
    return _windows if sys.platform == "win32" else _linux


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return not is_windows()


def name() -> str:
    return "windows" if is_windows() else "linux"


def installed_root():
    return _mod().installed_root()


def is_elevated() -> bool:
    return _mod().is_elevated()


def pid_alive(pid: int) -> bool:
    return _mod().pid_alive(pid)


def terminate_pid(pid: int) -> None:
    _mod().terminate_pid(pid)


def kill_processes_matching(pattern: str) -> None:
    _mod().kill_processes_matching(pattern)


def find_pid_by_pattern(pattern: str):
    return _mod().find_pid_by_pattern(pattern)


def wrap_ssh_command(cmd: list) -> list:
    return _mod().wrap_ssh_command(cmd)


def get_user_home() -> tuple:
    return _mod().get_user_home()


def get_default_interface():
    return _mod().get_default_interface()


def get_default_gateway():
    return _mod().get_default_gateway()


def find_process_in_list(names: list):
    return _mod().find_process_in_list(names)


def start_detached(args: list, env: dict, cwd: str = None) -> int:
    return _mod().start_detached(args, env, cwd)


def ssh_executable() -> str:
    return _mod().ssh_executable()


def supports_client_tun() -> bool:
    return _mod().supports_client_tun()


def enable_console_colors() -> None:
    _mod().enable_console_colors()
