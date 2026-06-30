#!/usr/bin/env python3
"""DNS configuration for tunneled traffic."""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR
from lib.utils import run_command

DNS_STATE = RUNTIME_DIR / "dns.json"
RESOLV_CONF = Path("/etc/resolv.conf")
RESOLV_BACKUP = RUNTIME_DIR / "resolv.conf.bak"


class DNSManager:

    DEFAULT_SERVERS = ["1.1.1.1", "8.8.8.8"]

    def __init__(self, config: Dict):
        dns_cfg = config.get("dns", {})
        self.enabled = dns_cfg.get("enabled", True)
        self.servers = dns_cfg.get("servers", self.DEFAULT_SERVERS)
        self.mode = dns_cfg.get("mode", "direct")

    def save_state(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        state = {"servers_before": self._read_current_servers()}
        if RESOLV_CONF.exists():
            shutil.copy2(RESOLV_CONF, RESOLV_BACKUP)
        DNS_STATE.write_text(json.dumps(state, indent=2))

    def _read_current_servers(self) -> List[str]:
        servers = []
        if not RESOLV_CONF.exists():
            return servers
        for line in RESOLV_CONF.read_text().splitlines():
            line = line.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    servers.append(parts[1])
        return servers

    def setup(self):
        if not self.enabled:
            log.debug("DNS override disabled")
            return

        self.save_state()

        if self.mode == "direct":
            self._write_resolv(self.servers)
            log.info(f"DNS configured: {', '.join(self.servers)}")
        elif self.mode == "tun":
            # Traffic to DNS goes through TUN via routing
            self._write_resolv(self.servers)
            log.info(f"DNS servers set (via tunnel): {', '.join(self.servers)}")

    def _write_resolv(self, servers: List[str]):
        lines = ["# Managed by ssh-free\n"]
        for srv in servers:
            lines.append(f"nameserver {srv}\n")
        RESOLV_CONF.write_text("".join(lines))

    def restore(self):
        if RESOLV_BACKUP.exists():
            shutil.copy2(RESOLV_BACKUP, RESOLV_CONF)
            RESOLV_BACKUP.unlink(missing_ok=True)
            log.info("DNS configuration restored")
        elif DNS_STATE.exists():
            state = json.loads(DNS_STATE.read_text())
            before = state.get("servers_before", [])
            if before:
                self._write_resolv(before)

        DNS_STATE.unlink(missing_ok=True)

    @staticmethod
    def test_resolution(host: str = "google.com") -> bool:
        code, out, _ = run_command(["getent", "hosts", host], timeout=5)
        if code == 0:
            return True
        code, _, _ = run_command(
            ["python3", "-c", f"import socket; socket.gethostbyname('{host}')"],
            timeout=5,
        )
        return code == 0
