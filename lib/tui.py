#!/usr/bin/env python3
"""Interactive terminal UI for ssh-free."""

import os
import subprocess
import sys
from typing import Callable, Dict, List, Optional

from lib.config import load_config, save_user_config
from lib.display import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    banner,
    connected_summary,
    fetch_public_ip,
    measure_latency,
    run_doctor_report,
    status_display,
)
from lib.lock import SessionLock
from lib.monitor import Monitor
from lib.paths import ROOT, STATUS_FILE, USER_CONFIG
from lib.profiles import (
    add_profile,
    apply_profile_overrides,
    get_profile,
    list_profiles,
    profile_target,
    resolve_server_by_profile,
    set_default_profile,
)
from lib.rules import expand_rules, load_rules_config
from lib.session import load_session
from lib.traffic import TrafficStats
from lib.utils import is_root, read_yaml


def clear_screen():
    print("\033[2J\033[H", end="")


def pause():
    input(f"\n{DIM}Press Enter to continue...{RESET}")


def menu_header(title: str):
    clear_screen()
    banner("3.0")
    print(f"{BOLD}{CYAN}{title}{RESET}\n")


def run_cmd(args: List[str], need_root: bool = True) -> int:
    if need_root and not is_root():
        print(f"{RED}Root required. Re-run with sudo.{RESET}")
        pause()
        return 1

    env = os.environ.copy()
    env["SSH_FREE_ROOT"] = str(ROOT)
    result = subprocess.run(
        [sys.executable] + args,
        env=env,
    )
    return result.returncode


def show_traffic_panel(session: Dict):
    stats = TrafficStats.from_session(session).snapshot_with_rates()
    tun = stats["tun"]
    rates = stats.get("rates", {})

    print(f"{BOLD}Traffic ({tun['name']}){RESET}")
    print(f"  Download: {GREEN}{tun['rx_human']}{RESET}  ({rates.get('rx_human', '0 B/s')})")
    print(f"  Upload:   {CYAN}{tun['tx_human']}{RESET}  ({rates.get('tx_human', '0 B/s')})")
    print()


