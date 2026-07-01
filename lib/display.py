#!/usr/bin/env python3
"""Terminal UI helpers."""

import json
import socket
import time
from typing import Dict, List, Optional, Tuple

from lib.utils import internet_available, run_command

# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"


def banner(version: str = "1.0"):
    width = 44
    line = "─" * width
    print(f"{DIM}{line}{RESET}")
    print(f"{BOLD} SSH-FREE v{version}{RESET}")
    print(f"{DIM}{line}{RESET}")
    print()


def step_ok(label: str, detail: str = ""):
    suffix = f" {DIM}({detail}){RESET}" if detail else ""
    print(f"{GREEN}✓{RESET} {label}{suffix}")


def step_fail(label: str, detail: str = ""):
    suffix = f" {RED}{detail}{RESET}" if detail else ""
    print(f"{RED}✗{RESET} {label}{suffix}")


def step_skip(label: str, detail: str = ""):
    suffix = f" {DIM}{detail}{RESET}" if detail else ""
    print(f"{YELLOW}○{RESET} {label}{suffix}")


def connected_summary(
    server: Dict,
    public_ip: Optional[str] = None,
    latency_ms: Optional[float] = None,
    socks_source: str = "ssh",
):
    print()
    print(f"{BOLD}{GREEN}CONNECTED{RESET}")
    print()
    print(f"{DIM}Server:{RESET}")
    host = server.get("host", "?")
    user = server.get("user", "root")
    print(f"  {user}@{host}")
    print()
    print(f"{DIM}Tunnel:{RESET}")
    print(f"  {GREEN}ACTIVE{RESET}")
    print()
    if public_ip:
        print(f"{DIM}Public IP:{RESET}")
        print(f"  {public_ip}")
        print()
    if latency_ms is not None:
        print(f"{DIM}Latency:{RESET}")
        print(f"  {latency_ms:.0f} ms")
        print()
    if socks_source != "ssh":
        print(f"{DIM}SOCKS:{RESET}")
        print(f"  {socks_source}")
        print()


def server_proxy_summary(
    server: Dict,
    local_socks: str,
    remote_proxy_url: str,
    remote_public_ip: Optional[str] = None,
    usage: str = "",
):
    print()
    print(f"{BOLD}{GREEN}READY — SERVER USES YOUR INTERNET{RESET}")
    print()
    print(f"{DIM}Server:{RESET}  {server.get('user', 'root')}@{server.get('host', '?')}")
    print(f"{DIM}Your proxy:{RESET}  {local_socks}")
    if remote_public_ip:
        print(f"{DIM}Server outbound IP:{RESET}  {remote_public_ip}")
    print()
    if usage:
        print(f"{DIM}Usage on server:{RESET}")
        print(usage)
        print()


def disconnected_banner():
    print()
    print(f"{YELLOW}DISCONNECTED{RESET}")
    print()


def clear_screen():
    print("\033[2J\033[H", end="")


def measure_latency(host: str = "1.1.1.1", count: int = 3) -> Optional[float]:
    import sys

    if sys.platform == "win32":
        code, out, _ = run_command(
            ["ping", "-n", str(count), "-w", "2000", host],
            timeout=15,
        )
    else:
        code, out, _ = run_command(
            ["ping", "-c", str(count), "-W", "2", host],
            timeout=15,
        )
    if code != 0:
        return None

    for line in out.splitlines():
        lower = line.lower()
        if "average" in lower and "ms" in lower:
            for token in line.replace("=", " ").replace(",", " ").split():
                if token.lower().endswith("ms"):
                    try:
                        return float(token.lower().replace("ms", ""))
                    except ValueError:
                        pass
        if "avg" in lower or "rtt" in lower:
            parts = line.split("=")
            if len(parts) >= 2:
                values = parts[1].strip().split("/")
                if len(values) >= 2:
                    try:
                        return float(values[1])
                    except ValueError:
                        pass
    return None


def fetch_public_ip(timeout: int = 10) -> Optional[str]:
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]

    for url in services:
        code, out, _ = run_command(
            ["curl", "-s", "--max-time", str(timeout), url],
            timeout=timeout + 2,
        )
        if code == 0 and out.strip():
            return out.strip().splitlines()[0]

    return None


def run_doctor_report(results: Dict):
    banner("3.0")
    print(f"{BOLD}System Diagnostics{RESET}")
    print()

    labels = {
        "network": "Network interface",
        "ssh": "OpenSSH client",
        "tun": "TUN support",
        "tun2socks": "tun2socks binary",
        "socks": "SOCKS5 proxy",
        "v2rayn": "v2rayN / proxy",
        "root": "Root privileges",
        "internet": "Internet connectivity",
        "routing": "Local routing backend",
    }

    for key, label in labels.items():
        result = results.get(key)
        if result is None:
            continue
        if isinstance(result, dict):
            ok = result.get("ok", False)
            msg = result.get("message", "")
        else:
            ok = result.ok
            msg = result.message

        if ok:
            step_ok(label, msg)
        else:
            step_fail(label, msg)

    print()


def status_display(status: Dict):
    banner("3.0")
    healthy = status.get("healthy", False)
    state = f"{GREEN}HEALTHY{RESET}" if healthy else f"{RED}UNHEALTHY{RESET}"
    print(f"Status: {state}")
    print()

    server = status.get("server") or {}
    if server:
        print(f"Server:  {server.get('user', 'root')}@{server.get('host', '?')}")

    profile = status.get("profile")
    if profile:
        print(f"Profile: {profile}")

    mode = status.get("routing_mode")
    if mode:
        print(f"Routing: {mode}")

    print(f"SSH:       {'up' if status.get('ssh_alive') else 'down'}")
    print(f"TUN:       {'up' if status.get('tun_alive') else 'down'}")
    print(f"tun2socks: {'up' if status.get('tun2socks_alive') else 'down'}")
    print(f"Internet:  {'yes' if status.get('internet') else 'no'}")
    print()

    traffic = status.get("traffic")
    if traffic:
        traffic_display(traffic)

    updated = status.get("updated_at")
    if updated:
        print(f"{DIM}Updated: {updated}{RESET}")
    print()


def traffic_display(traffic: Dict):
    tun = traffic.get("tun", {})
    rates = traffic.get("rates", {})
    print(f"{BOLD}Traffic ({tun.get('name', 'tun')}){RESET}")
    print(f"  ↓ {GREEN}{tun.get('rx_human', '0 B')}{RESET}  ({rates.get('rx_human', '0 B/s')})")
    print(f"  ↑ {CYAN}{tun.get('tx_human', '0 B')}{RESET}  ({rates.get('tx_human', '0 B/s')})")
    print()
