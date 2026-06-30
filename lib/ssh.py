#!/usr/bin/env python3
"""SSH dynamic tunnel (SOCKS5) management."""

import os
import signal
import subprocess
import sys
import time
from typing import Dict, List, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR, SSH_PID_FILE
from lib.ssh_context import (
    build_ssh_env,
    discover_identity_files,
    get_invoking_user,
    parse_ssh_error,
    permission_denied_hint,
)
from lib.utils import is_port_open, run_command


class SSHTunnel:

    def __init__(self, config: Dict, server: Dict):
        self.config = config
        self.server = server
        ssh_cfg = config.get("ssh", {})
        self.keepalive = ssh_cfg.get("keepalive", 30)
        self.socks_port = ssh_cfg.get("local_port", 0) or self._pick_port()
        self.identity_file = ssh_cfg.get("identity_file") or None
        self.extra_args = ssh_cfg.get("extra_args", [])
        self.allow_password = ssh_cfg.get("allow_password", True)
        _, self.ssh_home = get_invoking_user()
        self.identity_files = discover_identity_files(self.ssh_home, self.identity_file)

    def _pick_port(self) -> int:
        for port in range(10801, 10900):
            if not is_port_open("127.0.0.1", port):
                return port
        raise RuntimeError("No free local port for SSH SOCKS tunnel")

    def build_command(self, background: bool = True) -> list:
        user = self.server.get("user", "root")
        host = self.server["host"]
        port = self.server.get("port", 22)

        cmd = [
            "ssh",
            "-N",
            "-D", f"127.0.0.1:{self.socks_port}",
            "-o", "ExitOnForwardFailure=yes",
            "-o", f"ServerAliveInterval={self.keepalive}",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "LogLevel=ERROR",
        ]

        if background and not (self.allow_password and sys.stdin.isatty()):
            cmd.extend(["-o", "BatchMode=yes"])
        else:
            cmd.extend(["-o", "BatchMode=no"])

        for key in self.identity_files:
            cmd.extend(["-i", key])

        user_config = os.path.join(self.ssh_home, ".ssh", "config")
        if os.path.isfile(user_config):
            cmd.extend(["-F", user_config])

        for arg in self.extra_args:
            cmd.append(str(arg))

        cmd.extend(["-p", str(port), f"{user}@{host}"])
        return cmd

    def start(self, background: bool = True) -> int:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

        if not self.identity_files and background and not sys.stdin.isatty():
            raise RuntimeError(
                "No SSH keys found and no TTY for password auth. "
                + permission_denied_hint()
            )

        cmd = self.build_command(background=background)
        if background:
            cmd.insert(1, "-f")

        log.info(
            f"Starting SSH tunnel to {self.server['user']}@{self.server['host']} "
            f"(SOCKS 127.0.0.1:{self.socks_port})"
        )
        if self.identity_files:
            log.debug(
                "SSH keys: "
                + ", ".join(os.path.basename(k) for k in self.identity_files)
            )
        log.debug(f"SSH command: {' '.join(cmd)}")

        env = build_ssh_env()
        interactive = sys.stdin.isatty() and self.allow_password

        process = subprocess.Popen(
            cmd,
            stdin=None,
            stdout=subprocess.DEVNULL,
            stderr=None if interactive else subprocess.PIPE,
            env=env,
        )

        if background:
            for _ in range(60 if interactive else 30):
                if is_port_open("127.0.0.1", self.socks_port):
                    pid = self._find_ssh_pid()
                    if pid:
                        SSH_PID_FILE.write_text(str(pid))
                        log.debug(f"SSH tunnel PID: {pid}")
                        return pid
                time.sleep(0.5)

            if interactive:
                raise RuntimeError(
                    "SSH tunnel failed: authentication timed out or was denied. "
                    + permission_denied_hint()
                )

            _, err = process.communicate(timeout=5)
            message = parse_ssh_error(err or b"")
            if "Permission denied" in message or "publickey" in message:
                message = f"{message}\n  {permission_denied_hint()}"
            raise RuntimeError(f"SSH tunnel failed: {message}")

        SSH_PID_FILE.write_text(str(process.pid))
        return process.pid

    def _find_ssh_pid(self) -> Optional[int]:
        code, out, _ = run_command(
            ["pgrep", "-f", f"127.0.0.1:{self.socks_port}"]
        )
        if code == 0 and out:
            return int(out.splitlines()[0])
        return None

    def stop(self):
        if SSH_PID_FILE.exists():
            try:
                pid = int(SSH_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except (ProcessLookupError, ValueError):
                pass
            SSH_PID_FILE.unlink(missing_ok=True)

        port = self.socks_port
        code, out, _ = run_command(["pgrep", "-f", f"127.0.0.1:{port}"])
        if code == 0:
            for line in out.splitlines():
                try:
                    os.kill(int(line), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def is_alive(self) -> bool:
        if not SSH_PID_FILE.exists():
            return is_port_open("127.0.0.1", self.socks_port)

        try:
            pid = int(SSH_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return is_port_open("127.0.0.1", self.socks_port)
        except (ProcessLookupError, ValueError):
            return False

    def get_socks_port(self) -> int:
        return self.socks_port
