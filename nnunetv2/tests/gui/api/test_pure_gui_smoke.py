"""Pure-GUI launch smoke: enqueue via app.state.job_queue, then exercise
the API (/api/jobs/{id} get + /api/jobs/{id}/stop) to confirm the full
lifecycle wires together end-to-end without going through the real
nnUNetv2_* binaries.
"""
from __future__ import annotations

import os
import sys


def test_launch_then_stop(populated_client):
    """Enqueue via the queue + spawn directly, then stop through the API."""
    cfg = populated_client.app.state.gui_config

    # Spawn a long-lived subprocess directly using the launcher so the API
    # can observe a running row without relying on TestClient event-loop
    # scheduling for the queue worker.
    from nnunetv2.gui.jobs.launcher import spawn
    from nnunetv2.gui.jobs.signals import is_alive, kill_group

    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "30", "0"]
    log_path = str(cfg.results / ".nnunet_gui" / "logs" / "smoke.log")
    job = spawn(cfg, kind="train", argv=argv, env=os.environ.copy(),
                log_path=log_path)
    try:
        # Verify it's visible via the public API.
        r = populated_client.get(f"/api/jobs/{job.id}")
        assert r.status_code == 200
        assert r.json()["status"] == "running"

        # Stop via the API
        r = populated_client.post(f"/api/jobs/{job.id}/stop")
        assert r.status_code in (200, 202)

        # Reap the zombie so is_alive returns False
        try:
            import psutil
            psutil.Process(job.pid).wait(timeout=5)
        except Exception:
            pass

        final = populated_client.get(f"/api/jobs/{job.id}").json()
        assert final["status"] == "killed"
    finally:
        if job.pgid and is_alive(job.pgid):
            kill_group(job.pgid)


def test_launch_dry_run_preprocess_via_api(populated_client):
    """Dry-run preview round-trip through the public API."""
    r = populated_client.post(
        "/api/preprocess?dry_run=true",
        json={"dataset_id": 27, "verify_dataset_integrity": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_plan_and_preprocess"
    assert "--verify_dataset_integrity" in body["argv"]


def test_launch_dry_run_train_multifold_via_api(populated_client):
    r = populated_client.post(
        "/api/train?dry_run=true",
        json={"dataset_id": 27, "configuration": "3d_fullres",
              "folds": ["0", "1"], "npz": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 2
    assert "--npz" in body["jobs"][0]["argv"]
