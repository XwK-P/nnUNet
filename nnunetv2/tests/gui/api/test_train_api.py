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


def test_train_validation_missing_required(populated_client):
    r = populated_client.post("/api/train", json={"folds": ["0"]})
    assert r.status_code == 422
