"""Resolve project root when invoked via symlink or Windows PATH."""

import os
import sys
from pathlib import Path


def _default_installed_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "ssh-free"
    return Path("/opt/ssh-free")


def init(caller_file: str) -> str:
    root = os.environ.get("SSH_FREE_ROOT")

    if not root:
        inst = _default_installed_root()
        if (inst / "lib" / "__init__.py").exists():
            root = str(inst)
        else:
            root = str(Path(caller_file).resolve().parent.parent)

    os.environ.setdefault("SSH_FREE_ROOT", root)

    if root not in sys.path:
        sys.path.insert(0, root)

    return root
