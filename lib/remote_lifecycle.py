#!/usr/bin/env python3
"""Server-side prepare/teardown — full rollback on disconnect."""

import subprocess
from typing import Dict, List, Optional, Tuple

from lib.logger import log
from lib.server_proxy import MARKER, _ssh_base_cmd
from lib.ssh_context import build_ssh_env, run_remote_bash

REMOTE_STATE_DIR = "/var/run/ssh-free"
REMOTE_STATE_FILE = f"{REMOTE_STATE_DIR}/session.env"
SSHD_DROPIN = "/etc/ssh/sshd_config.d/99-ssh-free-forwarding.conf"
SSHD_DROPIN_MARKER = "# ssh-free-managed"


def _port_range(config: Dict) -> Tuple[int, int]:
    rev = config.get("reverse", {}) or {}
    start = int(rev.get("remote_port", 10809))
    count = max(int(rev.get("remote_port_count", 100)), 1)
    return start, start + count - 1


def _run_remote_script(
    config: Dict,
    server: Dict,
    script: str,
    timeout: int = 45,
) -> subprocess.CompletedProcess:
    cmd = _ssh_base_cmd(server, config) + ["bash", "-s"]
    return run_remote_bash(cmd, script, build_ssh_env(), timeout)


def teardown_remote_session(
    config: Dict,
    server: Dict,
    remote_port: Optional[int] = None,
    restore_sshd: bool = True,
) -> bool:
    """
    Restore server to pre-ssh-free state: proxy files, yum backup, tunnel port, marker.
    Safe to call even when nothing was configured.
    """
    start, end = _port_range(config)
    port_arg = str(remote_port) if remote_port else ""

    script = f"""set -e
REMOTE_PORT="{port_arg}"
START={start}
END={end}

if [ -f {REMOTE_STATE_FILE} ]; then
  # shellcheck disable=SC1091
  . {REMOTE_STATE_FILE}
fi

rm -f /etc/apt/apt.conf.d/99ssh-free-proxy
rm -f /etc/dnf/dnf.conf.d/ssh-free-proxy.conf
rm -f /etc/profile.d/ssh-free-proxy.sh
rm -f /etc/environment.d/99ssh-free-proxy.conf

if [ -f /etc/yum.conf.ssh-free.bak ]; then
  mv -f /etc/yum.conf.ssh-free.bak /etc/yum.conf
elif [ -f /etc/yum.conf ]; then
  grep -v '{MARKER}' /etc/yum.conf > /tmp/yum.conf.ssh-free || true
  if [ -s /tmp/yum.conf.ssh-free ]; then
    mv -f /tmp/yum.conf.ssh-free /etc/yum.conf
  else
    rm -f /tmp/yum.conf.ssh-free
  fi
fi

close_port() {{
  local p="$1"
  [ -z "$p" ] && return 0
  fuser -k "${{p}}/tcp" 2>/dev/null || true
  if ss -ltnp "sport = :$p" 2>/dev/null | grep -qE 'sshd|ssh'; then
    fuser -k "${{p}}/tcp" 2>/dev/null || true
  fi
}}

if [ -n "$REMOTE_PORT" ]; then
  close_port "$REMOTE_PORT"
fi

for p in $(seq "$START" "$END"); do
  if ss -ltnp "sport = :$p" 2>/dev/null | grep -qE 'users:\\(\\(\"sshd|ssh'; then
    fuser -k "$p/tcp" 2>/dev/null || true
  fi
done

rm -rf {REMOTE_STATE_DIR}

RESTORE_SSHD="{str(restore_sshd).lower()}"
if [ "$RESTORE_SSHD" = "true" ]; then
  DROPIN="{SSHD_DROPIN}"
  MARKER="{SSHD_DROPIN_MARKER}"
  if [ -f "$DROPIN" ] && grep -q "$MARKER" "$DROPIN" 2>/dev/null; then
    rm -f "$DROPIN"
  fi
  if [ -f /etc/ssh/sshd_config.ssh-free.bak ]; then
    mv -f /etc/ssh/sshd_config.ssh-free.bak /etc/ssh/sshd_config
  fi
  sshd -t 2>/dev/null && (systemctl reload sshd 2>/dev/null || service sshd reload 2>/dev/null || true)
fi

echo restored
"""
    result = _run_remote_script(config, server, script, timeout=45)
    if result.returncode == 0:
        log.info("Server restored (proxy removed, port closed)")
        return True

    msg = (result.stderr or result.stdout or "unknown error").strip()
    log.warning(f"Remote teardown: {msg}")
    return False


def prepare_remote_port(config: Dict, server: Dict, port: int) -> bool:
    """Free a specific port on the server (stale ssh -R listeners). Returns True if free."""
    script = f"""p={port}
if ss -ltnp "sport = :$p" 2>/dev/null | grep -qE 'sshd|ssh'; then
  fuser -k "$p/tcp" 2>/dev/null || true
  sleep 0.4
fi
if ss -ltn 2>/dev/null | grep -qE ":$p[[:space:]]"; then exit 1; fi
if netstat -ltn 2>/dev/null | grep -qE ":$p[[:space:]]"; then exit 1; fi
if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/$p" 2>/dev/null; then exit 1; fi
exit 0
"""
    result = _run_remote_script(config, server, script, timeout=15)
    return result.returncode == 0


