"""Folder-scoped /api/predict/preview endpoint.

This mirror of /api/runs/.../predictions/{case_id} lets the Predict
page render side-by-side previews against an arbitrary predictions/
folder (one the user pasted in, not a GUI-managed Run).
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def preview_client(populated_paths, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.tests.gui.fixtures.builders import build_case_nifti

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))

    pred_folder = tmp_path / "preds"
    pred_folder.mkdir()
    # A real .nii.gz so the NIfTI loader actually produces a PNG.
    build_case_nifti(pred_folder, "case_001.nii.gz", shape=(8, 16, 16))

    client = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    return client, pred_folder


def test_preview_returns_png_for_nifti(preview_client):
    client, folder = preview_client
    r = client.get(
        f"/api/predict/preview?prediction_folder={folder}&case_id=case_001&axis=0&slice=4"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_unknown_case_returns_404(preview_client):
    client, folder = preview_client
    r = client.get(
        f"/api/predict/preview?prediction_folder={folder}&case_id=case_999&axis=0&slice=0"
    )
    assert r.status_code == 404


def test_preview_unsupported_format_returns_415(preview_client):
    """A .nrrd file is listed but has no decoder wired up here. The
    endpoint should surface 415 instead of letting the NIfTI loader 500.
    """
    client, folder = preview_client
    (folder / "case_other.nrrd").write_bytes(b"NRRD\x00\x00\x00\x00")
    r = client.get(
        f"/api/predict/preview?prediction_folder={folder}&case_id=case_other"
    )
    assert r.status_code == 415
    assert "supported" in r.json().get("detail", "").lower()


def test_preview_prefers_nii_gz_over_nii(preview_client):
    """If both `case_001.nii` and `case_001.nii.gz` live in the folder,
    the .nii.gz must win (matches the runs-scoped sibling endpoint).
    """
    client, folder = preview_client
    sibling = folder / "case_001.nii"
    sibling.write_bytes(b"\x00" * 16)  # invalid bytes — must not be picked
    r = client.get(
        f"/api/predict/preview?prediction_folder={folder}&case_id=case_001&axis=0&slice=0"
    )
    # If the router had picked the .nii (invalid), decoding would 500.
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
