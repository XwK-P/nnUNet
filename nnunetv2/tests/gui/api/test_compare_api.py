from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def compare_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.tests.gui.fixtures.builders import (
        build_tb_event_dir, build_run_summary,
    )

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)

    # Add a tensorboard dir + summary on one of the populated runs
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / rid
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0), (1, 0.5)]),
                 ("val_loss",   [(0, 1.1), (1, 0.6)])],
    )
    build_run_summary(fold_dir, foreground_mean_dice=0.88)

    app = create_app(cfg)
    return TestClient(app)


def test_compare_empty_run_ids_returns_empty_payload(compare_client):
    r = compare_client.get("/api/compare")
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"] == []
    assert body["summaries"] == []


def test_compare_single_run(compare_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["metrics"]) == 1
    assert body["metrics"][0]["run_id"] == rid
    assert "train_loss" in body["metrics"][0]["series"]
    assert len(body["summaries"]) == 1
    assert body["summaries"][0]["foreground_mean_dice"] == 0.88


def test_compare_filter_metric_keys(compare_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid}&metric_keys=train_loss")
    body = r.json()
    series = body["metrics"][0]["series"]
    assert set(series.keys()) == {"train_loss"}


def test_compare_multiple_run_ids_preserves_order(compare_client):
    rid1 = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    rid2 = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid1}&run_ids={rid2}")
    body = r.json()
    assert [m["run_id"] for m in body["metrics"]] == [rid1, rid2]
    assert [s["run_id"] for s in body["summaries"]] == [rid1, rid2]


def test_compare_unknown_run_returns_placeholder(compare_client):
    rid = "Dataset999_X/p__t__c/fold_3"
    r = compare_client.get(f"/api/compare?run_ids={rid}")
    body = r.json()
    assert body["metrics"][0]["series"] == {}
    assert body["summaries"][0]["status"] == "unknown"