def ensure_sshd_remote_forwarding(config: Dict, server: Dict) -> bool:
    """
    Ensure sshd allows reverse (-R) tunnels. Creates a drop-in config and reloads sshd.
    Removes the drop-in on teardown.
    """
    script = f"""set -e
DROPIN="{SSHD_DROPIN}"
MARKER="{SSHD_DROPIN_MARKER}"

needs_fix() {{
  local df atf
  df=$(sshd -T 2>/dev/null | awk '$1=="disableforwarding"{{print $2; exit}}')
  atf=$(sshd -T 2>/dev/null | awk '$1=="allowtcpforwarding"{{print $2; exit}}')
  [ "$df" = "yes" ] && return 0
  case "$atf" in
    yes|all|remote) return 1 ;;
    *) return 0 ;;
  esac
}}

if needs_fix; then
  mkdir -p /etc/ssh/sshd_config.d
  if grep -qE '^[[:space:]]*DisableForwarding[[:space:]]' /etc/ssh/sshd_config 2>/dev/null; then
    cp -a /etc/ssh/sshd_config /etc/ssh/sshd_config.ssh-free.bak 2>/dev/null || true
    sed -i 's/^[[:space:]]*DisableForwarding.*/# &  # ssh-free-managed/' /etc/ssh/sshd_config
  fi
  cat > "$DROPIN" << 'EOF'
# ssh-free-managed
DisableForwarding no
AllowTcpForwarding yes
AllowStreamLocalForwarding yes
GatewayPorts no
EOF
  if ! sshd -t 2>/dev/null; then
    rm -f "$DROPIN"
    echo "sshd_config_invalid"
    exit 1
  fi
  if systemctl reload sshd 2>/dev/null; then
    echo "reloaded_systemctl"
  elif service sshd reload 2>/dev/null; then
    echo "reloaded_service"
  else
    systemctl restart sshd 2>/dev/null || service sshd restart
    echo "restarted"
  fi
  sleep 1
  if needs_fix; then
    echo "still_disabled"
    exit 1
  fi
  echo "forwarding_enabled"
else
  echo "forwarding_ok"
fi
"""
    result = _run_remote_script(config, server, script, timeout=45)
    out = (result.stdout or "").strip()
    if result.returncode != 0:
        log.error(
            "Server blocks SSH reverse forwarding (-R). "
            f"Could not auto-enable: {out or result.stderr}"
        )
        return False
    if "forwarding_enabled" in out or "reloaded" in out or "restarted" in out:
        log.info("SSH reverse forwarding enabled on server (sshd reloaded)")
    return True


def remove_sshd_forwarding_dropin(config: Dict, server: Dict) -> None:
    """Remove ssh-free sshd changes (drop-in + main config backup)."""
    script = f"""DROPIN="{SSHD_DROPIN}"
MARKER="{SSHD_DROPIN_MARKER}"
if [ -f "$DROPIN" ] && grep -q "$MARKER" "$DROPIN" 2>/dev/null; then
  rm -f "$DROPIN"
fi
if [ -f /etc/ssh/sshd_config.ssh-free.bak ]; then
  mv -f /etc/ssh/sshd_config.ssh-free.bak /etc/ssh/sshd_config
fi
sshd -t 2>/dev/null && (systemctl reload sshd 2>/dev/null || service sshd reload 2>/dev/null || true)
"""
    _run_remote_script(config, server, script, timeout=20)


def prepare_remote_connect(config: Dict, server: Dict) -> None:
    """Clean leftovers, enable sshd forwarding, free preferred port."""
    teardown_remote_session(config, server, restore_sshd=False)
    if not ensure_sshd_remote_forwarding(config, server):
        raise RuntimeError(
            "Server sshd blocks reverse port forwarding (-R). "
            "As root on server, set AllowTcpForwarding yes in /etc/ssh/sshd_config "
            "and run: systemctl reload sshd"
        )
    preferred, _ = _port_range(config)
    if prepare_remote_port(config, server, preferred):
        log.info(f"Server port {preferred} ready")
    else:
        log.info(f"Port {preferred} busy — will pick next free port")


def register_remote_session(
    config: Dict,
    server: Dict,
    remote_port: int,
    local_socks: str,
) -> None:
    """Record active session on server for reliable teardown later."""
    host = server.get("host", "")
    script = f"""mkdir -p {REMOTE_STATE_DIR}
cat > {REMOTE_STATE_FILE} << 'EOF'
REMOTE_PORT={remote_port}
LOCAL_SOCKS={local_socks}
SERVER_HOST={host}
SSH_FREE=1
EOF
chmod 600 {REMOTE_STATE_FILE}
echo registered
"""
    result = _run_remote_script(config, server, script, timeout=15)
    if result.returncode != 0:
        log.warning("Could not write server session marker (teardown may need local session)")


def discover_free_remote_ports(
    config: Dict,
    server: Dict,
    preferred: Optional[int] = None,
    limit: int = 15,
) -> List[int]:
    """Return free ports; preferred port first when available."""
    start, end = _port_range(config)
    pref = preferred if preferred is not None else start
    script = f"""start={start}
end={end}
pref={pref}
limit={limit}
found=0

port_free() {{
  local p="$1"
  ss -ltn 2>/dev/null | grep -qE ":$p[[:space:]]" && return 1
  netstat -ltn 2>/dev/null | grep -qE ":$p[[:space:]]" && return 1
  timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/$p" 2>/dev/null && return 1
  return 0
}}

if port_free "$pref"; then echo "$pref"; found=1; fi

for p in $(seq "$start" "$end"); do
  [ "$p" -eq "$pref" ] && continue
  port_free "$p" || continue
  echo "$p"
  found=$((found + 1))
  [ "$found" -ge "$limit" ] && break
done
"""
    result = _run_remote_script(config, server, script, timeout=30)
    ports: List[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            ports.append(int(line))
    return ports
