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
