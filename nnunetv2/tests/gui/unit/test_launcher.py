from __future__ import annotations

import json
import os
import sys
import time

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.signals import is_alive
from nnunetv2.gui.state.jobs import get_job


def test_spawn_creates_running_job(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.5", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "test.log"),
                output_run_id="Dataset027_ACDC/x__y__z/fold_0")
    try:
        assert job.status == "running"
        assert job.pid is not None
        assert job.pgid is not None
        # Verify it's actually running
        assert is_alive(job.pgid)
        # Wait for it to finish naturally via psutil (reaps the zombie too).
        import psutil
        try:
            psutil.Process(job.pid).wait(timeout=5)
        except psutil.NoSuchProcess:
            pass
        assert not is_alive(job.pgid)
    finally:
        # Best effort cleanup; if still alive, kill the group
        from nnunetv2.gui.jobs.signals import kill_group
        if job.pgid and is_alive(job.pgid):
            kill_group(job.pgid)


def test_spawn_writes_argv_and_log_path(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]
    job = spawn(gui_config, kind="predict", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "predict.log"),
                output_run_id=None)
    fetched = get_job(gui_config, job.id)
    assert json.loads(fetched.args_json) == argv
    assert fetched.log_path == str(gui_config.results / "predict.log")


def test_spawn_creates_detached_process_group(gui_config):
    """On POSIX, the child's pgid must differ from the parent's."""
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.3", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "x.log"),
                output_run_id=None)
    try:
        if os.name == "posix":
            assert job.pgid != os.getpgrp()
    finally:
        from nnunetv2.gui.jobs.signals import kill_group, is_alive
        if job.pgid and is_alive(job.pgid):
            kill_group(job.pgid)


def test_spawn_preserves_slot(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "s.log"), slot="dataset_27")
    fetched = get_job(gui_config, job.id)
    assert fetched.slot == "dataset_27"


def test_spawn_records_log_path_contents(gui_config):
    init_db(gui_config)
    log_path = gui_config.results / "stdout_capture.log"
    # Print something then exit; verify it landed in the log file
    argv = [sys.executable, "-c", "print('hello from child'); import sys; sys.exit(0)"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(log_path))
    # Wait for it to exit
    from nnunetv2.gui.jobs.signals import is_alive
    deadline = time.time() + 5
    while time.time() < deadline and is_alive(job.pgid):
        time.sleep(0.05)
    # Give the file some time to flush
    time.sleep(0.1)
    assert log_path.exists()
    contents = log_path.read_text()
    assert "hello from child" in contents
