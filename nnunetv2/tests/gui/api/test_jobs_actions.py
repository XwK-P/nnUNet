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
