from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.queue import JobQueue
from nnunetv2.gui.state.jobs import JobFilter, get_job, list_jobs


@pytest.mark.asyncio
async def test_queue_runs_jobs_serially(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)

    argv1 = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.3", "0"]
    argv2 = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "0"]

    j1 = await q.enqueue(kind="train", argv=argv1, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j1.log"))
    j2 = await q.enqueue(kind="train", argv=argv2, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j2.log"))

    # Wait for both to finish
    await q.drain(timeout=10)
    statuses = [j.status for j in list_jobs(gui_config, JobFilter())]
    assert set(statuses) == {"completed"}
    j1f = get_job(gui_config, j1.id)
    j2f = get_job(gui_config, j2.id)
    # Ordering: j2 must have started after j1 ended (serial).
    assert j2f.started_at is not None
    assert j1f.ended_at is not None
    assert j2f.started_at >= j1f.ended_at


@pytest.mark.asyncio
async def test_queue_cancel_queued_only(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.5", "0"]

    j1 = await q.enqueue(kind="train", argv=argv, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j1.log"))
    j2 = await q.enqueue(kind="train", argv=argv, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j2.log"))
    # j2 is queued; cancel it
    await asyncio.sleep(0.05)
    ok = await q.cancel(j2.id)
    assert ok
    # Cancelling the already-running j1 returns False (must use stop)
    ok = await q.cancel(j1.id)
    assert ok is False
    await q.drain(timeout=10)
    assert get_job(gui_config, j2.id).status == "cancelled"


@pytest.mark.asyncio
async def test_queue_cancel_nonexistent_returns_false(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)
    ok = await q.cancel(99999)
    assert ok is False


@pytest.mark.asyncio
async def test_queue_uses_per_job_env_not_first_enqueue_env(gui_config, tmp_path):
    """When two jobs are queued under one slot with different envs, the
    second job must launch with its own env, not inherit the first.

    Strategy: have each subprocess write its key NNUNET_TEST_TAG to a file
    via a tiny stdin-free helper. The two jobs each pin a distinct value;
    if the worker reused the first job's env, the second file would carry
    the first value.
    """
    init_db(gui_config)
    q = JobQueue(gui_config)

    helper_src = tmp_path / "envtag.py"
    helper_src.write_text(
        "import os, sys\n"
        "open(sys.argv[1], 'w').write(os.environ.get('NNUNET_TEST_TAG', '<missing>'))\n"
    )
    tag1_out = tmp_path / "j1_tag.txt"
    tag2_out = tmp_path / "j2_tag.txt"

    env_a = {**os.environ, "NNUNET_TEST_TAG": "alpha"}
    env_b = {**os.environ, "NNUNET_TEST_TAG": "beta"}

    await q.enqueue(
        kind="train", argv=[sys.executable, str(helper_src), str(tag1_out)],
        env=env_a, log_path=str(gui_config.results / "j1.log"),
    )
    await q.enqueue(
        kind="train", argv=[sys.executable, str(helper_src), str(tag2_out)],
        env=env_b, log_path=str(gui_config.results / "j2.log"),
    )
    await q.drain(timeout=10)

    assert tag1_out.read_text() == "alpha"
    assert tag2_out.read_text() == "beta", (
        "second job inherited the first job's env — worker is reusing a single dict"
    )


@pytest.mark.asyncio
async def test_kickstart_pending_resumes_queued_after_restart(gui_config):
    """A queued row left from a previous boot must be picked up by kickstart_pending."""
    from nnunetv2.gui.state.jobs import Job, insert_job
    init_db(gui_config)
    import json as _json
    # Simulate a row written by a prior server boot, including the env
    # captured at that earlier enqueue — kickstart_pending must use that
    # row's env rather than asking callers to re-provide one.
    insert_job(gui_config, Job(
        id=None, kind="train",
        args_json='["%s", "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]'
                  % sys.executable.replace("\\", "\\\\"),
        env_json=_json.dumps(dict(os.environ)),
        pid=None, pgid=None, status="queued",
        started_at=None, ended_at=None, exit_code=None,
        log_path=str(gui_config.results / "boot.log"),
        output_run_id=None, created_by="gui", error_message=None, slot="global",
    ))
    # Fresh queue (mimics a fresh process), no prior enqueue to kick the worker.
    q = JobQueue(gui_config)
    kicked = await q.kickstart_pending()
    assert kicked == 1
    await q.drain(timeout=10)
    [row] = list_jobs(gui_config, JobFilter())
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_queue_failed_spawn_does_not_block_next(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)
    bad = ["/nonexistent/binary/that/will/not/run", "x"]
    good = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]
    j1 = await q.enqueue(kind="train", argv=bad, env=os.environ.copy(),
                          log_path=str(gui_config.results / "bad.log"))
    j2 = await q.enqueue(kind="train", argv=good, env=os.environ.copy(),
                          log_path=str(gui_config.results / "good.log"))
    await q.drain(timeout=10)
    j1f = get_job(gui_config, j1.id)
    j2f = get_job(gui_config, j2.id)
    assert j1f.status == "failed"
    assert j2f.status == "completed"
