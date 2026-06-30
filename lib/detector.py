#!/usr/bin/env python3
"""Auto-detection for network, SSH, SOCKS5, and v2rayN."""

import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from lib.logger import log
from lib.utils import (
    command_exists,
    get_default_gateway,
    get_default_interface,
    is_port_open,
    run_command,
    ssh_version,
)


@dataclass
class DetectionResult:
    ok: bool
    message: str
    details: Dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class Detector:

    V2RAY_PORTS = [10808, 1080, 2080, 7890, 10809]
    V2RAY_PROCESSES = ["v2ray", "xray", "v2raya", "sing-box", "clash"]

    def __init__(self, config: Dict):
        self.config = config

    def detect_network(self) -> DetectionResult:
        iface = get_default_interface()
        gateway = get_default_gateway()

        if not iface:
            return DetectionResult(False, "No default network interface found")

        log.debug(f"Default interface: {iface}, gateway: {gateway}")
        return DetectionResult(
            True,
            iface,
            {"interface": iface, "gateway": gateway},
        )

    def detect_ssh(self) -> DetectionResult:
        if not command_exists("ssh"):
            return DetectionResult(False, "OpenSSH client not installed")

        version = ssh_version()
        return DetectionResult(True, version.strip(), {"version": version})

    def detect_socks_candidates(
        self,
        candidates: Optional[List[str]] = None,
    ) -> DetectionResult:
        if candidates is None:
            candidates = self.config.get("socks", {}).get("candidates", [])

        found = []
        for entry in candidates:
            if ":" not in entry:
                continue
            host, port_str = entry.rsplit(":", 1)
            if not port_str.isdigit():
                continue
            port = int(port_str)
            if is_port_open(host, port):
                found.append({"host": host, "port": port, "address": entry})

        if found:
            best = found[0]
            return DetectionResult(
                True,
                best["address"],
                {"endpoints": found, "selected": best},
            )

        return DetectionResult(False, "No SOCKS5 proxy detected", {"endpoints": []})

    def detect_v2rayn(self) -> DetectionResult:
        """Detect v2rayN / common proxy clients on typical local ports."""
        process_found = self._find_proxy_process()
        socks = self._scan_v2ray_ports()

        if socks:
            addr = f"{socks['host']}:{socks['port']}"
            msg = addr
            if process_found:
                msg = f"{addr} ({process_found})"
            return DetectionResult(
                True,
                msg,
                {"endpoint": socks, "process": process_found},
            )

        if process_found:
            return DetectionResult(
                False,
                f"Process {process_found} running but SOCKS port closed",
                {"process": process_found},
            )

        return DetectionResult(False, "v2rayN / proxy client not detected")

    def _scan_v2ray_ports(self) -> Optional[Dict]:
        for port in self.V2RAY_PORTS:
            if is_port_open("127.0.0.1", port):
                return {"host": "127.0.0.1", "port": port}
        return None

    def _find_proxy_process(self) -> Optional[str]:
        code, out, _ = run_command(["ps", "aux"])
        if code != 0:
            return None

        for line in out.splitlines():
            lower = line.lower()
            for name in self.V2RAY_PROCESSES:
                if name in lower and "grep" not in lower:
                    return name
        return None

    def detect_tun2socks(self) -> DetectionResult:
        from lib.utils import find_tun2socks

        path = find_tun2socks(self.config)
        if path:
            return DetectionResult(True, path, {"path": path})

        return DetectionResult(
            False,
            "tun2socks not found (install via install.sh)",
        )

    def detect_tun_support(self) -> DetectionResult:
        code, _, err = run_command(["ip", "tuntap", "add", "mode", "tun", "name", "ssh-free-test"])
        if code == 0:
            run_command(["ip", "tuntap", "del", "mode", "tun", "name", "ssh-free-test"])
            return DetectionResult(True, "TUN/TAP available")

        if "Operation not permitted" in err or code != 0:
            code2, out2, _ = run_command(["ls", "/dev/net/tun"])
            if code2 == 0:
                return DetectionResult(True, "TUN device node present")

        return DetectionResult(False, f"TUN not available: {err}")

    def detect_all(self) -> Dict[str, DetectionResult]:
        return {
            "network": self.detect_network(),
            "ssh": self.detect_ssh(),
            "socks": self.detect_socks_candidates(),
            "v2rayn": self.detect_v2rayn(),
            "tun2socks": self.detect_tun2socks(),
            "tun": self.detect_tun_support(),
        }

    def resolve_socks_endpoint(
        self,
        ssh_socks_port: int,
    ) -> Tuple[str, int, str]:
        """
        Pick SOCKS endpoint: external proxy if configured & up, else SSH tunnel.
        Returns (host, port, source).
        """
        socks_cfg = self.config.get("socks", {})
        auto = socks_cfg.get("auto_detect", True)
        prefer_external = socks_cfg.get("prefer_external", False)

        if auto and prefer_external:
            v2ray = self.detect_v2rayn()
            if v2ray.ok:
                ep = v2ray.details["endpoint"]
                return ep["host"], ep["port"], "v2rayn"

            socks = self.detect_socks_candidates()
            if socks.ok:
                ep = socks.details["selected"]
                return ep["host"], ep["port"], "external"

        fixed = socks_cfg.get("endpoint")
        if fixed and ":" in fixed:
            host, port_str = fixed.rsplit(":", 1)
            if port_str.isdigit():
                return host, int(port_str), "config"

        return "127.0.0.1", ssh_socks_port, "ssh"

    @staticmethod
    def _which(name: str) -> Optional[str]:
        code, out, _ = run_command(["which", name])
        if code == 0 and out:
            return out.strip()
        return None

    def resolve_interface(self) -> str:
        tun_cfg = self.config.get("network", {})
        iface_setting = tun_cfg.get("tun_interface", "auto")

        if iface_setting and iface_setting != "auto":
            return iface_setting

        result = self.detect_network()
        if result.ok:
            return result.message

        raise RuntimeError("Cannot detect default network interface")
