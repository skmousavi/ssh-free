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

    if py_cmd is None:
        py_cmd = [sys.executable] if sys.platform == "win32" else find_python()
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

    env = {**os.environ, "SSH_FREE_ROOT": str(root)}
    result = subprocess.run(
        [sys.executable, str(root / "bin" / "doctor")],
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        _warn("doctor reported issues (see above)")
    else:
        _ok("doctor: system ready")


def get_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "ssh-free"


def _add_user_path(directory: str) -> None:
    import winreg

    launcher = str(directory)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    ) as key:
        try:
            path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            path = ""

        parts = [p for p in path.split(";") if p]
        if launcher not in parts:
            parts.append(launcher)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))

        winreg.SetValueEx(key, "SSH_FREE_ROOT", 0, winreg.REG_EXPAND_SZ, str(get_install_dir()))


def _copy_tree(repo_root: Path, install_dir: Path) -> None:
    exclude = {".git", "__pycache__", "launchers"}
    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    for item in repo_root.iterdir():
        if item.name in exclude:
            continue
        dest = install_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, dest)

    (install_dir / "logs").mkdir(exist_ok=True)
    (install_dir / "runtime").mkdir(exist_ok=True)


def _write_launchers(install_dir: Path, py_exe: str) -> Path:
    launcher_dir = install_dir / "launchers"
    launcher_dir.mkdir(exist_ok=True)
    names = ("ssh-free", "ssh-free-stop", "doctor", "status", "tui")

    for name in names:
        script = install_dir / "bin" / name
        content = (
            "@echo off\r\n"
            "setlocal\r\n"
            f'set "SSH_FREE_ROOT={install_dir}"\r\n'
            f'call "{install_dir}\\win-prereq.bat" || exit /b 1\r\n'
            f'"{py_exe}" "{script}" %*\r\n'
        )
        (launcher_dir / f"{name}.cmd").write_text(content, encoding="ascii")

    return launcher_dir


def install_full(repo_root: Path) -> Path:
    """Full install like install.sh — deps, copy files, PATH, verify."""
    # CMD quirk: "%~dp0" ends with \ which escapes the closing quote (path gets a ")
    raw = str(repo_root).strip().strip('"').rstrip("\\/")
    repo_root = Path(raw).resolve()
    if not (repo_root / "bin" / "ssh-free").is_file():
        _fail(f"Invalid repo: {repo_root} (bin\\ssh-free not found)")

    install_dependencies([sys.executable])

    install_dir = get_install_dir()
    _ok(f"Copying files to {install_dir}")
    _copy_tree(repo_root, install_dir)

    py_exe = sys.executable
    launcher_dir = _write_launchers(install_dir, py_exe)
    _ok(f"Creating launchers in {launcher_dir}")

    _add_user_path(str(launcher_dir))
    _ok(f"Added to user PATH: {launcher_dir}")

    os.environ["SSH_FREE_ROOT"] = str(install_dir)
    path = os.environ.get("Path", "")
    if str(launcher_dir) not in path:
        os.environ["Path"] = f"{path};{launcher_dir}" if path else str(launcher_dir)

    verify_installation(install_dir)
    return install_dir


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
    parser.add_argument(
        "--install",
        metavar="REPO",
        help="Full install from repo directory",
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        print("[INFO] windows_setup.py is for Windows only", file=sys.stderr)
        return 0

    try:
        if args.install:
            dest = install_full(Path(args.install))
            _ok("Installation complete!")
            print()
            print("  Close and reopen CMD, then:")
            print("    ssh-free administrator@192.168.0.9")
            print()
            print("  Or from repo folder now:")
            print("    ssh-free.bat administrator@192.168.0.9")
            print()
            print("  v2rayN must be running (127.0.0.1:10808)")
            print()
            return 0

        if args.verify:
            verify_installation(Path(args.verify))
            return 0

        if args.ensure_deps or args.install_deps or len(sys.argv) == 1:
            install_dependencies()
            return 0

        parser.print_help()
        return 1
    except SetupError:
        return 1
    except Exception as exc:
        _fail(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
