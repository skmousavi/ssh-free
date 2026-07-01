#!/usr/bin/env python3
"""SSH reverse tunnel — share local SOCKS proxy with remote server."""

import os
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR, SSH_PID_FILE
from lib.platform import (
    find_pid_by_pattern,
    is_linux,
    kill_processes_matching,
    pid_alive,
    ssh_executable,
    terminate_pid,
)
from lib.remote_lifecycle import (
    discover_free_remote_ports,
    prepare_remote_connect,
    register_remote_session,
    teardown_remote_session,
)
from lib.ssh_context import (
    build_ssh_env,
    discover_identity_files,
    get_invoking_user,
    parse_ssh_error,
    permission_denied_hint,
    wrap_local_ssh,
)
from lib.utils import is_port_open, run_command


class ReverseSSHTunnel:
    """Forward local SOCKS (v2rayN) to remote server via ssh -R."""

    DEFAULT_PORT_COUNT = 100

    def __init__(
        self,
        config: Dict,
        server: Dict,
        local_host: str,
        local_port: int,
        remote_port: Optional[int] = None,
    ):
        self.config = config
        self.server = server
        self.local_host = local_host
        self.local_port = local_port
        ssh_cfg = config.get("ssh", {})
        self.keepalive = ssh_cfg.get("keepalive", 30)
        self.identity_file = ssh_cfg.get("identity_file") or None
        self.extra_args = ssh_cfg.get("extra_args", [])
        _, self.ssh_home = get_invoking_user()
        self.sudo_user = (
            os.environ.get("SUDO_USER")
            if is_linux() and os.environ.get("SUDO_USER")
            else None
        )
        self.identity_files = discover_identity_files(self.ssh_home, self.identity_file)

        rev_cfg = config.get("reverse", {}) or config.get("tunnel", {}).get("reverse", {})
        self.remote_port = int(
            remote_port if remote_port is not None else rev_cfg.get("remote_port", 10809)
        )
        self.remote_bind = rev_cfg.get("remote_bind", "127.0.0.1")
        self._base_remote_port = self.remote_port
        count = int(rev_cfg.get("remote_port_count", self.DEFAULT_PORT_COUNT))
        self._port_count = max(count, 1)
        self._port_end = self._base_remote_port + self._port_count - 1

    def build_command(self, background: bool = True) -> list:
        user = self.server.get("user", "root")
        host = self.server["host"]
        port = self.server.get("port", 22)

        forward = (
            f"{self.remote_bind}:{self.remote_port}:"
            f"{self.local_host}:{self.local_port}"
        )

        cmd = [
            ssh_executable(),
            "-N",
            "-R", forward,
            "-o", "ExitOnForwardFailure=yes",
            "-o", f"ServerAliveInterval={self.keepalive}",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "LogLevel=ERROR",
            "-o", "BatchMode=yes",
        ]

        for key in self.identity_files:
            cmd.extend(["-i", key])

        user_config = os.path.join(self.ssh_home, ".ssh", "config")
        if os.path.isfile(user_config):
            cmd.extend(["-F", user_config])

        for arg in self.extra_args:
            cmd.append(str(arg))

        cmd.extend(["-p", str(port), f"{user}@{host}"])
        return wrap_local_ssh(cmd)

    def _ssh_bin_index(self, cmd: list) -> int:
        for i, part in enumerate(cmd):
            base = os.path.basename(str(part)).lower()
            if base in ("ssh", "ssh.exe"):
                return i
        return 1

    def _ssh_run(self, remote_cmd: str, timeout: int = 25) -> tuple:
        user = self.server.get("user", "root")
        host = self.server["host"]
        port = self.server.get("port", 22)
        cmd = [
            ssh_executable(),
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "LogLevel=ERROR",
            "-p", str(port),
        ]
        for key in self.identity_files:
            cmd.extend(["-i", key])
        cmd.extend([f"{user}@{host}", remote_cmd])
        return run_command(wrap_local_ssh(cmd), timeout=timeout)

    def _remote_port_in_use_script(self, port: int) -> str:
        return (
            f"p={port}; "
            f"ss -ltn 2>/dev/null | grep -qE ':$p[[:space:]]' && exit 0; "
            f"netstat -ltn 2>/dev/null | grep -qE ':$p[[:space:]]' && exit 0; "
            f"timeout 1 bash -c \"echo >/dev/tcp/127.0.0.1/$p\" 2>/dev/null && exit 0; "
            f"exit 1"
        )

    def is_remote_port_in_use(self, port: Optional[int] = None) -> bool:
        port = port if port is not None else self.remote_port
        code, _, _ = self._ssh_run(self._remote_port_in_use_script(port), timeout=8)
        return code == 0

    def discover_free_remote_ports(self, limit: int = 10) -> List[int]:
        """Deprecated — use lib.remote_lifecycle.discover_free_remote_ports."""
        return discover_free_remote_ports(
            self.config, self.server, preferred=self._base_remote_port, limit=limit
        )

    def is_remote_port_listening(self) -> bool:
        return self.is_remote_port_in_use(self.remote_port)

    def start(self, background: bool = True, quiet_retry: bool = False) -> int:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

        if not is_port_open(self.local_host, self.local_port):
            raise RuntimeError(
                f"Local SOCKS not available at {self.local_host}:{self.local_port}. "
                "Start v2rayN or your proxy client first."
            )

        if not self.identity_files:
            raise RuntimeError("No SSH keys found. " + permission_denied_hint())

        cmd = self.build_command(background=background)
        if background:
            idx = self._ssh_bin_index(cmd)
            cmd.insert(idx + 1, "-f")

        if not quiet_retry:
            log.info(
                f"Reverse tunnel: server {self.remote_bind}:{self.remote_port} "
                f"-> local {self.local_host}:{self.local_port}"
            )
        else:
            log.debug(
                f"Retry reverse tunnel on port {self.remote_port}"
            )
        log.debug(f"SSH command: {' '.join(cmd)}")

        err_file = tempfile.NamedTemporaryFile(
            mode="w+b", suffix=".ssh-err", delete=False
        )
        err_path = err_file.name
        err_file.close()

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=open(err_path, "wb"),
            env=build_ssh_env(),
            start_new_session=True,
        )

        time.sleep(1.0)

        for attempt in range(20):
            if process.poll() is not None:
                rc = process.returncode
                err_msg = ""
                try:
                    with open(err_path, "rb") as fh:
                        err_msg = parse_ssh_error(fh.read())
                except OSError:
                    pass
                finally:
                    try:
                        os.unlink(err_path)
                    except OSError:
                        pass
                if rc != 0:
                    raise RuntimeError(
                        "Reverse SSH tunnel failed: "
                        + (err_msg or self._diagnose_tunnel_failure())
                    )
                # ssh -f exits 0 after detaching — verify the forward on server

            if self.is_remote_port_listening():
                try:
                    os.unlink(err_path)
                except OSError:
                    pass
                pid = self._find_ssh_pid()
                if pid:
                    SSH_PID_FILE.write_text(str(pid))
                    log.debug(f"Reverse SSH PID: {pid}")
                else:
                    log.debug("Tunnel port open (ssh pid not tracked)")
                return pid or 0

            if attempt == 4 and not quiet_retry:
                log.info("Waiting for reverse tunnel on server...")
            time.sleep(1.0)

        try:
            os.unlink(err_path)
        except OSError:
            pass

        self.stop()
        raise RuntimeError(
            f"Reverse tunnel port {self.remote_port} not listening on server "
            f"(check AllowTcpForwarding on {self.server['host']})"
        )

    def _diagnose_tunnel_failure(self) -> str:
        code, out, err = self._ssh_run(
            "grep -E '^(AllowTcpForwarding|GatewayPorts)' /etc/ssh/sshd_config 2>/dev/null | tail -3",
            timeout=8,
        )
        hint = ""
        if code == 0 and out.strip():
            hint = f" sshd: {out.strip()}"
        return (
            "ssh exited before forward was ready."
            + hint
            + " Try without sudo: ssh-free user@host"
        )

    def start_with_retry(self) -> int:
        prepare_remote_connect(self.config, self.server)
        self._kill_stale_forwards()

        free_ports = discover_free_remote_ports(
            self.config,
            self.server,
            preferred=self._base_remote_port,
            limit=15,
        )
        if not free_ports:
            raise RuntimeError(
                f"No free port on server in range "
                f"{self._base_remote_port}-{self._port_end}. "
                "Widen reverse.remote_port_count in config."
            )

        log.info(
            f"Using server port {free_ports[0]}"
            + (f" (backups: {free_ports[1:4]}...)" if len(free_ports) > 1 else "")
        )

        last_error = None
        for port in free_ports:
            self.remote_port = port
            try:
                pid = self.start(background=True, quiet_retry=port != free_ports[0])
                register_remote_session(
                    self.config,
                    self.server,
                    self.remote_port,
                    f"{self.local_host}:{self.local_port}",
                )
                return pid
            except RuntimeError as exc:
                last_error = exc
                log.info(f"Port {port} failed, trying next...")
                self.stop()
                time.sleep(0.3)

        raise RuntimeError(
            f"Could not open reverse tunnel (tried {len(free_ports)} ports). "
            f"Last error: {last_error}. "
            "Ensure AllowTcpForwarding yes in server sshd_config."
        )

    def stop(self, release_remote: bool = False):
        if SSH_PID_FILE.exists():
            try:
                pid = int(SSH_PID_FILE.read_text().strip())
                terminate_pid(pid)
            except (ValueError, OSError):
                pass
            SSH_PID_FILE.unlink(missing_ok=True)

        host = self.server["host"]
        kill_processes_matching(f"ssh.*-R.*{host}")

        if release_remote:
            teardown_remote_session(
                self.config, self.server, remote_port=self.remote_port
            )

    def _kill_stale_forwards(self):
        self.stop()
        time.sleep(0.5)

    def _find_ssh_pid(self) -> Optional[int]:
        host = self.server["host"]
        pid = find_pid_by_pattern(f"ssh.*-R.*{host}")
        if pid:
            return pid
        return find_pid_by_pattern(host)

    def get_remote_port(self) -> int:
        return self.remote_port

    def get_proxy_url(self) -> str:
        return f"socks5h://{self.remote_bind}:{self.remote_port}"

    def build_interactive_ssh_cmd(self) -> List[str]:
        user = self.server.get("user", "root")
        host = self.server["host"]
        port = self.server.get("port", 22)
        proxy = self.get_proxy_url()
        port_num = self.remote_port

        cmd = [
            ssh_executable(),
            "-t",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ServerAliveInterval={self.keepalive}",
            "-p", str(port),
        ]
        for key in self.identity_files:
            cmd.extend(["-i", key])
        cmd.append(f"{user}@{host}")
        cmd.extend([
            f"env ALL_PROXY=socks5://127.0.0.1:{port_num} "
            f"HTTP_PROXY={proxy} HTTPS_PROXY={proxy} "
            f"http_proxy={proxy} https_proxy={proxy} bash -l",
        ])
        return cmd
