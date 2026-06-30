#!/usr/bin/env python3
"""tun2socks process management."""

import os
import signal
import subprocess
import time
from typing import Dict, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR, TUN2SOCKS_PID_FILE
from lib.utils import command_exists, run_command, which


class Tun2Socks:

    LOG_FILE = RUNTIME_DIR / "tun2socks.log"

    def __init__(
        self,
        config: Dict,
        tun_name: str,
        socks_host: str,
        socks_port: int,
    ):
        self.config = config
        self.tun_name = tun_name
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.process = None
        self.binary = self._find_binary()

    def _find_binary(self) -> str:
        from lib.utils import find_tun2socks

        path = find_tun2socks(self.config)
        if path:
            return path

        raise RuntimeError(
            "tun2socks binary not found. Run install.sh or set tun2socks.binary in config."
        )

    def build_command(self) -> list:
        proxy = f"socks5://{self.socks_host}:{self.socks_port}"
        mtu = self.config.get("network", {}).get("mtu", 1500)

        tun_cfg = self.config.get("tun2socks", {})
        loglevel = tun_cfg.get("loglevel", "warning")
        # tun2socks v2.x accepts: debug|info|warning|error|silent
        if loglevel == "warn":
            loglevel = "warning"

        cmd = [
            self.binary,
            "-device", f"tun://{self.tun_name}",
            "-proxy", proxy,
            "-mtu", str(mtu),
            "-loglevel", loglevel,
        ]
        return cmd

    def start(self) -> int:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command()

        log.info(
            f"Starting tun2socks ({self.tun_name} -> {self.socks_host}:{self.socks_port})"
        )
        log.debug(f"tun2socks command: {' '.join(cmd)}")

        log_fd = open(self.LOG_FILE, "a")
        self.process = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )
        log_fd.close()

        time.sleep(1)

        if self.process.poll() is not None:
            log_tail = self._read_log_tail()
            raise RuntimeError(
                f"tun2socks exited immediately (see {self.LOG_FILE})"
                + (f": {log_tail}" if log_tail else "")
            )

        TUN2SOCKS_PID_FILE.write_text(str(self.process.pid))
        log.debug(f"tun2socks PID: {self.process.pid}")
        return self.process.pid

    def stop(self):
        if TUN2SOCKS_PID_FILE.exists():
            try:
                pid = int(TUN2SOCKS_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except (ProcessLookupError, ValueError):
                pass
            TUN2SOCKS_PID_FILE.unlink(missing_ok=True)

        if self.process and self.process.poll() is None:
            self.process.terminate()

    def is_alive(self) -> bool:
        if TUN2SOCKS_PID_FILE.exists():
            try:
                pid = int(TUN2SOCKS_PID_FILE.read_text().strip())
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, ValueError):
                return False
        return self.process is not None and self.process.poll() is None

    def _read_log_tail(self, lines: int = 3) -> str:
        if not self.LOG_FILE.exists():
            return ""
        try:
            content = self.LOG_FILE.read_text().strip().splitlines()
            return content[-1] if content else ""
        except OSError:
            return ""
