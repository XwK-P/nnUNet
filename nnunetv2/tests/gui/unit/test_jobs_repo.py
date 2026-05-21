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


def test_job_default_slot_is_global(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make())
    assert j.slot == "global"


def test_job_explicit_slot_preserved(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make(slot="dataset_27"))
    fetched = get_job(gui_config, j.id)
    assert fetched.slot == "dataset_27"


def test_claim_queued_for_launch_returns_true_only_once(gui_config):
    """Atomic queued -> starting transition: the first claim wins; a
    concurrent claim must observe rowcount=0 even though the row id is
    still valid. Models the /cancel-after-pop race.
    """
    from nnunetv2.gui.state.jobs import claim_queued_for_launch
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="queued"))
    assert claim_queued_for_launch(gui_config, j.id) is True
    # Second claim sees status='starting' and fails the WHERE clause.
    assert claim_queued_for_launch(gui_config, j.id) is False
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "starting"


def test_claim_queued_for_launch_rejects_cancelled_row(gui_config):
    from nnunetv2.gui.state.jobs import claim_queued_for_launch
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="queued"))
    update_job_status(gui_config, j.id, status="cancelled")
    # Same row, but status is no longer 'queued' — the claim must be a no-op.
    assert claim_queued_for_launch(gui_config, j.id) is False
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "cancelled"


def test_claim_queued_for_cancel_returns_true_only_once(gui_config):
    """Cancel mirrors the launch CAS: only the first attempt wins; a
    duplicate (or post-launch) cancel must observe rowcount=0 even
    though the row id is still valid.
    """
    from nnunetv2.gui.state.jobs import claim_queued_for_cancel
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="queued"))
    ended = datetime(2026, 5, 21, 4, 30, tzinfo=timezone.utc)
    assert claim_queued_for_cancel(gui_config, j.id, ended_at=ended) is True
    assert claim_queued_for_cancel(gui_config, j.id, ended_at=ended) is False
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "cancelled"
    assert fetched.ended_at is not None


def test_cancel_loses_when_launch_already_claimed_the_row(gui_config):
    """If the worker's claim_queued_for_launch wins first, a follow-up
    cancel must NOT succeed (and must not overwrite ``starting`` to
    ``cancelled``). Without this guard, a successful cancel that races
    a successful claim would leave the DB row marked cancelled while
    the subprocess was already being spawned — an unkillable orphan.
    """
    from nnunetv2.gui.state.jobs import (
        claim_queued_for_cancel, claim_queued_for_launch,
    )
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="queued"))
    assert claim_queued_for_launch(gui_config, j.id) is True
    ended = datetime(2026, 5, 21, 4, 31, tzinfo=timezone.utc)
    assert claim_queued_for_cancel(gui_config, j.id, ended_at=ended) is False
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "starting"
    assert fetched.ended_at is None


def test_init_db_migrates_legacy_job_table(gui_config):
    """A state.db from an older install will have a `job` table that
    lacks both `slot` and `env_json`. init_db must add the missing
    nullable columns idempotently so the next enqueue can write to them.
    """
    import sqlite3
    cfg = gui_config
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    # Hand-build a pre-migration `job` table with the original v1 schema.
    db_path = cfg.state_db
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            args_json TEXT NOT NULL,
            pid INTEGER, pgid INTEGER,
            status TEXT NOT NULL,
            started_at TIMESTAMP, ended_at TIMESTAMP,
            exit_code INTEGER, log_path TEXT,
            output_run_id TEXT, created_by TEXT, error_message TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    # Migration should add slot + env_json without erroring.
    init_db(cfg)
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(job)")}
    conn.close()
    assert "slot" in cols
    assert "env_json" in cols
    # And the upgraded table is still functional through the ORM layer.
    j = insert_job(cfg, _make())
    assert j.slot == "global"
    assert j.env_json is None
