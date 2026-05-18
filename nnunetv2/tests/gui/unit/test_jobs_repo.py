from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.jobs import (
    Job, JobFilter, insert_job, get_job, list_jobs, update_job_status,
)


def _make(**ov) -> Job:
    base = Job(
        id=None, kind="train", args_json='{"dataset_id":27}',
        pid=None, pgid=None, status="queued",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None,
    )
    return base.model_copy(update=ov)


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_jobs(gui_config, JobFilter()) == []


def test_insert_returns_id(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make())
    assert j.id is not None
    fetched = get_job(gui_config, j.id)
    assert fetched.kind == "train"


def test_filter_by_status(gui_config):
    init_db(gui_config)
    insert_job(gui_config, _make(status="running"))
    insert_job(gui_config, _make(status="completed"))
    running = list_jobs(gui_config, JobFilter(status="running"))
    assert len(running) == 1


def test_filter_by_kind(gui_config):
    init_db(gui_config)
    insert_job(gui_config, _make(kind="train"))
    insert_job(gui_config, _make(kind="predict"))
    train = list_jobs(gui_config, JobFilter(kind="train"))
    assert len(train) == 1


def test_update_status(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="starting", pid=123))
    update_job_status(gui_config, j.id, status="running")
    j2 = get_job(gui_config, j.id)
    assert j2.status == "running"
    assert j2.pid == 123  # unchanged


def test_update_status_with_terminal_fields(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="running"))
    ended = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    update_job_status(gui_config, j.id, status="completed", ended_at=ended, exit_code=0)
    j2 = get_job(gui_config, j.id)
    assert j2.status == "completed"
    assert j2.exit_code == 0
    assert j2.ended_at is not None
