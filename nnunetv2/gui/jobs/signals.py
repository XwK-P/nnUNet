"""Cross-platform signal helpers — never raise on already-dead pgid."""
from __future__ import annotations

import os
import signal
import sys


def terminate(pgid: int) -> None:
    """SIGTERM the entire process group (POSIX) or send Ctrl-Break (Windows)."""
    try:
        if os.name == "posix":
            os.killpg(pgid, signal.SIGTERM)
        elif sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP allows sending CTRL_BREAK_EVENT to the pid
            os.kill(pgid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    except (ProcessLookupError, OSError):
        pass


def kill_group(pgid: int) -> None:
    """SIGKILL the process group; on Windows TerminateProcess via os.kill."""
    try:
        if os.name == "posix":
            os.killpg(pgid, signal.SIGKILL)
        elif sys.platform == "win32":
            os.kill(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def is_alive(pgid: int) -> bool:
    """Return True if pgid still has at least one live process."""
    if pgid is None or pgid <= 0:
        return False
    try:
        os.kill(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
