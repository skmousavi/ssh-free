#!/usr/bin/env python3
"""SSH environment for Linux (sudo) and Windows."""

import glob
import os
import sys
from typing import List, Optional, Tuple

from lib.platform import get_user_home, is_linux, is_windows, wrap_ssh_command


def get_invoking_user() -> Tuple[str, str]:
    return get_user_home()


def resolve_ssh_auth_sock() -> Optional[str]:
    sock = os.environ.get("SSH_AUTH_SOCK")
    if sock and os.path.exists(sock):
        return sock

    if is_linux():
        uid = os.environ.get("SUDO_UID") or os.environ.get("UID")
        if uid:
            for path in (
                f"/run/user/{uid}/keyring/ssh",
                f"/run/user/{uid}/gcr/ssh",
            ):
                if os.path.exists(path):
                    return path

    return None


def discover_identity_files(home: str, configured: Optional[str] = None) -> List[str]:
    if configured:
        path = configured.replace("~", home)
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return [path]
        return []

    ssh_dir = os.path.join(home, ".ssh")
    if not os.path.isdir(ssh_dir):
        return []

    keys: List[str] = []
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        path = os.path.join(ssh_dir, name)
        if os.path.isfile(path):
            keys.append(path)

    for path in sorted(glob.glob(os.path.join(ssh_dir, "id_*"))):
        if path.endswith(".pub") or path.endswith("-cert.pub"):
            continue
        if path not in keys:
            keys.append(path)

    return keys


def build_ssh_env() -> dict:
    env = os.environ.copy()
    user, home = get_invoking_user()
    env["HOME"] = home
    env["USER"] = user
    env["LOGNAME"] = user
    if is_windows():
        env["USERPROFILE"] = home

    sock = resolve_ssh_auth_sock()
    if sock:
        env["SSH_AUTH_SOCK"] = sock

    return env


def wrap_local_ssh(cmd: list) -> list:
    return wrap_ssh_command(cmd)


def run_remote_bash(cmd: list, script: str, env: dict, timeout: int):
    """Pipe a bash script to a remote shell without CRLF corruption.

    On Windows, text-mode stdin translates '\\n' to '\\r\\n', which breaks
    bash on the server. We normalize to LF and send raw bytes, then decode
    stdout/stderr back to str so callers get a normal CompletedProcess.
    """
    import subprocess

    normalized = script.replace("\r\n", "\n").replace("\r", "\n")
    proc = subprocess.run(
        cmd,
        input=normalized.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
    )
    return subprocess.CompletedProcess(
        proc.args,
        proc.returncode,
        stdout=(proc.stdout or b"").decode("utf-8", "replace"),
        stderr=(proc.stderr or b"").decode("utf-8", "replace"),
    )


def parse_ssh_error(stderr: bytes) -> str:
    text = stderr.decode(errors="replace").strip()
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("**")
    ]
    if lines:
        return lines[-1]
    return text or "connection failed"


def permission_denied_hint() -> str:
    _, home = get_invoking_user()
    keys = discover_identity_files(home)
    if is_windows():
        hint = f"SSH auth failed. Keys are loaded from {home}\\.ssh\\"
    elif is_linux() and os.environ.get("SUDO_USER"):
        hint = (
            f"SSH auth failed under sudo. Keys are loaded from {home}/.ssh/ "
            f"(not /root/.ssh/)."
        )
    else:
        hint = f"SSH auth failed. Keys are loaded from {home}/.ssh/"
    if not keys:
        hint += (
            " No private keys found — copy your public key to the server "
            "or set ssh.identity_file in config/user.yml"
        )
    else:
        hint += f" Using: {', '.join(os.path.basename(k) for k in keys)}"
    sock = resolve_ssh_auth_sock()
    if not sock and is_linux():
        hint += (
            ". If you use ssh-agent, try: "
            "sudo SSH_AUTH_SOCK=$SSH_AUTH_SOCK ssh-free user@host"
        )
    return hint
