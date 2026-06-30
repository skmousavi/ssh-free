#!/usr/bin/env python3
"""TUN interface management."""

from typing import Dict, Optional

from lib.logger import log
from lib.utils import run_command


class TUNInterface:

    DEFAULT_NAME = "ssh-free0"
    DEFAULT_ADDR = "198.18.0.1"
    DEFAULT_PREFIX = 15

    def __init__(self, config: Dict):
        net = config.get("network", {})
        self.name = net.get("tun_name", self.DEFAULT_NAME)
        self.addr = net.get("tun_address", self.DEFAULT_ADDR)
        self.prefix = net.get("tun_prefix", self.DEFAULT_PREFIX)
        self.mtu = net.get("mtu", 1500)

    def exists(self) -> bool:
        code, _, _ = run_command(["ip", "link", "show", self.name])
        return code == 0

    def create(self):
        if self.exists():
            log.debug(f"TUN {self.name} already exists")
            return

        code, _, err = run_command(
            ["ip", "tuntap", "add", "dev", self.name, "mode", "tun"]
        )
        if code != 0:
            raise RuntimeError(f"Failed to create TUN {self.name}: {err}")

        log.info(f"Created TUN interface {self.name}")

    def configure(self):
        cidr = f"{self.addr}/{self.prefix}"

        run_command(["ip", "addr", "flush", "dev", self.name])
        code, _, err = run_command(
            ["ip", "addr", "add", cidr, "dev", self.name]
        )
        if code != 0:
            raise RuntimeError(f"Failed to set TUN address: {err}")

        run_command(["ip", "link", "set", self.name, "mtu", str(self.mtu)])
        code, _, err = run_command(["ip", "link", "set", self.name, "up"])
        if code != 0:
            raise RuntimeError(f"Failed to bring up TUN: {err}")

        log.info(f"TUN {self.name} configured ({cidr}, MTU {self.mtu})")

    def up(self):
        self.create()
        self.configure()

    def down(self):
        if not self.exists():
            return

        run_command(["ip", "link", "set", self.name, "down"])
        code, _, err = run_command(["ip", "tuntap", "del", "dev", self.name, "mode", "tun"])
        if code != 0:
            log.warning(f"Failed to remove TUN: {err}")
        else:
            log.info(f"Removed TUN interface {self.name}")

    def get_name(self) -> str:
        return self.name

    def get_network_cidr(self) -> str:
        return f"{self.addr}/{self.prefix}"
