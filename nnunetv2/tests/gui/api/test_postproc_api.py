from __future__ import annotations

import pytest


@pytest.fixture
def postproc_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_postproc_dry_run(postproc_client):
    r = postproc_client.post("/api/postproc/apply?dry_run=true", json={
        "input_folder": "/preds",
        "output_folder": "/preds_pp",
        "pp_pkl_file": "/pp.pkl",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_apply_postprocessing"
    assert body["argv"][body["argv"].index("-i") + 1] == "/preds"
    assert body["argv"][body["argv"].index("-o") + 1] == "/preds_pp"


def test_postproc_enqueue(postproc_client):
    r = postproc_client.post("/api/postproc/apply", json={
        "input_folder": "/preds",
        "output_folder": "/preds_pp",
        "pp_pkl_file": "/pp.pkl",
    })
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_postproc_validation_error(postproc_client):
    r = postproc_client.post("/api/postproc/apply", json={"input_folder": "/x"})
    assert r.status_code == 422
