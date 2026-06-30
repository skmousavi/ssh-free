#!/usr/bin/env bash
set -euo pipefail

# ssh-free installer
# Usage: sudo ./install.sh

VERSION="3.0.0"
INSTALL_DIR="/opt/ssh-free"
BIN_LINKS=(ssh-free ssh-free-stop doctor status tui)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || error "Run as root: sudo ./install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info "Installing ssh-free v${VERSION}"

# command_or_pkg: "binary:apt-package" (binary omitted if same as package)
DEPS=(
    python3
    python3-yaml
    iproute2
    iptables
    openssh-client
    curl
    ping:iputils-ping
    unzip
)

pkg_installed() {
    local pkg="$1"
    dpkg -s "$pkg" &>/dev/null
}

cmd_exists() {
    command -v "$1" &>/dev/null
}

resolve_pkg() {
    local entry="$1"
    if [[ "$entry" == *:* ]]; then
        echo "${entry#*:}"
    else
        echo "$entry"
    fi
}

resolve_cmd() {
    local entry="$1"
    if [[ "$entry" == *:* ]]; then
        echo "${entry%%:*}"
    else
        echo "$entry"
    fi
}

install_apt_packages() {
    local missing=()
    local entry pkg cmd

    for entry in "${DEPS[@]}"; do
        pkg="$(resolve_pkg "$entry")"
        cmd="$(resolve_cmd "$entry")"
        if pkg_installed "$pkg" || cmd_exists "$cmd"; then
            continue
        fi
        missing+=("$pkg")
    done

    [[ ${#missing[@]} -eq 0 ]] && return 0

    info "Installing packages: ${missing[*]}"

    # Try without apt-get update first (avoids failing on broken third-party repos)
    if apt-get install -y --no-install-recommends "${missing[@]}" 2>/dev/null; then
        return 0
    fi

    warn "Direct install failed — running apt-get update (may warn on broken repos)..."
    apt-get update -qq 2>/dev/null \
        || warn "apt-get update failed (e.g. broken HashiCorp repo) — retrying install anyway"

    if apt-get install -y --no-install-recommends "${missing[@]}" 2>/dev/null; then
        return 0
    fi

    warn "Could not install via apt: ${missing[*]}"
    for pkg in "${missing[@]}"; do
        if ! pkg_installed "$pkg"; then
            warn "  missing: $pkg — install manually if needed"
        fi
    done
}

install_apt_packages

# iproute2 config dir (optional; full tunnel mode works without rt_tables)
if [[ ! -f /etc/iproute2/rt_tables ]] && command -v apt-get &>/dev/null; then
    apt-get install -y --no-install-recommends iproute2 2>/dev/null || true
fi

verify_python_deps() {
    if python3 -c "import yaml" 2>/dev/null; then
        info "Python dependency OK (yaml)"
        return 0
    fi

    warn "PyYAML not found — installing python3-yaml via apt..."
    apt-get install -y --no-install-recommends python3-yaml 2>/dev/null \
        || apt-get install -y --no-install-recommends python3-yaml

    if python3 -c "import yaml" 2>/dev/null; then
        info "Python dependency OK (yaml)"
        return 0
    fi

    error "PyYAML required. Install with: sudo apt install python3-yaml"
}

verify_python_deps

# Install files
info "Copying files to ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
if command -v rsync &>/dev/null; then
    rsync -a --exclude='.git' --exclude='__pycache__' \
        "${SCRIPT_DIR}/" "${INSTALL_DIR}/"
else
    cp -a "${SCRIPT_DIR}/." "${INSTALL_DIR}/"
    rm -rf "${INSTALL_DIR}/.git" "${INSTALL_DIR}/"__pycache__ 2>/dev/null || true
fi

mkdir -p "${INSTALL_DIR}/logs" "${INSTALL_DIR}/runtime"

# tun2socks
T2S="${INSTALL_DIR}/bin/tun2socks"
if [[ ! -x "${T2S}" ]]; then
    ARCH="$(uname -m)"
    case "${ARCH}" in
        x86_64)  T2S_ARCH="amd64" ;;
        aarch64) T2S_ARCH="arm64" ;;
        *)       warn "Unknown arch ${ARCH}, skipping tun2socks download" ; T2S_ARCH="" ;;
    esac

    if [[ -n "${T2S_ARCH}" ]]; then
        URL="https://github.com/xjasonlyu/tun2socks/releases/download/v2.5.2/tun2socks-linux-${T2S_ARCH}.zip"
        info "Downloading tun2socks (${T2S_ARCH})..."
        TMP="$(mktemp -d)"
        curl -fsSL "${URL}" -o "${TMP}/tun2socks.zip"
        unzip -qo "${TMP}/tun2socks.zip" -d "${TMP}"
        mv "${TMP}/tun2socks-linux-${T2S_ARCH}" "${T2S}"
        chmod +x "${T2S}"
        rm -rf "${TMP}"
        info "tun2socks installed at ${T2S}"
    fi
fi

# Expose tun2socks on PATH
if [[ -x "${T2S}" ]]; then
    ln -sf "${T2S}" "/usr/local/bin/tun2socks"
fi

# Symlinks
info "Creating symlinks in /usr/local/bin"
for cmd in "${BIN_LINKS[@]}"; do
    ln -sf "${INSTALL_DIR}/bin/${cmd}" "/usr/local/bin/${cmd}"
    chmod +x "${INSTALL_DIR}/bin/${cmd}"
done

# Environment for systemd and shells
info "Setting SSH_FREE_ROOT=${INSTALL_DIR}"
cat > /etc/profile.d/ssh-free.sh <<EOF
export SSH_FREE_ROOT=${INSTALL_DIR}
EOF
chmod 644 /etc/profile.d/ssh-free.sh

# systemd
if command -v systemctl &>/dev/null; then
    info "Installing systemd units"
    sed "s|/opt/ssh-free|${INSTALL_DIR}|g" \
        "${INSTALL_DIR}/services/ssh-free-monitor.service" \
        > /etc/systemd/system/ssh-free-monitor.service
    systemctl daemon-reload
fi

info "Installation complete!"
echo ""
echo "  sudo ssh-free root@YOUR_SERVER"
echo "  sudo ssh-free --tui"
echo "  sudo ssh-free --profile home"
echo "  sudo status --watch"
echo "  sudo ssh-free-stop"
echo "  sudo doctor"
echo "  sudo status"
echo ""
