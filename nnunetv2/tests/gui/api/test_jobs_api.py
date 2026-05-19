from __future__ import annotations


def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_job_404(client):
    r = client.get("/api/jobs/9999")
    assert r.status_code == 404


def test_list_jobs_after_insert(gui_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.gui.state.jobs import Job, insert_job
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    app = create_app(cfg)
    insert_job(cfg, Job(id=None, kind="train", args_json="{}", pid=None, pgid=None,
                        status="completed", started_at=None, ended_at=None,
                        exit_code=0, log_path=None, output_run_id=None,
                        created_by="cli", error_message=None))
    c = TestClient(app)
    r = c.get("/api/jobs")
    assert r.status_code == 200
    assert len(r.json()) == 1
