#!/usr/bin/env python3
"""Lock file to prevent concurrent sessions (stale-lock aware)."""

import os

from lib.paths import LOCK_FILE
from lib.platform import pid_alive


class SessionLock:

    def _read_pid(self):
        try:
            return int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            return None

    def _clear_if_stale(self) -> bool:
        """Remove the lock file if it belongs to a dead/unknown process.

        Returns True if the lock is stale (removed or absent), False if a
        live process still holds it.
        """
        if not LOCK_FILE.exists():
            return True

        pid = self._read_pid()
        if pid is None or not pid_alive(pid):
            LOCK_FILE.unlink(missing_ok=True)
            return True
        return False

    def acquire(self) -> bool:
        if not self._clear_if_stale():
            return False

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            LOCK_FILE.write_text(str(os.getpid()))
        except OSError:
            return False
        return True

    def release(self):
        LOCK_FILE.unlink(missing_ok=True)

    def is_locked(self) -> bool:
        """True only if a live process holds the lock. Cleans up stale locks."""
        return not self._clear_if_stale()

    def force_release(self):
        self.release()
