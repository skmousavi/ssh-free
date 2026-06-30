"""Resolve project root when invoked via /usr/local/bin symlink."""

import os
import sys
from pathlib import Path

INSTALLED_ROOT = Path("/opt/ssh-free")


def init(caller_file: str) -> str:
    root = os.environ.get("SSH_FREE_ROOT")

    if not root:
        if (INSTALLED_ROOT / "lib" / "__init__.py").exists():
            root = str(INSTALLED_ROOT)
        else:
            root = str(Path(caller_file).resolve().parent.parent)

    os.environ.setdefault("SSH_FREE_ROOT", root)

    if root not in sys.path:
        sys.path.insert(0, root)

    return root
