from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def metrics_client(populated_paths, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.tests.gui.fixtures.builders import build_inference_summary

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))

    pred_folder = tmp_path / "preds"
    pred_folder.mkdir()
    build_inference_summary(pred_folder,
                            per_case={"case_001": 0.92, "case_002": 0.83},
                            foreground_mean_dice=0.875)

    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None))), pred_folder


def test_per_case_metrics_returns_rows(metrics_client):
    client, pred_folder = metrics_client
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={pred_folder}")
    assert r.status_code == 200
    body = r.json()
    assert body["foreground_mean_dice"] == 0.875
    cases = {c["case_id"]: c["dice"] for c in body["cases"]}
    assert cases == {"case_001": 0.92, "case_002": 0.83}


def test_per_case_metrics_averages_multiclass_dice(populated_paths, monkeypatch, tmp_path):
    """For a multi-class summary.json, per-case Dice must be the mean
    of all non-background label Dices — not the arbitrary first one
    encountered, which would mislead model comparisons for multi-class
    datasets.
    """
    import json
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    pred_folder = tmp_path / "multi"
    pred_folder.mkdir()
    # 3 foreground labels with distinct Dices so a mean (0.4) differs
    # from either the first (0.6) or last (0.1) label's score.
    summary = {
        "foreground_mean": {"Dice": 0.4},
        "metric_per_case": [
            {
                "reference_file": "case_001",
                "metrics": {
                    "0": {"Dice": 0.99},  # background — ignored
                    "1": {"Dice": 0.6},
                    "2": {"Dice": 0.5},
                    "3": {"Dice": 0.1},
                },
            },
        ],
    }
    (pred_folder / "summary.json").write_text(json.dumps(summary))
    client = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={pred_folder}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["cases"]) == 1
    dice = body["cases"][0]["dice"]
    assert dice == pytest.approx((0.6 + 0.5 + 0.1) / 3)


def test_per_case_metrics_missing_summary(client, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={empty}")
    assert r.status_code == 404


def test_per_case_metrics_path_must_exist(client):
    r = client.get("/api/predict/per_case_metrics?prediction_folder=/nope/nope")
    assert r.status_code == 404
