from __future__ import annotations

import json
import os
import sys
import time

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.signals import is_alive, kill_group
from nnunetv2.gui.state.jobs import Job, insert_job


def _cfg_from_client(populated_client) -> GuiConfig:
    """Reuse the app's config so spawn writes to the same DB the API reads."""
    return populated_client.app.state.gui_config


def test_stop_running_job(populated_client):
    cfg = _cfg_from_client(populated_client)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "30"]
    job = spawn(cfg, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(cfg.results / "stoptest.log"))
    try:
        r = populated_client.post(f"/api/jobs/{job.id}/stop")
        assert r.status_code in (200, 202)
        # Reap the (potentially zombie) child so is_alive returns False.
        import psutil
        try:
            psutil.Process(job.pid).wait(timeout=5)
        except psutil.NoSuchProcess:
            pass
        assert not is_alive(job.pgid)
        # And the row was transitioned to 'killed'
        r2 = populated_client.get(f"/api/jobs/{job.id}")
        assert r2.json()["status"] == "killed"
    finally:
        if job.pgid and is_alive(job.pgid):
            kill_group(job.pgid)


def test_stop_completed_job_rejected(populated_client):
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=None, pgid=None, status="completed",
        started_at=None, ended_at=None, exit_code=0,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/stop")
    assert r.status_code == 409


def test_stop_unknown_job_404(populated_client):
    r = populated_client.post("/api/jobs/99999/stop")
    assert r.status_code == 404


def test_stop_returns_504_when_process_survives_kill(populated_client, monkeypatch):
    """If signal delivery succeeds but the process keeps running past
    our SIGTERM+SIGKILL budget (permission edge case, container
    namespace, uninterruptable kernel state), the row must NOT be
    marked killed — that would hide live GPU usage. Surface 504 and
    leave the status alone so the reaper can transition it later.
    """
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=42, pgid=42, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    # Stub signal delivery so terminate/kill_group are no-ops and
    # is_alive always reports the process is still alive.
    monkeypatch.setattr("nnunetv2.gui.routers.jobs.terminate", lambda pgid: None)
    monkeypatch.setattr("nnunetv2.gui.routers.jobs.kill_group", lambda pgid: None)
    monkeypatch.setattr("nnunetv2.gui.routers.jobs.is_alive", lambda pgid: True)
    r = populated_client.post(f"/api/jobs/{j.id}/stop")
    assert r.status_code == 504, r.text
    body = r.json()
    detail = body.get("detail") or body.get("message", "")
    assert "still alive" in detail.lower()
    # Crucially the row stays 'running' — we did not lie about killing it.
    r2 = populated_client.get(f"/api/jobs/{j.id}")
    assert r2.json()["status"] == "running"


def test_stop_starting_without_pgid_returns_conflict_not_500(populated_client):
    """In the narrow window between status='starting' and the launcher
    writing pid/pgid back, /stop must not 500 the user. Surface 409 so
    the client can retry instead of bubbling a server error to the UI.
    """
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=None, pgid=None, status="starting",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/stop")
    assert r.status_code == 409
    assert "retry" in r.json().get("detail", "").lower()


def test_cancel_queued_job(populated_client):
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=None, pgid=None, status="queued",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/cancel")
    assert r.status_code == 200


def test_cancel_running_job_rejected(populated_client):
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=999999, pgid=999999, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/cancel")
    assert r.status_code == 409


def test_cancel_unknown_job_404(populated_client):
    r = populated_client.post("/api/jobs/99999/cancel")
    assert r.status_code == 404


def test_restart_finished_job(populated_client):
    cfg = _cfg_from_client(populated_client)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05"]
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json=json.dumps(argv),
        pid=None, pgid=None, status="failed",
        started_at=None, ended_at=None, exit_code=1,
        log_path=str(cfg.results / "r.log"),
        output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/restart")
    assert r.status_code == 201
    assert "new_job_id" in r.json()


def test_restart_running_rejected(populated_client):
    cfg = _cfg_from_client(populated_client)
    j = insert_job(cfg, Job(
        id=None, kind="train", args_json="[]",
        pid=999999, pgid=999999, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    r = populated_client.post(f"/api/jobs/{j.id}/restart")
    assert r.status_code == 409


def test_restart_unknown_job_404(populated_client):
    r = populated_client.post("/api/jobs/99999/restart")
    assert r.status_code == 404
