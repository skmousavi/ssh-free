#!/usr/bin/env python3

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.utils import run_command


def installed_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "ssh-free"


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pid_alive(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def terminate_pid(pid: int) -> None:
    run_command(["taskkill", "/PID", str(int(pid)), "/F", "/T"])


def kill_processes_matching(pattern: str) -> None:
    extra = ""
    if "tun2socks" in pattern:
        name_cond = "$_.Name -like '*tun2socks*'"
        needle = "tun2socks"
    elif "-R" in pattern:
        name_cond = "$_.Name -eq 'ssh.exe'"
        needle = pattern.split("-R")[-1].lstrip(".*")
        extra = " -and $_.CommandLine -like '*-R*'"
    elif "-D" in pattern:
        name_cond = "$_.Name -eq 'ssh.exe'"
        needle = "127.0.0.1"
        extra = " -and $_.CommandLine -like '*-D*'"
    else:
        name_cond = "$_.Name -eq 'ssh.exe'"
        needle = pattern

    # Only kill the actual ssh/tun2socks child processes, never ourselves.
    # (The needle can be a host/IP that also appears in this launcher's own
    # command line, so a name filter + PID guard is essential.)
    ps_script = (
        f"$n='{needle}'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { "
        f"{name_cond} -and $_.ProcessId -ne $PID -and "
        f"$_.CommandLine -and $_.CommandLine -like \"*$n*\"{extra} }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    run_command(["powershell", "-NoProfile", "-Command", ps_script], timeout=20)


def find_pid_by_pattern(pattern: str) -> Optional[int]:
    if "-R" in pattern:
        needle = pattern.split("-R")[-1].lstrip(".*")
    else:
        needle = pattern

    ps_script = (
        f"$n='{needle}'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'ssh.exe' -and $_.CommandLine -like \"*$n*\" } | "
        "Select-Object -First 1 -ExpandProperty ProcessId"
    )
    code, out, _ = run_command(
        ["powershell", "-NoProfile", "-Command", ps_script],
        timeout=15,
    )
    if code == 0 and out.strip().isdigit():
        return int(out.strip())
    return None


def wrap_ssh_command(cmd: list) -> list:
    return cmd


def get_user_home() -> Tuple[str, str]:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    home = os.path.expanduser("~")
    return user, home


def get_default_interface() -> Optional[str]:
    code, out, _ = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1).InterfaceAlias",
        ],
        timeout=10,
    )
    if code == 0 and out.strip():
        return out.strip().splitlines()[0]
    return "Ethernet"


def get_default_gateway() -> Optional[str]:
    code, out, _ = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1).NextHop",
        ],
        timeout=10,
    )
    if code == 0 and out.strip():
        return out.strip().splitlines()[0]
    return None


def find_process_in_list(names: List[str]) -> Optional[str]:
    code, out, _ = run_command(
        ["tasklist", "/FO", "CSV", "/NH"],
        timeout=15,
    )
    if code != 0:
        return None
    lower_blob = out.lower()
    for name in names:
        if name.lower() in lower_blob:
            return name
    return None


def start_detached(args: list, env: dict, cwd: str = None) -> int:
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        cwd=cwd,
        creationflags=creationflags,
        close_fds=True,
    )
    return proc.pid


def ssh_executable() -> str:
    path = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32",
        "OpenSSH",
        "ssh.exe",
    )
    if os.path.isfile(path):
        return path
    return "ssh"


def supports_client_tun() -> bool:
    return False


def enable_console_colors() -> None:
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
