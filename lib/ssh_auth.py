#!/usr/bin/env python3
"""
Cross-platform SSH auth bootstrap.

ssh-free runs many non-interactive SSH commands (teardown, sshd fix, port
scan, the reverse tunnel itself). Those use BatchMode=yes, which disables
password prompts. If the user only has password auth, every one of those
fails.

To support password-based servers on both Linux and Windows (Windows OpenSSH
has no ControlMaster multiplexing), we set up key auth automatically:

  1. If key auth already works -> done, nothing to do.
  2. Otherwise, ensure a local keypair exists (generate ed25519 if missing).
  3. Push the public key to the server's authorized_keys via ONE interactive,
     password-authenticated SSH session (user types password once).
  4. Verify key auth now works.

After this, all automated commands and the persistent tunnel use the key
silently.
"""

import os
import shutil
import socket
import subprocess
from typing import Dict, List, Optional

from lib.logger import log
from lib.platform import ssh_executable
from lib.ssh_context import (
    build_ssh_env,
    discover_identity_files,
    get_invoking_user,
    wrap_local_ssh,
)


def _keygen_executable() -> str:
    exe = ssh_executable()
    if exe.lower().endswith("ssh.exe"):
        candidate = exe[:-7] + "ssh-keygen.exe"
        if os.path.isfile(candidate):
            return candidate
    if os.path.sep in exe or "/" in exe:
        base = os.path.dirname(exe)
        candidate = os.path.join(base, "ssh-keygen")
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("ssh-keygen")
    return found or "ssh-keygen"


def _server_parts(server: Dict) -> tuple:
    return (
        server.get("user", "root"),
        server["host"],
        int(server.get("port", 22)),
    )


def _base_ssh(server: Dict, identity_files: List[str], batch: bool) -> list:
    user, host, port = _server_parts(server)
    cmd = [
        ssh_executable(),
        "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "LogLevel=ERROR",
    ]
    if batch:
        cmd += ["-o", "BatchMode=yes"]
    for key in identity_files:
        cmd += ["-i", key]
    cmd += ["-p", str(port), f"{user}@{host}"]
    return wrap_local_ssh(cmd)


def key_auth_works(server: Dict, config: Dict) -> bool:
    _, home = get_invoking_user()
    identity_files = discover_identity_files(
        home, config.get("ssh", {}).get("identity_file")
    )
    cmd = _base_ssh(server, identity_files, batch=True) + ["true"]
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=build_ssh_env(),
            timeout=25,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _ensure_local_keypair(config: Dict) -> Optional[str]:
    """Return path to a private key, generating an ed25519 key if none exists."""
    _, home = get_invoking_user()
    configured = config.get("ssh", {}).get("identity_file")
    if configured:
        path = os.path.expanduser(configured.replace("~", home))
        if os.path.isfile(path):
            return path

    existing = discover_identity_files(home, None)
    if existing:
        return existing[0]

    ssh_dir = os.path.join(home, ".ssh")
    try:
        os.makedirs(ssh_dir, exist_ok=True)
        try:
            os.chmod(ssh_dir, 0o700)
        except OSError:
            pass
    except OSError as exc:
        log.error(f"Cannot create {ssh_dir}: {exc}")
        return None

    key_path = os.path.join(ssh_dir, "id_ed25519")
    comment = f"ssh-free@{socket.gethostname()}"
    cmd = [
        _keygen_executable(),
        "-t", "ed25519",
        "-N", "",
        "-f", key_path,
        "-C", comment,
    ]
    log.info("Generating SSH key (id_ed25519) for passwordless login")
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=build_ssh_env(),
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error(f"ssh-keygen failed: {exc}")
        return None

    if result.returncode != 0 or not os.path.isfile(key_path):
        log.error(f"ssh-keygen failed: {(result.stderr or result.stdout).strip()}")
        return None
    return key_path


def _read_public_key(private_key: str) -> Optional[str]:
    pub_path = private_key + ".pub"
    if not os.path.isfile(pub_path):
        return None
    try:
        with open(pub_path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        return content or None
    except OSError:
        return None


def _push_public_key(server: Dict, private_key: str, quiet: bool) -> bool:
    """Interactive: append pubkey to server authorized_keys (one password prompt)."""
    pubkey = _read_public_key(private_key)
    if not pubkey:
        log.error(f"Public key not found for {private_key}")
        return False

    # Escape single quotes for safe embedding in a single-quoted shell string.
    safe_key = pubkey.replace("'", "'\\''")
    remote = (
        "umask 077; "
        "mkdir -p ~/.ssh; "
        "touch ~/.ssh/authorized_keys; "
        f"grep -qxF '{safe_key}' ~/.ssh/authorized_keys 2>/dev/null || "
        f"echo '{safe_key}' >> ~/.ssh/authorized_keys; "
        "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
        "echo ssh-free-key-installed"
    )

    user, host, port = _server_parts(server)
    cmd = [
        ssh_executable(),
        "-o", "ConnectTimeout=25",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "PubkeyAuthentication=no",
        "-p", str(port),
        f"{user}@{host}",
        remote,
    ]
    cmd = wrap_local_ssh(cmd)

    if not quiet:
        print()
        print(f"  Enter the SSH password for {user}@{host} once to set up")
        print("  passwordless login (used only to install your key):")
        print()

    try:
        result = subprocess.run(cmd, env=build_ssh_env(), timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error(f"Could not install key on server: {exc}")
        return False
    return result.returncode == 0


def ensure_key_auth(server: Dict, config: Dict, quiet: bool = False) -> bool:
    """
    Guarantee key-based SSH auth to the server.

    Returns True if key auth works (already or after installing the key).
    If it can't be established, returns False; the caller should surface a
    clear message.
    """
    if config.get("ssh", {}).get("password_auth_disabled"):
        # User forced key-only; just report whether it works.
        return key_auth_works(server, config)

    if key_auth_works(server, config):
        return True

    if not quiet:
        log.info("Key auth not available yet — setting up passwordless login")

    private_key = _ensure_local_keypair(config)
    if not private_key:
        return False

    if not _push_public_key(server, private_key, quiet):
        log.error(
            "Failed to install SSH key on server. "
            "Check the password and that the server allows password login."
        )
        return False

    if key_auth_works(server, config):
        if not quiet:
            log.info("Passwordless login configured")
        return True

    log.error(
        "Installed the key but key auth still fails. "
        "The server may reject key auth (PubkeyAuthentication no) — "
        "enable it in /etc/ssh/sshd_config."
    )
    return False
