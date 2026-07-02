#!/usr/bin/env python3
"""
Run server-side scripts with the right privilege level.

ssh-free's server steps (enable sshd forwarding, write proxy config under
/etc, reload sshd, write /var/run state) need root. The SSH user may be a
non-root account, so we transparently escalate with sudo:

  * uid 0            -> run directly
  * passwordless sudo -> sudo bash -s
  * sudo w/ password  -> prompt once, feed via `sudo -S` (password is the
                         first stdin line; the rest is the script)
  * no root/sudo      -> run as-is (privileged ops will fail with a clear
                         permission error)

The chosen method is cached per server for the session.
"""

import getpass
import sys
from typing import Dict, Optional

from lib.logger import log
from lib.ssh_context import build_ssh_env, run_remote_bash

_priv_cache: Dict[str, "Privilege"] = {}


class Privilege:
    def __init__(self, mode: str, password: Optional[str] = None):
        self.mode = mode  # root | sudo | sudo_pw | none
        self.password = password


def _server_key(server: Dict) -> str:
    return f"{server.get('user', 'root')}@{server['host']}:{server.get('port', 22)}"


def _base_ssh(server: Dict, config: Dict) -> list:
    from lib.server_proxy import _ssh_base_cmd

    return _ssh_base_cmd(server, config)


def reset_privilege(server: Optional[Dict] = None) -> None:
    if server is None:
        _priv_cache.clear()
    else:
        _priv_cache.pop(_server_key(server), None)


def resolve_privilege(server: Dict, config: Dict, quiet: bool = False) -> Privilege:
    key = _server_key(server)
    cached = _priv_cache.get(key)
    if cached is not None:
        return cached

    probe = (
        "id -u; "
        "if command -v sudo >/dev/null 2>&1; then "
        "  if sudo -n true 2>/dev/null; then echo SUDO_NP; else echo SUDO_PW; fi; "
        "else echo NOSUDO; fi"
    )
    result = run_remote_bash(
        _base_ssh(server, config) + ["bash", "-s"],
        probe,
        build_ssh_env(),
        20,
    )
    out = result.stdout or ""
    tokens = out.split()
    uid = None
    if tokens:
        try:
            uid = int(tokens[0])
        except ValueError:
            uid = None

    if uid == 0:
        priv = Privilege("root")
    elif "SUDO_NP" in out:
        priv = Privilege("sudo")
    elif "SUDO_PW" in out:
        if quiet or not sys.stdin.isatty():
            log.warning(
                "Server needs root; sudo requires a password but no terminal "
                "is available to prompt."
            )
            priv = Privilege("none")
        else:
            user = server.get("user", "root")
            host = server["host"]
            try:
                pw = getpass.getpass(
                    f"  [sudo] password for {user}@{host} "
                    f"(needed to configure the server): "
                )
            except (EOFError, KeyboardInterrupt):
                pw = None
            priv = Privilege("sudo_pw", pw) if pw else Privilege("none")
    else:
        priv = Privilege("none")

    _priv_cache[key] = priv
    return priv


def run_privileged(server: Dict, config: Dict, script: str, timeout: int = 45):
    """Run a bash script on the server as root when possible."""
    priv = resolve_privilege(server, config)
    base = _base_ssh(server, config)
    env = build_ssh_env()

    if priv.mode == "root" or priv.mode == "none":
        return run_remote_bash(base + ["bash", "-s"], script, env, timeout)

    if priv.mode == "sudo":
        return run_remote_bash(base + ["sudo", "-p", "", "bash", "-s"], script, env, timeout)

    # sudo_pw: password consumed by `sudo -S` as the first stdin line,
    # the remaining stdin is the script for bash.
    wrapped = f"{priv.password}\n{script}"
    return run_remote_bash(
        base + ["sudo", "-S", "-p", "", "bash", "-s"], wrapped, env, timeout
    )
