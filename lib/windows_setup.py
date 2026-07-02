#!/usr/bin/env python3
"""
Windows prerequisite checker and installer (like install.sh on Linux).

Usage:
    python lib/windows_setup.py --ensure-deps   # before each run
    python lib/windows_setup.py --install-deps  # install step only
    python lib/windows_setup.py --verify        # post-install verification
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

VERSION = "3.0.0"
MIN_PYTHON = (3, 8)

OPENSSH_CAPABILITY = "OpenSSH.Client~~~~0.0.1.0"
SSH_PATHS = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.cmd",
]


class SetupError(RuntimeError):
    pass


def _ok(msg: str) -> None:
    print(f"[+] {msg}")


def _warn(msg: str) -> None:
    print(f"[!] {msg}")


def _fail(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    raise SetupError(msg)


def _run(cmd: List[str], timeout: int = 120) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"


def find_python() -> List[str]:
    for spec in (["python"], ["py", "-3"], ["python3"]):
        exe = spec[0]
        if shutil.which(exe):
            code, out, err = _run(spec + ["--version"], timeout=15)
            if code == 0:
                ver_line = out or err
                return spec
    return []


def check_python_version(py_cmd: List[str]) -> None:
    code, out, err = _run(py_cmd + ["-c", "import sys; print(sys.version_info[:2])"])
    if code != 0:
        _fail("Could not determine Python version")
    try:
        major, minor = map(int, out.strip().strip("()").split(","))
        if (major, minor) < MIN_PYTHON:
            _fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, found {major}.{minor}")
    except ValueError:
        _warn(f"Python version check inconclusive: {out}")


def ensure_pip(py_cmd: List[str]) -> None:
    code, _, _ = _run(py_cmd + ["-m", "pip", "--version"], timeout=30)
    if code == 0:
        _ok("pip OK")
        return

    _warn("pip not found — bootstrapping...")
    _run(py_cmd + ["-m", "ensurepip", "--upgrade"], timeout=120)
    code, _, _ = _run(py_cmd + ["-m", "pip", "--version"], timeout=30)
    if code != 0:
        _fail("pip is required. Reinstall Python and check 'pip' option.")


def ensure_pyyaml(py_cmd: List[str]) -> None:
    code, _, _ = _run(py_cmd + ["-c", "import yaml"], timeout=15)
    if code == 0:
        _ok("Python dependency OK (yaml)")
        return

    _warn("PyYAML not found — installing...")
    for extra in ([], ["--user"]):
        code, out, err = _run(
            py_cmd + ["-m", "pip", "install", *extra, "pyyaml"],
            timeout=180,
        )
        if code == 0:
            break
        _warn(err or out or "pip install failed")

    code, _, _ = _run(py_cmd + ["-c", "import yaml"], timeout=15)
    if code != 0:
        _fail("PyYAML required. Run: python -m pip install pyyaml")


def find_ssh() -> Optional[Path]:
    for path in SSH_PATHS:
        if path.is_file():
            return path
    which = shutil.which("ssh")
    if which:
        return Path(which)
    return None


def install_openssh_client() -> bool:
    """Try to install OpenSSH Client (may need admin). Returns True if available after."""
    if find_ssh():
        return True

    _warn("OpenSSH client not found — attempting install...")

    # Windows Optional Feature (admin)
    ps = (
        f"Add-WindowsCapability -Online -Name {OPENSSH_CAPABILITY} "
        "| Out-Null; exit $LASTEXITCODE"
    )
    code, _, err = _run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        timeout=300,
    )
    if code == 0 and find_ssh():
        _ok("OpenSSH client installed")
        return True

    # winget fallback
    if shutil.which("winget"):
        code, _, _ = _run(
            [
                "winget", "install", "--id", "Microsoft.OpenSSH.Beta",
                "-e", "--accept-source-agreements", "--accept-package-agreements",
            ],
            timeout=300,
        )
        if find_ssh():
            _ok("OpenSSH client installed (winget)")
            return True

    return False


def check_openssh(required: bool = True) -> None:
    path = find_ssh()
    if path:
        _ok(f"OpenSSH client ({path})")
        return

    if install_openssh_client():
        return

    msg = (
        "OpenSSH client not installed.\n"
        "  Settings -> Apps -> Optional features -> Add OpenSSH Client\n"
        "  Or run PowerShell as Administrator:\n"
        f"  Add-WindowsCapability -Online -Name {OPENSSH_CAPABILITY}"
    )
    if required:
        _fail(msg)
    _warn(msg)


def check_optional_tools() -> None:
    for tool in ("curl", "ping"):
        if shutil.which(tool):
            _ok(f"{tool} OK")
        else:
            _warn(f"{tool} not in PATH (optional)")


def install_dependencies(py_cmd: Optional[List[str]] = None) -> List[str]:
    _ok(f"Checking Windows prerequisites (ssh-free v{VERSION})")

    py_cmd = py_cmd or find_python()
    if not py_cmd:
        _fail(
            "Python 3 not found.\n"
            "  Download: https://python.org\n"
            "  During install, check 'Add python.exe to PATH'"
        )

    ver_code, ver_out, ver_err = _run(py_cmd + ["--version"], timeout=15)
    if ver_code == 0:
        _ok(f"Python ({ver_out or ver_err})")
    check_python_version(py_cmd)
    ensure_pip(py_cmd)
    ensure_pyyaml(py_cmd)
    check_openssh(required=True)
    check_optional_tools()

    _ok("All prerequisites OK")
    return py_cmd


def verify_installation(root: Path) -> None:
    _ok("Verifying installation...")
    if not (root / "bin" / "ssh-free").is_file():
        _fail(f"Missing {root / 'bin' / 'ssh-free'}")

    py_cmd = find_python()
    if not py_cmd:
        _fail("Python not found after install")

    code, out, err = _run(
        py_cmd
        + [
            str(root / "bin" / "doctor"),
        ],
        timeout=60,
        env={**os.environ, "SSH_FREE_ROOT": str(root)},
    )
    if code != 0:
        _warn("doctor reported issues (see above)")
    else:
        _ok("doctor: system ready")


def main() -> int:
    parser = argparse.ArgumentParser(description="ssh-free Windows setup")
    parser.add_argument(
        "--ensure-deps",
        action="store_true",
        help="Check and install missing dependencies (default)",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Alias for --ensure-deps",
    )
    parser.add_argument(
        "--verify",
        metavar="ROOT",
        help="Verify install at ROOT",
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        print("[INFO] windows_setup.py is for Windows only", file=sys.stderr)
        return 0

    try:
        if args.verify:
            verify_installation(Path(args.verify))
            return 0

        install_dependencies()
        return 0
    except SetupError:
        return 1
    except Exception as exc:
        _fail(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
