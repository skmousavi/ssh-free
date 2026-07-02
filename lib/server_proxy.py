#!/usr/bin/env python3
"""Automatic server-side proxy setup (no manual steps)."""

import subprocess
from typing import Dict, List, Optional

from lib.logger import log
from lib.ssh_context import build_ssh_env, discover_identity_files, get_invoking_user
from lib.utils import run_command

MARKER = "# ssh-free-proxy"

REMOTE_FILES = [
    "/etc/apt/apt.conf.d/99ssh-free-proxy",
    "/etc/dnf/dnf.conf.d/ssh-free-proxy.conf",
    "/etc/yum.conf.ssh-free.bak",
    "/etc/profile.d/ssh-free-proxy.sh",
    "/etc/environment.d/99ssh-free-proxy.conf",
]


def _ssh_base_cmd(server: Dict, config: Dict) -> list:
    from lib.platform import ssh_executable
    from lib.ssh_context import discover_identity_files, get_invoking_user, wrap_local_ssh

    user = server.get("user", "root")
    host = server["host"]
    port = server.get("port", 22)
    _, home = get_invoking_user()
    identity_files = discover_identity_files(
        home, config.get("ssh", {}).get("identity_file")
    )

    cmd = [
        ssh_executable(),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "LogLevel=ERROR",
        "-p", str(port),
    ]
    for key in identity_files:
        cmd.extend(["-i", key])
    cmd.append(f"{user}@{host}")
    return wrap_local_ssh(cmd)


def setup_remote_proxy_system(
    config: Dict,
    server: Dict,
    proxy_url: str,
) -> List[str]:
    """Configure yum/dnf/apt and shell on the server automatically."""
    if not config.get("reverse", {}).get("auto_setup", True):
        return []

    remote_port = proxy_url.rsplit(":", 1)[-1]
    proxy = f"socks5h://127.0.0.1:{remote_port}"
    socks = f"socks5://127.0.0.1:{remote_port}"

    script = f"""set -e
PORT={remote_port}
PROXY="{proxy}"
SOCKS="{socks}"

mkdir -p /etc/environment.d /etc/dnf/dnf.conf.d /etc/apt/apt.conf.d

# Debian/Ubuntu apt
cat > /etc/apt/apt.conf.d/99ssh-free-proxy << EOF
Acquire::http::Proxy "$PROXY";
Acquire::https::Proxy "$PROXY";
EOF

# RHEL/CentOS/Fedora dnf & yum (must be socks5h, NOT http://)
cat > /etc/dnf/dnf.conf.d/ssh-free-proxy.conf << EOF
[main]
proxy=$PROXY
EOF

if [ -f /etc/yum.conf ]; then
  cp -a /etc/yum.conf /etc/yum.conf.ssh-free.bak 2>/dev/null || true
  grep -v '{MARKER}' /etc/yum.conf > /tmp/yum.conf.new || true
  mv /tmp/yum.conf.new /etc/yum.conf
  echo "proxy=$PROXY  {MARKER}" >> /etc/yum.conf
fi

# All interactive shells
cat > /etc/profile.d/ssh-free-proxy.sh << EOF
# ssh-free managed
export ALL_PROXY="$SOCKS"
export HTTP_PROXY="$PROXY"
export HTTPS_PROXY="$PROXY"
export http_proxy="$PROXY"
export https_proxy="$PROXY"
EOF
chmod 644 /etc/profile.d/ssh-free-proxy.sh

# systemd user services / some tools
cat > /etc/environment.d/99ssh-free-proxy.conf << EOF
ALL_PROXY=$SOCKS
HTTP_PROXY=$PROXY
HTTPS_PROXY=$PROXY
http_proxy=$PROXY
https_proxy=$PROXY
EOF

echo OK
"""

    from lib.remote_exec import run_privileged

    result = run_privileged(server, config, script, 60)

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to configure server proxy automatically: "
            + (result.stderr.strip() or result.stdout.strip())
        )

    log.info("Server configured: yum/dnf/apt + shell (automatic)")
    return list(REMOTE_FILES)


def cleanup_remote_proxy(
    config: Dict,
    server: Dict,
    remote_port: Optional[int] = None,
):
    """Remove ssh-free changes from server (full rollback)."""
    from lib.remote_lifecycle import teardown_remote_session

    teardown_remote_session(config, server, remote_port=remote_port)


def test_remote_download(server: Dict, config: Dict, proxy_url: str) -> Optional[str]:
    """Verify server can reach internet through shared proxy."""
    proxy = proxy_url
    remote_cmd = f"""
PROXY="{proxy}"
if command -v curl >/dev/null 2>&1; then
  curl -sf --max-time 20 --proxy "$PROXY" https://api.ipify.org && exit 0
  curl -sf --max-time 20 --proxy "$PROXY" https://icanhazip.com && exit 0
fi
if command -v wget >/dev/null 2>&1; then
  wget -q -e use_proxy=yes -e http_proxy="$PROXY" -O - --timeout=20 https://api.ipify.org && exit 0
fi
echo "NO_CURL_WGET"
exit 1
"""
    cmd = _ssh_base_cmd(server, config) + ["bash", "-c", remote_cmd]
    code, out, err = run_command(cmd, timeout=30)
    if code == 0 and out.strip() and "NO_CURL" not in out:
        return out.strip().splitlines()[0]

    if "NO_CURL" in out:
        log.warning("curl/wget not on server — skipping download test (yum should still work)")
        return None

    raise RuntimeError(
        "Server cannot reach internet via your proxy. "
        "Keep v2rayN running on laptop and retry."
    )


def open_interactive_shell(tunnel) -> int:
    cmd = tunnel.build_interactive_ssh_cmd()
    log.info("Opening server shell (yum/apt use your proxy automatically)")
    return subprocess.run(cmd, env=build_ssh_env()).returncode
