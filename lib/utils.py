#!/usr/bin/env python3

import json
import shutil
import socket
import subprocess
import os
import platform
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import yaml

from lib.logger import log

def run_command(
    command: List[str],
    check: bool = False,
    timeout: int = 20,
) -> Tuple[int, str, str]:

    """
    Execute shell command.

    Returns:
        (returncode, stdout, stderr)
    """

    try:

        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=check,
        )

        return (
            process.returncode,
            process.stdout.strip(),
            process.stderr.strip(),
        )

    except subprocess.TimeoutExpired:

        return -1, "", "Command timeout"

    except Exception as e:

        return -1, "", str(e)
    
def command_exists(command: str) -> bool:

    return shutil.which(command) is not None

def which(command: str) -> Optional[str]:

    return shutil.which(command)


def find_tun2socks(config: Optional[dict] = None) -> Optional[str]:
    """Locate tun2socks binary (PATH, install dir, config override)."""
    import sys

    if sys.platform == "win32":
        return None

    from lib.paths import BIN_DIR, TUN2SOCKS_BIN

    if config:
        custom = config.get("tun2socks", {}).get("binary")
        if custom and os.path.isfile(custom) and os.access(custom, os.X_OK):
            return custom

    for name in ("tun2socks", "tun2socks-linux-amd64", "badvpn-tun2socks"):
        path = which(name)
        if path:
            return path

    for candidate in (TUN2SOCKS_BIN, BIN_DIR / "tun2socks", Path("/opt/ssh-free/bin/tun2socks")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None

def is_root() -> bool:
    from lib.platform import is_elevated
    return is_elevated()

def file_exists(path: str) -> bool:

    return Path(path).exists()
def ensure_directory(path: str):

    Path(path).mkdir(
        parents=True,
        exist_ok=True,
    )

def read_yaml(path: str):

    with open(path, "r") as f:

        return yaml.safe_load(f)
    
def write_yaml(path: str, data):

    with open(path, "w") as f:

        yaml.dump(
            data,
            f,
            default_flow_style=False,
        )

def human_size(size):

    units = ["B", "KB", "MB", "GB", "TB"]

    index = 0

    while size >= 1024 and index < len(units) - 1:

        size /= 1024

        index += 1

    return f"{size:.2f} {units[index]}"

def is_port_open(host: str, port: int) -> bool:

    sock = socket.socket()
    sock.settimeout(1)

    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()
    

def get_kernel():

    return platform.release()

def get_arch():

    return platform.machine()

def get_os():

    return platform.system()

def run_json(command: List[str]):

    code, out, err = run_command(command)

    if code != 0:

        return None

    try:

        return json.loads(out)

    except:

        return None
    

def get_default_interface():
    from lib.platform import get_default_interface as _iface
    return _iface()


def get_default_gateway():
    from lib.platform import get_default_gateway as _gw
    return _gw()


def get_ip(interface):

    data = run_json(
        [
            "ip",
            "-j",
            "addr",
            "show",
            interface,
        ]
    )

    if not data:

        return None

    for addr in data[0]["addr_info"]:

        if addr["family"] == "inet":

            return addr["local"]

    return None



def internet_available():

    return is_port_open("1.1.1.1", 53)


def ssh_version():

    code, out, err = run_command(
        [
            "ssh",
            "-V",
        ]
    )

    text = err if err else out

    return text


def hostname():

    return platform.node()


from datetime import datetime

def now():

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


