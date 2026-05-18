from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def gui_paths(tmp_path: Path) -> dict[str, Path]:
    """Three nnUNet root directories rooted under pytest's tmp_path.

    Each test gets a fresh trio. The GUI code never escapes these dirs.
    """
    raw = tmp_path / "raw"
    preprocessed = tmp_path / "preprocessed"
    results = tmp_path / "results"
    for p in (raw, preprocessed, results):
        p.mkdir()
    return {"raw": raw, "preprocessed": preprocessed, "results": results}


@pytest.fixture
def gui_config(gui_paths, monkeypatch):
    """A GuiConfig pointing at the tmp paths, on port 0 (caller-bound), no token."""
    from nnunetv2.gui.config import GuiConfig

    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))

    return GuiConfig.from_env_and_args(
        host="127.0.0.1",
        port=0,
        token=None,
    )


@pytest.fixture
def app(gui_config):
    """A FastAPI app instance built against gui_config — fresh per test."""
    from nnunetv2.gui.server import create_app

    return create_app(gui_config)


@pytest.fixture
def client(app):
    """A FastAPI TestClient bound to the test app."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def populated_paths(gui_paths):
    """Like gui_paths, but with a small fixture tree pre-built.

    Contents: one raw dataset (Dataset027_ACDC, 3 cases, single CT channel) that
    is preprocessed and has two completed runs (3d_fullres fold_0 and 2d fold_0).
    """
    from nnunetv2.tests.gui.fixtures.builders import (
        build_dataset_raw,
        build_dataset_preprocessed,
        build_run,
    )

    folder = build_dataset_raw(gui_paths["raw"], dataset_id=27, name="ACDC")
    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder=folder)
    build_run(gui_paths["results"], dataset_folder=folder, configuration="3d_fullres", fold="0")
    build_run(gui_paths["results"], dataset_folder=folder, configuration="2d", fold="0")
    return gui_paths


@pytest.fixture
def populated_nifti_paths(gui_paths):
    """Like populated_paths but writes real NIfTI bytes for one case."""
    from nnunetv2.tests.gui.fixtures.builders import (
        build_dataset_raw, build_dataset_preprocessed, build_run, build_case_nifti,
    )
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=27, name="ACDC",
                                case_ids=["case_001"])
    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder=folder)
    build_run(gui_paths["results"], dataset_folder=folder, configuration="3d_fullres", fold="0")
    # Replace the empty touched files with real NIfTI
    images_tr = gui_paths["raw"] / folder / "imagesTr"
    labels_tr = gui_paths["raw"] / folder / "labelsTr"
    (images_tr / "case_001_0000.nii.gz").unlink()
    (labels_tr / "case_001.nii.gz").unlink()
    build_case_nifti(images_tr, "case_001_0000.nii.gz", shape=(8, 16, 16))
    build_case_nifti(labels_tr, "case_001.nii.gz", shape=(8, 16, 16))
    return gui_paths
