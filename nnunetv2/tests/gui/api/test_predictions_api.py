from __future__ import annotations

import pytest


@pytest.fixture
def predictions_client(populated_nifti_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_run_predictions
    fold_dir = (populated_nifti_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    build_run_predictions(fold_dir, case_ids=["case_001"], use_real_nifti=True)
    monkeypatch.setenv("nnUNet_raw", str(populated_nifti_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_nifti_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_nifti_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_predictions_empty_run(populated_client):
    # No predictions/ dir on fold_0
    r = populated_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    assert r.json() == []


def test_list_predictions_populated(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == "case_001"


def test_prediction_preview(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_001?axis=0&slice=4"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_prediction_preview_unknown_case(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_999?axis=0&slice=0"
    )
    assert r.status_code == 404


def test_predictions_on_unknown_run(client):
    r = client.get("/api/runs/Dataset999_X/x__y__z/fold_0/predictions")
    assert r.status_code == 404


def test_list_predictions_filters_non_segmentation_files(predictions_client, populated_nifti_paths):
    """A predictions/ directory may also contain non-segmentation files
    written alongside a normal predict run — JSON args dumps from
    nnUNet itself, and .npz/.pkl probability companions when the user
    passes --save_probabilities. Listing must skip those so case rows
    aren't duplicated and prediction_preview can't be sent a non-image
    file to decode.
    """
    pred_dir = (
        populated_nifti_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
        / "predictions"
    )
    # Drop the kinds of file nnUNet writes as siblings of the .nii.gz output:
    (pred_dir / "case_001.npz").write_bytes(b"PK\x03\x04")
    (pred_dir / "case_001.pkl").write_bytes(b"\x80\x04")
    (pred_dir / "predict_from_raw_data_args.json").write_text("{}")
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    body = r.json()
    assert [row["case_id"] for row in body] == ["case_001"], (
        f"expected only the segmentation case, got {body}"
    )
    # And the preview lookup still resolves the .nii.gz, not the .npz.
    r2 = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_001?axis=0&slice=4"
    )
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"
