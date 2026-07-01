#!/usr/bin/env python3
"""Lock file to prevent concurrent sessions."""

import os
import signal
from lib.paths import LOCK_FILE
from lib.platform import pid_alive


class SessionLock:

    def acquire(self) -> bool:
        if LOCK_FILE.exists():
            return False

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(str(os.getpid()))
        return True

    def release(self):
        LOCK_FILE.unlink(missing_ok=True)

    def is_locked(self) -> bool:
        if not LOCK_FILE.exists():
            return False

        try:
            pid = int(LOCK_FILE.read_text().strip())
            return pid_alive(pid)
        except (ValueError, OSError):
            LOCK_FILE.unlink(missing_ok=True)
            return False

    def force_release(self):
        self.release()
