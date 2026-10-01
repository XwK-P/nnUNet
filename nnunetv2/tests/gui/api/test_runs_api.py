from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


@pytest.fixture
def run_with_tb(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir
    fold_dir = (populated_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    build_tb_event_dir(fold_dir / "tensorboard",
                       scalars={"train_loss": [(0, 1.0), (1, 0.7), (2, 0.5)]})
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_runs_empty(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_populated(populated_client):
    r = populated_client.get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(run["dataset_id"] == "Dataset027_ACDC" for run in body)


def test_list_runs_filter_by_dataset_id(populated_client):
    r = populated_client.get("/api/runs?dataset_id=Dataset027_ACDC")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = populated_client.get("/api/runs?dataset_id=Dataset999_None")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_filter_by_configuration(populated_client):
    r = populated_client.get("/api/runs?configuration=3d_fullres")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["configuration"] == "3d_fullres"


def test_list_runs_filter_by_status(populated_client):
    r = populated_client.get("/api/runs?status=completed")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_run_detail(populated_client):
    r = populated_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["configuration"] == "3d_fullres"
    assert body["fold"] == "0"


def test_get_run_not_found(client):
    r = client.get("/api/runs/Dataset999_None/x__y__z/fold_0")
    assert r.status_code == 404


def test_metrics_history_replay(run_with_tb):
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = run_with_tb.get(f"/api/runs/{run_id}/metrics_history")
    assert r.status_code == 200
    body = r.json()
    keys = {m["key"] for m in body}
    assert "train_loss" in keys


def test_log_tail_returns_tail(populated_paths, monkeypatch):
    fold_dir = (populated_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    (fold_dir / "training_log_x.txt").write_text("a\nb\nc\nd\ne\n")
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get("/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/log_tail?bytes=4")
    assert r.status_code == 200
    assert r.text.endswith("e\n") or r.text.endswith("d\ne\n")
