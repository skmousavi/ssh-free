#!/usr/bin/env python3
"""Policy routing and route table management."""

import json
from typing import Dict, List, Optional

from lib.logger import log
from lib.paths import RUNTIME_DIR
from lib.routing_detect import (
    detect_routing_backend,
    ensure_rt_tables_entry,
    resolve_effective_mode,
)
from lib.rules import (
    expand_rules,
    is_cidr,
    is_ip,
    load_rules_config,
    save_rules_cache,
)
from lib.utils import get_default_gateway, get_default_interface, run_command

ROUTING_STATE = RUNTIME_DIR / "routing.json"


class Router:

    TABLE_ID = 100
    TABLE_NAME = "sshfree"
    RULE_PRIORITY = 100

    def __init__(self, config: Dict, tun_name: str, server_host: str):
        self.config = config
        self.tun_name = tun_name
        self.server_host = server_host
        self.physical_iface = get_default_interface()
        self.original_gateway = get_default_gateway()
        rules_cfg = load_rules_config(config)
        self.requested_mode = rules_cfg["mode"]
        self.backend = detect_routing_backend()
        self.mode = resolve_effective_mode(self.requested_mode, self.backend)
        self.include_rules = rules_cfg["include"]
        self.exclude_rules = rules_cfg["exclude"]
        self.split_rules = rules_cfg["split"]
        self.applied_priorities: List[str] = []
        self.use_policy = self.mode in ("split", "rules")

    def save_state(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "physical_iface": self.physical_iface,
            "original_gateway": self.original_gateway,
            "tun_name": self.tun_name,
            "server_host": self.server_host,
            "mode": self.mode,
            "requested_mode": self.requested_mode,
            "backend": self.backend.get("backend"),
            "use_policy": self.use_policy,
            "applied_priorities": self.applied_priorities,
            "include": self.include_rules,
            "exclude": self.exclude_rules,
        }
        ROUTING_STATE.write_text(json.dumps(state, indent=2))

    @classmethod
    def load_state(cls) -> Optional[Dict]:
        if not ROUTING_STATE.exists():
            return None
        return json.loads(ROUTING_STATE.read_text())

    def _ensure_route_table(self):
        if not self.use_policy:
            return

        if ensure_rt_tables_entry(self.TABLE_ID, self.TABLE_NAME):
            log.debug(f"Routing table {self.TABLE_ID} ({self.TABLE_NAME}) ready")
        else:
            log.debug(
                f"Using numeric routing table {self.TABLE_ID} "
                "(rt_tables file not available)"
            )

    def setup(self):
        if not self.physical_iface:
            raise RuntimeError("No physical interface for routing")

        if not self.backend["ip_available"]:
            raise RuntimeError("iproute2 (ip command) is required for routing")

        if self.mode != self.requested_mode:
            log.warning(
                f"Routing mode '{self.requested_mode}' not supported locally "
                f"({self.backend['backend']}, policy={self.backend['policy_routing']}) "
                f"— using '{self.mode}'"
            )

        log.info(
            f"Routing backend: {self.backend['backend']} "
            f"(mode={self.mode}, policy={self.use_policy})"
        )

        self._ensure_route_table()
        self.save_state()

        if self.server_host and self._is_ip_or_resolvable(self.server_host):
            self._bypass_host(self.server_host)

        exclude_targets, _ = expand_rules(self.exclude_rules)
        for target in exclude_targets:
            self._bypass_target(target)

        if self.mode == "full":
            self._setup_full_tunnel()
        elif self.mode == "rules":
            self._setup_rules_tunnel()
        else:
            self._setup_split_tunnel()

        log.info(f"Routing configured (mode={self.mode})")

    def _setup_full_tunnel(self):
        code, _, err = run_command(
            ["ip", "route", "replace", "default", "dev", self.tun_name]
        )
        if code != 0:
            raise RuntimeError(f"Failed to set default route via TUN: {err}")

    def _setup_split_tunnel(self):
        rules = self.split_rules or self.include_rules or ["0.0.0.0/0"]
        targets, _ = expand_rules(rules)

        for target in targets:
            self._route_via_tunnel(target)

    def _setup_rules_tunnel(self):
        if not self.include_rules:
            log.warning("Rules mode with empty include list — no tunnel routes added")
            return

        targets, domain_map = expand_rules(self.include_rules)
        save_rules_cache(domain_map)

        if not targets:
            raise RuntimeError("No valid routing rules resolved")

        run_command(
            [
                "ip", "route", "replace", "default",
                "dev", self.tun_name,
                "table", str(self.TABLE_ID),
            ]
        )

        for target in targets:
            self._route_via_tunnel(target)

        log.info(f"Applied {len(targets)} rule-based routes")

    def _route_via_tunnel(self, target: str):
        if is_cidr(target):
            dest = target
        elif is_ip(target):
            dest = f"{target}/32"
        else:
            return

        if self.use_policy:
            run_command(
                [
                    "ip", "route", "replace", dest,
                    "dev", self.tun_name,
                    "table", str(self.TABLE_ID),
                ]
            )
            priority = str(self._next_priority(target))
            run_command(
                [
                    "ip", "rule", "add",
                    "to", dest,
                    "table", str(self.TABLE_ID),
                    "priority", priority,
                ]
            )
            self.applied_priorities.append(priority)
        else:
            run_command(
                [
                    "ip", "route", "replace", dest,
                    "dev", self.tun_name,
                ]
            )

    def _next_priority(self, target: str) -> int:
        return 1000 + (hash(target) % 8000)

    def _bypass_host(self, host: str):
        for ip in self._resolve_host(host):
            self._bypass_target(ip)

    def _bypass_target(self, target: str):
        if is_cidr(target):
            for ip in self._resolve_cidr_hosts(target):
                self._add_bypass_route(ip)
            return

        resolved = self._resolve_host(target) if not is_ip(target) else [target]
        for ip in resolved:
            self._add_bypass_route(ip)

    def _add_bypass_route(self, ip: str):
        if self.original_gateway:
            run_command(
                [
                    "ip", "route", "replace", ip,
                    "via", self.original_gateway,
                    "dev", self.physical_iface,
                ]
            )
        else:
            run_command(
                [
                    "ip", "route", "replace", ip,
                    "dev", self.physical_iface,
                ]
            )
        log.debug(f"Bypass route for {ip} via {self.physical_iface}")

    def _resolve_cidr_hosts(self, cidr: str) -> List[str]:
        return [cidr.split("/")[0]] if is_cidr(cidr) else []

    def _resolve_host(self, host: str) -> List[str]:
        import socket
        try:
            results = socket.getaddrinfo(host, None, socket.AF_INET)
            return list({r[4][0] for r in results})
        except socket.gaierror:
            return [host] if self._looks_like_ip(host) else []

    @staticmethod
    def _looks_like_ip(value: str) -> bool:
        parts = value.split(".")
        return len(parts) == 4 and all(p.isdigit() for p in parts)

    def _is_ip_or_resolvable(self, host: str) -> bool:
        return bool(self._resolve_host(host) or self._looks_like_ip(host))

    def restore(self):
        state = self.load_state()
        if not state:
            self._fallback_restore()
            return

        use_policy = state.get("use_policy", state.get("mode") in ("split", "rules"))
        table_id = str(self.TABLE_ID)

        if use_policy:
            priorities = state.get("applied_priorities", [])
            if not priorities:
                code, out, _ = run_command(["ip", "rule", "show"])
                for line in out.splitlines():
                    if f"lookup {self.TABLE_NAME}" in line or f"lookup {table_id}" in line:
                        parts = line.split(":")[0].strip()
                        if parts.isdigit():
                            priorities.append(parts)

            for priority in priorities:
                run_command(["ip", "rule", "del", "priority", str(priority)])

            code, out, _ = run_command(["ip", "rule", "show"])
            for line in out.splitlines():
                if f"lookup {self.TABLE_NAME}" in line or f"lookup {table_id}" in line:
                    parts = line.split(":")[0].strip()
                    if parts.isdigit():
                        run_command(["ip", "rule", "del", "priority", parts])

        iface = state.get("physical_iface")
        gw = state.get("original_gateway")
        tun = state.get("tun_name", "ssh-free0")

        run_command(["ip", "route", "del", "default", "dev", tun])
        run_command(["ip", "route", "del", "default", "dev", tun, "table", table_id])

        if gw and iface:
            run_command(["ip", "route", "replace", "default", "via", gw, "dev", iface])
        elif iface:
            run_command(["ip", "route", "replace", "default", "dev", iface])

        server = state.get("server_host")
        if server:
            for ip in self._resolve_host(server):
                run_command(["ip", "route", "del", ip])

        for target in state.get("include", []):
            for ip in self._resolve_host(target) if not is_ip(target) and not is_cidr(target) else [target]:
                run_command(["ip", "route", "del", ip])

        ROUTING_STATE.unlink(missing_ok=True)
        log.info("Routing restored")

    def _fallback_restore(self):
        run_command(["ip", "route", "del", "default", "dev", self.tun_name])
        iface = get_default_interface()
        gw = get_default_gateway()
        if gw and iface:
            run_command(["ip", "route", "replace", "default", "via", gw, "dev", iface])
