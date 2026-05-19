from __future__ import annotations

import sys


def _fake_argv() -> list[str]:
    return [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]


def test_predict_dry_run(populated_client, tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    r = populated_client.post(
        "/api/predict?dry_run=true",
        json={
            "dataset_id": 27, "configuration": "3d_fullres",
            "input_folder": str(in_dir), "output_folder": str(out_dir),
            "folds": ["all"], "save_probabilities": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_predict"
    assert "--save_probabilities" in body["argv"]
    assert "job_id" not in body


def test_predict_validation_missing_paths(populated_client):
    r = populated_client.post(
        "/api/predict",
        json={"dataset_id": 27, "configuration": "3d_fullres"},
    )
    assert r.status_code == 422


def test_predict_enqueue_creates_job(populated_client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "nnunetv2.gui.routers.predict.render_predict",
        lambda req: _fake_argv(),
    )
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    r = populated_client.post(
        "/api/predict",
        json={
            "dataset_id": 27, "configuration": "3d_fullres",
            "input_folder": str(in_dir), "output_folder": str(out_dir),
            "folds": ["0"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert "job_id" in body


def test_predict_dry_run_multi_fold_argv(populated_client, tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    r = populated_client.post(
        "/api/predict?dry_run=true",
        json={
            "dataset_id": 27, "configuration": "3d_fullres",
            "input_folder": str(in_dir), "output_folder": str(out_dir),
            "folds": ["0", "1", "2"],
        },
    )
    body = r.json()
    argv = body["argv"]
    f_idx = argv.index("-f")
    assert argv[f_idx + 1 : f_idx + 4] == ["0", "1", "2"]
