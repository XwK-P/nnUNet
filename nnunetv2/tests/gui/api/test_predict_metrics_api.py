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


def test_per_case_metrics_strips_file_extension_from_case_id(
    populated_paths, monkeypatch, tmp_path
):
    """case_id in the response must be the suffix-stripped stem so the
    Predict page's metrics row → /api/predict/preview round-trip
    resolves. find_prediction_for_case matches against stripped stems,
    so leaving '.nii.gz' on the case_id would 404 every click.
    """
    import json
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    pred_folder = tmp_path / "stem"
    pred_folder.mkdir()
    summary = {
        "foreground_mean": {"Dice": 0.7},
        "metric_per_case": [
            {
                "reference_file": "/somewhere/case_001.nii.gz",
                "metrics": {"0": {"Dice": 0.99}, "1": {"Dice": 0.7}},
            },
        ],
    }
    (pred_folder / "summary.json").write_text(json.dumps(summary))
    client = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={pred_folder}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["cases"]) == 1
    assert body["cases"][0]["case_id"] == "case_001", (
        f"expected stem 'case_001', got {body['cases'][0]['case_id']!r}"
    )


def test_per_case_metrics_skips_nan_dice_in_aggregation(
    populated_paths, monkeypatch, tmp_path
):
    """nnUNet writes NaN for classes absent in a case. The endpoint
    must skip those before averaging so per-case Dice stays finite —
    FastAPI's JSON encoder rejects non-finite floats and would 500
    the whole response otherwise.
    """
    import json
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    pred_folder = tmp_path / "nan"
    pred_folder.mkdir()
    # NaN serialised via json.dumps(allow_nan=True) -> "NaN" literal.
    summary = {
        "foreground_mean": {"Dice": 0.6},
        "metric_per_case": [
            {
                "reference_file": "case_001.nii.gz",
                "metrics": {
                    "0": {"Dice": 0.99},
                    "1": {"Dice": 0.8},
                    "2": {"Dice": float("nan")},  # class absent in this case
                    "3": {"Dice": 0.4},
                },
            },
        ],
    }
    (pred_folder / "summary.json").write_text(json.dumps(summary))
    client = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={pred_folder}")
    assert r.status_code == 200, (
        f"endpoint must not 500 on NaN Dice values; got {r.status_code} {r.text}"
    )
    body = r.json()
    assert len(body["cases"]) == 1
    dice = body["cases"][0]["dice"]
    assert dice is not None
    # Mean of (0.8, 0.4) — NaN class skipped.
    assert dice == pytest.approx(0.6)


def test_per_case_metrics_missing_summary(client, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={empty}")
    assert r.status_code == 404


def test_per_case_metrics_path_must_exist(client):
    r = client.get("/api/predict/per_case_metrics?prediction_folder=/nope/nope")
    assert r.status_code == 404