class TUI:

    def __init__(self):
        self.config = load_config()

    def main_menu(self):
        while True:
            menu_header("Main Menu")
            locked = SessionLock().is_locked()
            state = f"{GREEN}CONNECTED{RESET}" if locked else f"{YELLOW}DISCONNECTED{RESET}"
            print(f"  Session: {state}\n")

            options = [
                ("1", "Connect", self.action_connect),
                ("2", "Disconnect", self.action_disconnect),
                ("3", "Status & Traffic", self.action_status),
                ("4", "Profiles", self.action_profiles),
                ("5", "Routing Rules", self.action_routing),
                ("6", "Doctor", self.action_doctor),
                ("7", "Exit", None),
            ]

            for key, label, _ in options:
                print(f"  {CYAN}[{key}]{RESET} {label}")

            print()
            choice = input(f"{BOLD}>{RESET} ").strip()

            if choice == "7":
                clear_screen()
                print("Goodbye.")
                break

            action = next((fn for k, _, fn in options if k == choice and fn), None)
            if action:
                action()
            else:
                print(f"{RED}Invalid choice{RESET}")
                pause()

    def action_connect(self):
        menu_header("Connect")
        profiles = list_profiles(self.config)

        if profiles:
            print(f"{BOLD}Profiles:{RESET}")
            for i, p in enumerate(profiles, 1):
                mark = f" {GREEN}*{RESET}" if p.get("default") else ""
                print(
                    f"  {CYAN}[{i}]{RESET} {p.get('name')} — "
                    f"{p.get('user', 'root')}@{p.get('host')}{mark}"
                )
            print(f"  {CYAN}[c]{RESET} Custom target (user@host)")
            print()
            choice = input("Select profile or [c]ustom: ").strip()

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(profiles):
                    profile = profiles[idx]
                    target = profile_target(profile)
                    run_cmd([str(ROOT / "bin" / "ssh-free"), target, "--profile", profile["name"]])
                    pause()
                    return

            if choice.lower() != "c":
                pause()
                return

        target = input("SSH target (user@host): ").strip()
        if not target:
            pause()
            return

        run_cmd([str(ROOT / "bin" / "ssh-free"), target])
        pause()

    def action_disconnect(self):
        run_cmd([str(ROOT / "bin" / "ssh-free-stop")])
        pause()

    def action_status(self):
        menu_header("Status & Traffic")

        session = load_session()
        if not session and not SessionLock().is_locked():
            print(f"{YELLOW}No active session.{RESET}")
            pause()
            return

        if STATUS_FILE.exists():
            import json
            status = json.loads(STATUS_FILE.read_text())
            status_display(status)

        if session:
            show_traffic_panel(session)
            server = session.get("server", {})
            connected_summary(
                server=server,
                public_ip=fetch_public_ip(),
                latency_ms=measure_latency(),
                socks_source=session.get("socks_source", "ssh"),
            )

        watch = input("Live watch? [y/N]: ").strip().lower()
        if watch in ("y", "yes"):
            self._watch_loop(session)

        pause()

    def _watch_loop(self, session: Dict):
        try:
            while True:
                clear_screen()
                menu_header("Live Traffic")
                show_traffic_panel(session)

                if STATUS_FILE.exists():
                    import json
                    status = json.loads(STATUS_FILE.read_text())
                    healthy = status.get("healthy", False)
                    state = f"{GREEN}HEALTHY{RESET}" if healthy else f"{RED}UNHEALTHY{RESET}"
                    print(f"Health: {state}")
                    print(f"SSH: {'up' if status.get('ssh_alive') else 'down'}  "
                          f"TUN: {'up' if status.get('tun_alive') else 'down'}  "
                          f"tun2socks: {'up' if status.get('tun2socks_alive') else 'down'}")

                print(f"\n{DIM}Refreshing every 2s — Ctrl+C to stop{RESET}")
                import time
                time.sleep(2)
        except KeyboardInterrupt:
            pass

    def action_profiles(self):
        while True:
            menu_header("Profiles")
            profiles = list_profiles(self.config)

            for p in profiles:
                mark = f" {GREEN}(default){RESET}" if p.get("default") else ""
                print(
                    f"  • {BOLD}{p.get('name')}{RESET}{mark}: "
                    f"{p.get('user', 'root')}@{p.get('host')}:{p.get('port', 22)}"
                )

            print()
            print(f"  {CYAN}[s]{RESET} Set default   {CYAN}[a]{RESET} Add   "
                  f"{CYAN}[c]{RESET} Connect   {CYAN}[b]{RESET} Back")
            print()
            choice = input(f"{BOLD}>{RESET} ").strip().lower()

            if choice == "b":
                break
            elif choice == "s":
                name = input("Profile name: ").strip()
                try:
                    set_default_profile(name)
                    self.config = load_config()
                    print(f"{GREEN}Default profile set to {name}{RESET}")
                except ValueError as e:
                    print(f"{RED}{e}{RESET}")
                pause()
            elif choice == "a":
                self._add_profile_wizard()
            elif choice == "c":
                name = input("Profile name to connect: ").strip()
                try:
                    server = resolve_server_by_profile(self.config, name)
                    target = profile_target(server)
                    run_cmd([str(ROOT / "bin" / "ssh-free"), target, "--profile", name])
                except ValueError as e:
                    print(f"{RED}{e}{RESET}")
                pause()

    def _add_profile_wizard(self):
        name = input("Profile name: ").strip()
        host = input("Host/IP: ").strip()
        user = input("User [root]: ").strip() or "root"
        port = input("Port [22]: ").strip() or "22"

        mode = input("Routing mode [full/split/rules]: ").strip() or "full"
        profile = {
            "name": name,
            "host": host,
            "user": user,
            "port": int(port) if port.isdigit() else 22,
        }

        if mode in ("split", "rules"):
            rules_str = input("Include rules (comma-separated CIDR/domains): ").strip()
            rules = [r.strip() for r in rules_str.split(",") if r.strip()]
            profile["routing"] = {"mode": mode, "include": rules}

        add_profile(profile)
        self.config = load_config()
        print(f"{GREEN}Profile '{name}' added.{RESET}")
        pause()

    def action_routing(self):
        menu_header("Routing Rules")
        rules_cfg = load_rules_config(self.config)

        print(f"  Mode:   {BOLD}{rules_cfg['mode']}{RESET}")
        print(f"  Include: {', '.join(rules_cfg['include']) or '(none)'}")
        print(f"  Exclude: {', '.join(rules_cfg['exclude']) or '(none)'}")
        print()

        if rules_cfg["include"]:
            targets, domain_map = expand_rules(rules_cfg["include"])
            print(f"  Resolved {len(targets)} target(s):")
            for t in targets[:10]:
                print(f"    • {t}")
            if len(targets) > 10:
                print(f"    ... and {len(targets) - 10} more")
            print()

        print(f"{DIM}Edit config/user.yml to change routing rules.{RESET}")
        pause()

    def action_doctor(self):
        menu_header("Doctor")
        run_cmd([str(ROOT / "bin" / "doctor")], need_root=False)
        pause()


def main():
    if not sys.stdin.isatty():
        print("TUI requires an interactive terminal.")
        sys.exit(1)

    TUI().main_menu()


if __name__ == "__main__":
    main()
