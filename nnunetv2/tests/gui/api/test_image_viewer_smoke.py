from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def test_full_pipeline_smoke(tmp_path, monkeypatch):
    """End-to-end: real NIfTI on disk → /api/datasets/.../cases/.../preview → PNG."""
    raw = tmp_path / "raw"; pre = tmp_path / "pre"; res = tmp_path / "res"
    for p in (raw, pre, res): p.mkdir()

    fixture = Path(__file__).parent.parent / "fixtures" / "data" / "tiny.nii.gz"
    ds = raw / "Dataset100_Tiny"
    (ds / "imagesTr").mkdir(parents=True)
    (ds / "labelsTr").mkdir(parents=True)
    shutil.copy(fixture, ds / "imagesTr" / "case_a_0000.nii.gz")
    shutil.copy(fixture, ds / "labelsTr" / "case_a.nii.gz")
    (ds / "dataset.json").write_text('{"channel_names": {"0": "CT"}, "labels": {"background": 0, "fg": 1}, "numTraining": 1, "file_ending": ".nii.gz"}')

    monkeypatch.setenv("nnUNet_raw", str(raw))
    monkeypatch.setenv("nnUNet_preprocessed", str(pre))
    monkeypatch.setenv("nnUNet_results", str(res))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset100_Tiny/cases")
    assert r.status_code == 200 and len(r.json()) == 1

    r = c.get("/api/datasets/Dataset100_Tiny/cases/case_a/preview?axis=0&slice=4&channel=0")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    r = c.get("/api/datasets/Dataset100_Tiny/cases/case_a/labels?axis=0&slice=4")
    assert r.status_code == 200
