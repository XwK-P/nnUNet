from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_update_tags_and_notes(populated_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = populated_client.put(f"/api/runs/{rid}",
                              json={"tags": ["baseline", "v1"], "notes": "initial run"})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "initial run"
    # tags_json stored as JSON; surface back as parsed list
    import json
    assert json.loads(body["tags_json"]) == ["baseline", "v1"]


def test_update_partial_keeps_other_fields(populated_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    populated_client.put(f"/api/runs/{rid}", json={"tags": ["t1"]})
    populated_client.put(f"/api/runs/{rid}", json={"notes": "n1"})
    r = populated_client.get(f"/api/runs/{rid}")
    body = r.json()
    import json
    assert json.loads(body["tags_json"]) == ["t1"]
    assert body["notes"] == "n1"


def test_update_unknown_run_returns_404(populated_client):
    r = populated_client.put("/api/runs/Dataset999_X/p__t__c/fold_0",
                              json={"notes": "x"})
    assert r.status_code == 404
