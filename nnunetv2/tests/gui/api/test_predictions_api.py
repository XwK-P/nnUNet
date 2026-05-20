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


def test_prediction_preview_png_served_as_is(predictions_client, populated_nifti_paths):
    """A .png prediction is already a 2-D image; the preview must serve
    it verbatim rather than handing the file to the NIfTI loader (which
    would 500 on decode).
    """
    from PIL import Image
    pred_dir = (
        populated_nifti_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
        / "predictions"
    )
    # Drop a real 4x4 PNG with a distinguishable pixel.
    png_path = pred_dir / "case_png.png"
    Image.new("L", (4, 4), color=42).save(str(png_path), format="PNG")
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_png"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Verbatim file bytes — not a re-encoded copy.
    assert r.content == png_path.read_bytes()


def test_prediction_preview_tiff_rendered_as_png(predictions_client, populated_nifti_paths):
    """A .tif/.tiff prediction must be decoded with PIL and re-encoded
    as PNG so it can be displayed; the NIfTI loader would 500.
    """
    from PIL import Image
    pred_dir = (
        populated_nifti_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
        / "predictions"
    )
    tif_path = pred_dir / "case_tif.tif"
    Image.new("L", (8, 4), color=99).save(str(tif_path), format="TIFF")
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_tif?axis=0&slice=0"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Real PNG signature so we know it was actually re-encoded.
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_prediction_preview_unsupported_format_returns_415(
    predictions_client, populated_nifti_paths
):
    """A .nrrd prediction is listed but the viewer has no decoder for it;
    return 415 (instead of a 500 from the NIfTI loader) so the UI can
    show a clear "format not supported" message.
    """
    pred_dir = (
        populated_nifti_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
        / "predictions"
    )
    (pred_dir / "case_nrrd.nrrd").write_bytes(b"NRRD\x00\x00\x00\x00")
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_nrrd"
    )
    assert r.status_code == 415
    assert "supported" in r.json().get("detail", "").lower()


def test_predictions_prefer_nii_gz_over_nii_for_duplicate_stems(
    predictions_client, populated_nifti_paths
):
    """A predictions/ directory can contain both `case_001.nii` and
    `case_001.nii.gz` (e.g. when the user inspects an older run and
    nnUNet was re-run with a different file_ending). The list and
    preview paths must deterministically prefer the compressed file —
    naive lexicographic sort puts `.nii` first, which is the opposite of
    what users expect.
    """
    pred_dir = (
        populated_nifti_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
        / "predictions"
    )
    # Build a real `.nii.gz` (already there from the fixture). Now drop a
    # `.nii` sibling that would sort first lexicographically.
    # The .nii is content-distinct so we could detect leakage if the
    # wrong file were served — but we only need to assert the list
    # surfaces the .nii.gz path.
    sibling = pred_dir / "case_001.nii"
    sibling.write_bytes(b"\x00" * 16)
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == "case_001"
    assert body[0]["path"].endswith(".nii.gz"), (
        f"expected .nii.gz to win over .nii, got {body[0]['path']}"
    )
    # And preview opens the .nii.gz (the .nii is invalid bytes; if the
    # router picked it instead the response would not be a 200 PNG).
    r2 = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_001?axis=0&slice=0"
    )
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"


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
