#!/usr/bin/env python3
"""NAT / masquerade for TUN traffic."""

import json
from typing import Dict, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR
from lib.utils import run_command

NAT_STATE = RUNTIME_DIR / "nat.json"


class NATManager:

    CHAIN = "SSH_FREE"

    def __init__(self, config: Dict, tun_name: str, physical_iface: Optional[str] = None):
        self.config = config
        self.tun_name = tun_name
        self.physical_iface = physical_iface
        nat_cfg = config.get("nat", {})
        self.enabled = nat_cfg.get("enabled", True)

    def save_state(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        NAT_STATE.write_text(
            json.dumps(
                {
                    "tun_name": self.tun_name,
                    "physical_iface": self.physical_iface,
                    "enabled": self.enabled,
                },
                indent=2,
            )
        )

    def setup(self):
        if not self.enabled:
            log.debug("NAT disabled")
            return

        self._ensure_chain()
        self._flush_chain()

        # Masquerade traffic leaving physical interface
        if self.physical_iface:
            run_command(
                [
                    "iptables", "-t", "nat", "-A", self.CHAIN,
                    "-o", self.physical_iface, "-j", "MASQUERADE",
                ]
            )

        # Forward between TUN and physical
        run_command(["iptables", "-A", "FORWARD", "-i", self.tun_name, "-j", "ACCEPT"])
        run_command(["iptables", "-A", "FORWARD", "-o", self.tun_name, "-j", "ACCEPT"])

        self.save_state()
        log.info("NAT rules applied")

    def _ensure_chain(self):
        code, _, _ = run_command(
            ["iptables", "-t", "nat", "-N", self.CHAIN]
        )
        if code != 0:
            run_command(["iptables", "-t", "nat", "-F", self.CHAIN])

        code, out, _ = run_command(["iptables", "-t", "nat", "-L", "POSTROUTING", "-n"])
        if self.CHAIN not in out:
            run_command(
                [
                    "iptables", "-t", "nat", "-A", "POSTROUTING",
                    "-j", self.CHAIN,
                ]
            )

    def _flush_chain(self):
        run_command(["iptables", "-t", "nat", "-F", self.CHAIN])

    def restore(self):
        state = None
        if NAT_STATE.exists():
            state = json.loads(NAT_STATE.read_text())

        tun = state.get("tun_name", self.tun_name) if state else self.tun_name

        run_command(["iptables", "-D", "FORWARD", "-i", tun, "-j", "ACCEPT"])
        run_command(["iptables", "-D", "FORWARD", "-o", tun, "-j", "ACCEPT"])

        run_command(["iptables", "-t", "nat", "-F", self.CHAIN])
        run_command(
            ["iptables", "-t", "nat", "-D", "POSTROUTING", "-j", self.CHAIN]
        )
        run_command(["iptables", "-t", "nat", "-X", self.CHAIN])

        NAT_STATE.unlink(missing_ok=True)
        log.info("NAT rules removed")
