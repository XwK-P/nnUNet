from __future__ import annotations

import pytest


def argv_index(argv, needle):
    return argv.index(needle)


@pytest.fixture
def models_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_models_groups_runs(models_client):
    r = models_client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    ids = sorted(m["id"] for m in body)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres",
    ]


def test_get_model_returns_folds(models_client):
    r = models_client.get(
        "/api/models/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dataset_id"] == "Dataset027_ACDC"
    assert body["configuration"] == "3d_fullres"
    assert len(body["folds"]) == 1
    assert body["folds"][0]["fold"] == "0"


def test_get_model_not_found(models_client):
    r = models_client.get("/api/models/Dataset999_X/p__t__c")
    assert r.status_code == 404


def test_export_dry_run(models_client):
    r = models_client.post("/api/models/export?dry_run=true",
                            json={"dataset_id": 27, "output_zip": "/tmp/model.zip",
                                  "configurations": ["3d_fullres"]})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_export_model_to_zip"
    assert body["argv"][argv_index(body['argv'], '-d') + 1] == "27"
    assert "job_id" not in body


def test_export_enqueues_job(models_client):
    r = models_client.post("/api/models/export",
                            json={"dataset_id": 27, "output_zip": "/tmp/model.zip"})
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_export_validation_error(models_client):
    r = models_client.post("/api/models/export", json={})
    assert r.status_code == 422


def test_import_dry_run(models_client):
    r = models_client.post("/api/models/import?dry_run=true",
                            json={"zip_path": "/tmp/some_model.zip"})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"] == ["nnUNetv2_install_pretrained_model_from_zip", "/tmp/some_model.zip"]


def test_import_enqueue(models_client):
    r = models_client.post("/api/models/import",
                            json={"zip_path": "/tmp/some_model.zip"})
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_import_validation_error(models_client):
    r = models_client.post("/api/models/import", json={})
    assert r.status_code == 422


def test_find_best_dry_run(models_client):
    r = models_client.post("/api/models/find_best?dry_run=true",
                            json={"dataset_id": 27, "configurations": ["3d_fullres", "2d"]})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_find_best_configuration"
    assert "27" in body["argv"]


def test_find_best_enqueue(models_client):
    r = models_client.post("/api/models/find_best",
                            json={"dataset_id": 27})
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_ensemble_dry_run(models_client):
    r = models_client.post("/api/models/ensemble?dry_run=true",
                            json={"input_folders": ["/a", "/b"], "output_folder": "/out"})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_ensemble"
    i_idx = body["argv"].index("-i")
    assert body["argv"][i_idx + 1 : i_idx + 3] == ["/a", "/b"]


def test_ensemble_enqueue(models_client):
    r = models_client.post("/api/models/ensemble",
                            json={"input_folders": ["/a", "/b"], "output_folder": "/out"})
    assert r.status_code == 201
    assert "job_id" in r.json()
