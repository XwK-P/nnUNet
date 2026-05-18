from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


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
