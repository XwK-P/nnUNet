from __future__ import annotations

import sys


def _fake_argv() -> list[str]:
    return [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]


def test_train_dry_run_single_fold(populated_client):
    r = populated_client.post(
        "/api/train?dry_run=true",
        json={"dataset_id": 27, "configuration": "3d_fullres", "folds": ["0"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["argv"][:4] == ["nnUNetv2_train", "27", "3d_fullres", "0"]


def test_train_dry_run_multifold(populated_client):
    r = populated_client.post(
        "/api/train?dry_run=true",
        json={
            "dataset_id": 27, "configuration": "3d_fullres",
            "folds": ["0", "1", "2"],
        },
    )
    body = r.json()
    assert len(body["jobs"]) == 3
    folds = [j["argv"][3] for j in body["jobs"]]
    assert folds == ["0", "1", "2"]


def test_train_enqueue_creates_n_jobs(populated_client, monkeypatch):
    monkeypatch.setattr(
        "nnunetv2.gui.routers.train.render_train",
        lambda req: _fake_argv(),
    )
    r = populated_client.post(
        "/api/train",
        json={"dataset_id": 27, "configuration": "3d_fullres",
              "folds": ["0", "1"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["job_ids"]) == 2


def test_train_includes_npz_when_requested(populated_client):
    r = populated_client.post(
        "/api/train?dry_run=true",
        json={"dataset_id": 27, "configuration": "3d_fullres",
              "folds": ["0"], "npz": True},
    )
    body = r.json()
    assert "--npz" in body["jobs"][0]["argv"]


def test_train_dry_run_with_trainer_and_plans(populated_client):
    r = populated_client.post(
        "/api/train?dry_run=true",
        json={"dataset_id": 27, "configuration": "3d_fullres",
              "folds": ["0"], "trainer": "nnUNetTrainerCustom",
              "plans": "nnUNetResEncUNetLPlans"},
    )
    body = r.json()
    argv = body["jobs"][0]["argv"]
    assert "-tr" in argv and "nnUNetTrainerCustom" in argv
    assert "-p" in argv and "nnUNetResEncUNetLPlans" in argv


def test_train_enqueue_uses_cfg_paths_in_job_env(
    populated_client, populated_paths, monkeypatch
):
    """train.enqueue must inject GuiConfig paths into the job env, not
    just inherit os.environ. When the GUI was started with --raw
    overrides that diverge from the parent shell's nnUNet_raw, spawned
    CLIs (which read paths from env via nnunetv2/paths.py) need to see
    the cfg paths — otherwise training fails immediately or targets
    the wrong dataset roots.
    """
    import json
    # Diverge the process env after the app's GuiConfig was already
    # built from populated_paths in the fixture. The launched job
    # should still see cfg.raw etc., not "/stale/...".
    monkeypatch.setenv("nnUNet_raw", "/stale/raw")
    monkeypatch.setenv("nnUNet_preprocessed", "/stale/pre")
    monkeypatch.setenv("nnUNet_results", "/stale/res")
    monkeypatch.setattr(
        "nnunetv2.gui.routers.train.render_train",
        lambda req: _fake_argv(),
    )
    r = populated_client.post(
        "/api/train",
        json={"dataset_id": 27, "configuration": "3d_fullres", "folds": ["0"]},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["job_ids"][0]
    j = populated_client.get(f"/api/jobs/{job_id}").json()
    env = json.loads(j["env_json"])
    assert env["nnUNet_raw"] == str(populated_paths["raw"])
    assert env["nnUNet_preprocessed"] == str(populated_paths["preprocessed"])
    assert env["nnUNet_results"] == str(populated_paths["results"])


def test_train_validation_missing_required(populated_client):
    r = populated_client.post("/api/train", json={"folds": ["0"]})
    assert r.status_code == 422
