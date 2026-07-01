#!/usr/bin/env python3
"""Full teardown and state cleanup."""

import json
import os
from typing import Optional

from lib.logger import log
from lib.platform import kill_processes_matching, pid_alive, terminate_pid
from lib.dns import DNSManager
from lib.nat import NATManager
from lib.paths import (
    LOCK_FILE,
    MONITOR_PID_FILE,
    RUNTIME_DIR,
    SESSION_FILE,
    SSH_PID_FILE,
    STATUS_FILE,
    TUN2SOCKS_PID_FILE,
    TRAFFIC_FILE,
)
from lib.routing import Router
from lib.tun import TUNInterface


class Cleanup:

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def stop_monitor(self):
        if not MONITOR_PID_FILE.exists():
            return

        try:
            pid = int(MONITOR_PID_FILE.read_text().strip())
            terminate_pid(pid)
        except (ValueError, OSError):
            pass
        MONITOR_PID_FILE.unlink(missing_ok=True)

    def stop_processes(self):
        session = self._load_session()
        server_host = None
        if session and session.get("server"):
            server_host = session["server"].get("host")

        for pid_file in (TUN2SOCKS_PID_FILE, SSH_PID_FILE):
            if not pid_file.exists():
                continue
            try:
                pid = int(pid_file.read_text().strip())
                terminate_pid(pid)
            except (ValueError, OSError):
                pass
            pid_file.unlink(missing_ok=True)

        kill_processes_matching("tun2socks.*ssh-free")
        kill_processes_matching("ssh.*-D.*127.0.0.1")
        if server_host:
            kill_processes_matching(f"ssh.*-R.*{server_host}")
        else:
            kill_processes_matching("ssh.*-R.*127.0.0.1")

    def restore_network(self):
        session = self._load_session()
        if session and session.get("tunnel_mode") == "server-proxy":
            server = session.get("server")
            remote_port = session.get("remote_port")
            if server:
                try:
                    from lib.server_proxy import cleanup_remote_proxy
                    cleanup_remote_proxy(
                        self.config, server, remote_port=remote_port
                    )
                except Exception as e:
                    log.warning(f"Remote cleanup: {e}")
            log.debug("Server-proxy mode — skipping local network restore")
            return

        # No local session — still try server rollback via remote marker / config
        try:
            from lib.config import resolve_server
            from lib.server_proxy import cleanup_remote_proxy

            server = resolve_server(self.config, None)
            if server.get("host"):
                cleanup_remote_proxy(self.config, server)
        except Exception:
            pass

        tun_name = "ssh-free0"
        physical = None

        if session:
            tun_name = session.get("tun_name", tun_name)
            physical = session.get("physical_iface")

        try:
            Router(self.config, tun_name, "").restore()
        except Exception as e:
            log.warning(f"Routing restore: {e}")

        try:
            DNSManager(self.config).restore()
        except Exception as e:
            log.warning(f"DNS restore: {e}")

        try:
            NATManager(self.config, tun_name, physical).restore()
        except Exception as e:
            log.warning(f"NAT restore: {e}")

        try:
            TUNInterface(self.config).down()
        except Exception as e:
            log.warning(f"TUN teardown: {e}")

    def remove_state(self):
        for path in (LOCK_FILE, SESSION_FILE, STATUS_FILE, TRAFFIC_FILE):
            path.unlink(missing_ok=True)
        traffic_state = RUNTIME_DIR / "traffic_state.json"
        traffic_state.unlink(missing_ok=True)
        rules_cache = RUNTIME_DIR / "rules_cache.json"
        rules_cache.unlink(missing_ok=True)

    def run(self, full: bool = True):
        log.info("Cleaning up ssh-free...")
        self.stop_monitor()
        self.stop_processes()

        if full:
            self.restore_network()

        self.remove_state()
        log.info("Cleanup complete")

    def _load_session(self) -> Optional[dict]:
        if not SESSION_FILE.exists():
            return None
        try:
            return json.loads(SESSION_FILE.read_text())
        except json.JSONDecodeError:
            return None
