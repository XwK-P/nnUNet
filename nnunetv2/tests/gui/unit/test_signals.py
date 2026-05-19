from __future__ import annotations

import os
import subprocess
import sys

from nnunetv2.gui.jobs.signals import is_alive, kill_group, terminate


def _spawn_long_sleep() -> subprocess.Popen:
    kwargs: dict = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "30"],
        **kwargs,
    )


def test_terminate_sends_sigterm():
    p = _spawn_long_sleep()
    try:
        pgid = os.getpgid(p.pid) if os.name == "posix" else p.pid
        terminate(pgid)
        code = p.wait(timeout=5)
        # SIGTERM exit on POSIX is -15; on Windows it's 1
        assert code is not None
    finally:
        if p.poll() is None:
            p.kill(); p.wait(timeout=2)


def test_kill_group_sends_sigkill():
    p = _spawn_long_sleep()
    try:
        pgid = os.getpgid(p.pid) if os.name == "posix" else p.pid
        kill_group(pgid)
        code = p.wait(timeout=5)
        assert code is not None
    finally:
        if p.poll() is None:
            p.kill(); p.wait(timeout=2)


def test_terminate_already_dead_is_noop():
    p = _spawn_long_sleep()
    p.kill(); p.wait(timeout=5)
    # Should not raise
    terminate(p.pid)
    kill_group(p.pid)


def test_is_alive_for_dead_pgid():
    p = _spawn_long_sleep()
    pid = p.pid
    p.kill(); p.wait(timeout=5)
    assert is_alive(pid) is False


def test_is_alive_for_zero_or_negative():
    assert is_alive(0) is False
    assert is_alive(-1) is False
