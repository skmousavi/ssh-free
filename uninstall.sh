#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/ssh-free"
BIN_LINKS=(ssh-free ssh-free-stop doctor status tui)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info() { echo -e "${GREEN}[+]${NC} $*"; }

[[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo ./uninstall.sh"; exit 1; }

info "Stopping ssh-free..."
/usr/local/bin/ssh-free-stop 2>/dev/null || true

info "Removing symlinks"
for cmd in "${BIN_LINKS[@]}"; do
    rm -f "/usr/local/bin/${cmd}"
done

info "Removing systemd unit"
rm -f /etc/systemd/system/ssh-free-monitor.service
systemctl daemon-reload 2>/dev/null || true

info "Removing ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"

info "Uninstall complete."
