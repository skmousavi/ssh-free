#!/usr/bin/env python3
"""Network traffic statistics."""

import json
import time
from typing import Dict, Optional, Tuple

from lib.paths import RUNTIME_DIR, TRAFFIC_FILE
from lib.utils import human_size, now, run_command

TRAFFIC_STATE = RUNTIME_DIR / "traffic_state.json"


class TrafficStats:

    def __init__(self, tun_name: str = "ssh-free0", physical_iface: Optional[str] = None):
        self.tun_name = tun_name
        self.physical_iface = physical_iface

    def read_iface_bytes(self, iface: str) -> Tuple[int, int]:
        rx_path = f"/sys/class/net/{iface}/statistics/rx_bytes"
        tx_path = f"/sys/class/net/{iface}/statistics/tx_bytes"

        try:
            with open(rx_path) as f:
                rx = int(f.read().strip())
            with open(tx_path) as f:
                tx = int(f.read().strip())
            return rx, tx
        except (OSError, ValueError):
            return self._read_proc_net_dev(iface)

    def _read_proc_net_dev(self, iface: str) -> Tuple[int, int]:
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if iface + ":" in line:
                        parts = line.split(":")[1].split()
                        return int(parts[0]), int(parts[8])
        except OSError:
            pass
        return 0, 0

    def snapshot(self) -> Dict:
        tun_rx, tun_tx = self.read_iface_bytes(self.tun_name)

        phys_rx, phys_tx = 0, 0
        if self.physical_iface:
            phys_rx, phys_tx = self.read_iface_bytes(self.physical_iface)

        return {
            "tun": {
                "name": self.tun_name,
                "rx_bytes": tun_rx,
                "tx_bytes": tun_tx,
                "rx_human": human_size(tun_rx),
                "tx_human": human_size(tun_tx),
            },
            "physical": {
                "name": self.physical_iface or "",
                "rx_bytes": phys_rx,
                "tx_bytes": phys_tx,
                "rx_human": human_size(phys_rx),
                "tx_human": human_size(phys_tx),
            },
            "timestamp": time.time(),
            "updated_at": now(),
        }

    def snapshot_with_rates(self) -> Dict:
        current = self.snapshot()
        prev = self._load_prev()

        rates = {"tun_rx_rate": 0, "tun_tx_rate": 0}
        if prev:
            dt = current["timestamp"] - prev.get("timestamp", 0)
            if dt > 0:
                rates["tun_rx_rate"] = (
                    current["tun"]["rx_bytes"] - prev.get("tun", {}).get("rx_bytes", 0)
                ) / dt
                rates["tun_tx_rate"] = (
                    current["tun"]["tx_bytes"] - prev.get("tun", {}).get("tx_bytes", 0)
                ) / dt

        current["rates"] = {
            "rx_per_sec": rates["tun_rx_rate"],
            "tx_per_sec": rates["tun_tx_rate"],
            "rx_human": human_size(rates["tun_rx_rate"]) + "/s",
            "tx_human": human_size(rates["tun_tx_rate"]) + "/s",
        }

        self._save_prev(current)
        return current

    def _load_prev(self) -> Optional[Dict]:
        if not TRAFFIC_STATE.exists():
            return None
        try:
            return json.loads(TRAFFIC_STATE.read_text())
        except json.JSONDecodeError:
            return None

    def _save_prev(self, data: Dict):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        TRAFFIC_STATE.write_text(json.dumps(data, indent=2))

    def save_public(self, data: Dict):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        TRAFFIC_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def load_public(cls) -> Optional[Dict]:
        if not TRAFFIC_FILE.exists():
            return None
        try:
            return json.loads(TRAFFIC_FILE.read_text())
        except json.JSONDecodeError:
            return None

    @classmethod
    def from_session(cls, session: Dict) -> "TrafficStats":
        return cls(
            tun_name=session.get("tun_name", "ssh-free0"),
            physical_iface=session.get("physical_iface"),
        )
