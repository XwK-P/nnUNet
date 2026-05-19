from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.reaper import attach_on_boot, run_reaper
from nnunetv2.gui.state.jobs import Job, get_job, insert_job


@pytest.mark.asyncio
async def test_reaper_marks_completed_on_clean_exit(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r.log"))
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "completed"
    assert fetched.exit_code == 0


@pytest.mark.asyncio
async def test_reaper_marks_failed_on_nonzero_exit(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "3"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r2.log"))
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "failed"
    assert fetched.exit_code == 3


@pytest.mark.asyncio
async def test_reaper_preserves_killed_status_after_stop(gui_config):
    """When /api/jobs/{id}/stop has already marked the row 'killed', the
    reaper must not rewrite that status to 'failed' based on the SIGTERM
    exit code it observes when the subprocess actually exits.
    """
    from datetime import datetime, timezone
    from nnunetv2.gui.state.jobs import update_job_status
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "3"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r_killed.log"))
    # Simulate the stop handler running before the reaper observes the exit.
    stop_time = datetime.now(timezone.utc)
    update_job_status(gui_config, job.id, status="killed", ended_at=stop_time)
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "killed", "reaper overwrote a user-initiated kill"
    # Exit code still recorded for diagnostics.
    assert fetched.exit_code == 3
    # ended_at preserved from the stop handler.
    assert fetched.ended_at is not None


@pytest.mark.asyncio
async def test_attach_on_boot_marks_unknown_for_dead_pid(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=999999, pgid=999999,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status in ("failed", "unknown")


@pytest.mark.asyncio
async def test_attach_on_boot_reattaches_live_pid(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "1.0", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r3.log"))
    # Simulate restart: re-run attach. Should detect alive and schedule reaper.
    tasks = await attach_on_boot(gui_config)
    assert len(tasks) == 1
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "completed"


@pytest.mark.asyncio
async def test_attach_on_boot_marks_failed_for_no_pid(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=None, pgid=None,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "failed"
    assert fetched.error_message and "no pid" in fetched.error_message


@pytest.mark.asyncio
async def test_attach_on_boot_recovers_completed_for_train_with_final_ckpt(gui_config, tmp_path):
    init_db(gui_config)
    run_id = "Dataset027_ACDC/p__t__c/fold_0"
    out = gui_config.results / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkpoint_final.pth").write_bytes(b"x")
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=999999, pgid=999999,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=run_id, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "completed"
