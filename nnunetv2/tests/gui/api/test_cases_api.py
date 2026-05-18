from __future__ import annotations

import pytest


def test_list_cases_for_known_dataset(populated_client):
    r = populated_client.get("/api/datasets/Dataset027_ACDC/cases")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert all("channels" in c for c in body)


def test_list_cases_unknown_dataset(populated_client):
    r = populated_client.get("/api/datasets/Dataset999_None/cases")
    assert r.status_code == 404


def test_list_cases_empty_dataset(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=50, name="Empty", case_ids=[])
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get(f"/api/datasets/{folder}/cases")
    assert r.status_code == 200
    assert r.json() == []


@pytest.fixture
def nifti_client(populated_nifti_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_nifti_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_nifti_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_nifti_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_preview_returns_png(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/preview?axis=0&slice=4&channel=0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_unknown_case(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_999/preview?axis=0&slice=0")
    assert r.status_code == 404


def test_preview_unknown_channel(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/preview?axis=0&slice=0&channel=9")
    assert r.status_code == 404


def test_labels_returns_png(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/labels?axis=0&slice=4")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_labels_for_case_without_label(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw, build_case_nifti
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=60, name="NoLabel",
                                case_ids=["c1"])
    # Remove the label file the builder created
    (gui_paths["raw"] / folder / "labelsTr" / "c1.nii.gz").unlink()
    build_case_nifti(gui_paths["raw"] / folder / "imagesTr", "c1_0000.nii.gz")
    (gui_paths["raw"] / folder / "imagesTr" / "c1_0000.nii.gz").exists()
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get(f"/api/datasets/{folder}/cases/c1/labels?axis=0&slice=0")
    assert r.status_code == 404
