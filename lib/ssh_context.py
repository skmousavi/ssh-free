#!/usr/bin/env python3
"""SSH environment when ssh-free runs under sudo."""

import glob
import os
import pwd
from typing import List, Optional, Tuple


def get_invoking_user() -> Tuple[str, str]:
    """Return (username, home_dir) for SSH authentication."""
    if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        user = os.environ["SUDO_USER"]
        try:
            home = pwd.getpwnam(user).pw_dir
        except KeyError:
            home = f"/home/{user}"
        return user, home

    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "root"
    home = os.environ.get("HOME") or pwd.getpwnam(user).pw_dir
    return user, home


def resolve_ssh_auth_sock() -> Optional[str]:
    sock = os.environ.get("SSH_AUTH_SOCK")
    if sock and os.path.exists(sock):
        return sock

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

    sock = resolve_ssh_auth_sock()
    if sock:
        env["SSH_AUTH_SOCK"] = sock

    return env


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
    hint = (
        f"SSH auth failed under sudo. Keys are loaded from {home}/.ssh/ "
        f"(not /root/.ssh/)."
    )
    if not keys:
        hint += (
            " No private keys found — run: ssh-copy-id user@host "
            "or set ssh.identity_file in config/user.yml"
        )
    else:
        hint += f" Using: {', '.join(os.path.basename(k) for k in keys)}"
    sock = resolve_ssh_auth_sock()
    if not sock:
        hint += (
            ". If you use ssh-agent, try: "
            "sudo SSH_AUTH_SOCK=$SSH_AUTH_SOCK ssh-free user@host"
        )
    return hint
