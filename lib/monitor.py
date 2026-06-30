#!/usr/bin/env python3
"""Health monitoring and auto-recovery."""

import json
import os
import signal
import sys
import time
from typing import Dict, Optional

from lib.logger import log
from lib.paths import MONITOR_PID_FILE, ROOT, RUNTIME_DIR, SESSION_FILE, STATUS_FILE
from lib.utils import internet_available, is_port_open, now, run_command
from lib.traffic import TrafficStats


class Monitor:

    CHECK_INTERVAL = 10
    MAX_FAILURES = 3

    def __init__(self, config: Dict):
        self.config = config
        monitor_cfg = config.get("monitor", {})
        self.enabled = monitor_cfg.get("enabled", True)
        self.interval = monitor_cfg.get("interval", self.CHECK_INTERVAL)
        self.auto_recover = config.get("ssh", {}).get("reconnect", True)
        self.failures = 0

    def load_session(self) -> Optional[Dict]:
        if not SESSION_FILE.exists():
            return None
        try:
            return json.loads(SESSION_FILE.read_text())
        except json.JSONDecodeError:
            return None

    def save_status(self, status: Dict):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        status["updated_at"] = now()
        STATUS_FILE.write_text(json.dumps(status, indent=2))

    def check_health(self, session: Dict) -> Dict:
        socks_port = session.get("socks_port", 0)
        ssh_alive = self._pid_alive(session.get("ssh_pid"))
        mode = session.get("tunnel_mode", "client-tun")

        if mode == "server-proxy":
            return {
                "healthy": ssh_alive,
                "ssh_alive": ssh_alive,
                "tun_alive": True,
                "tun2socks_alive": True,
                "socks_open": True,
                "internet": internet_available(),
                "failures": self.failures,
                "tunnel_mode": mode,
            }

        tun_alive = self._interface_up(session.get("tun_name", "ssh-free0"))
        tun2socks_alive = self._pid_alive(session.get("tun2socks_pid"))
        socks_open = is_port_open("127.0.0.1", socks_port) if socks_port else False
        internet = internet_available()

        healthy = ssh_alive and tun_alive and tun2socks_alive and socks_open

        return {
            "healthy": healthy,
            "ssh_alive": ssh_alive,
            "tun_alive": tun_alive,
            "tun2socks_alive": tun2socks_alive,
            "socks_open": socks_open,
            "internet": internet,
            "failures": self.failures,
        }

    def recover(self, session: Dict):
        if not self.auto_recover:
            log.warning("Auto-recover disabled")
            return

        log.warning("Attempting auto-recovery...")

        # Re-run ssh-free with stored server target
        server = session.get("server", {})
        target = f"{server.get('user', 'root')}@{server.get('host')}"
        mode_flag = []
        if session.get("tunnel_mode") == "client-tun":
            mode_flag = ["--client-tun"]

        code, out, err = run_command(
            [
                sys.executable,
                str(ROOT / "bin" / "ssh-free"),
                target,
                "--recover",
            ] + mode_flag,
            timeout=120,
        )

        if code == 0:
            log.info("Auto-recovery succeeded")
            self.failures = 0
        else:
            log.error(f"Auto-recovery failed: {err or out}")

    def run_loop(self):
        log.info(f"Monitor started (interval={self.interval}s)")

        while True:
            session = self.load_session()
            if not session:
                log.info("No active session, monitor exiting")
                break

            health = self.check_health(session)
            traffic = TrafficStats.from_session(session).snapshot_with_rates()
            TrafficStats.from_session(session).save_public(traffic)

            self.save_status(
                {
                    **health,
                    "server": session.get("server"),
                    "profile": session.get("profile"),
                    "routing_mode": session.get("routing_mode"),
                    "traffic": traffic,
                    "session": {
                        "tun_name": session.get("tun_name"),
                        "socks_port": session.get("socks_port"),
                    },
                }
            )

            if health["healthy"]:
                self.failures = 0
            else:
                self.failures += 1
                log.warning(
                    f"Health check failed ({self.failures}/{self.MAX_FAILURES}): "
                    f"ssh={health['ssh_alive']} tun={health['tun_alive']} "
                    f"tun2socks={health['tun2socks_alive']}"
                )

                if self.failures >= self.MAX_FAILURES:
                    self.recover(session)

            time.sleep(self.interval)

    @staticmethod
    def _pid_alive(pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (ProcessLookupError, ValueError):
            return False

    @staticmethod
    def _interface_up(name: str) -> bool:
        code, out, _ = run_command(["ip", "link", "show", name])
        return code == 0 and "UP" in out

    def start_daemon(self):
        if MONITOR_PID_FILE.exists():
            try:
                pid = int(MONITOR_PID_FILE.read_text().strip())
                os.kill(pid, 0)
                log.debug("Monitor already running")
                return pid
            except (ProcessLookupError, ValueError):
                MONITOR_PID_FILE.unlink(missing_ok=True)

        pid = os.fork()
        if pid > 0:
            MONITOR_PID_FILE.write_text(str(pid))
            return pid

        os.setsid()
        sys.stdin = open(os.devnull)
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

        try:
            self.run_loop()
        except KeyboardInterrupt:
            pass
        finally:
            MONITOR_PID_FILE.unlink(missing_ok=True)

        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    args = parser.parse_args()

    ROOT = os.environ.get("SSH_FREE_ROOT")
    if ROOT and ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from lib.config import load_config

    monitor = Monitor(load_config())
    if args.daemon:
        monitor.run_loop()
    else:
        monitor.start_daemon()
