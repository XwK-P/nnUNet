from __future__ import annotations


def test_list_datasets_empty(client):
    r = client.get("/api/datasets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_datasets_populated(populated_paths, monkeypatch):
    # Rebuild app pointed at populated_paths
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    app = create_app(cfg)
    c = TestClient(app)

    r = c.get("/api/datasets")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "Dataset027_ACDC"
    assert body[0]["case_count"] == 3


def test_get_dataset_detail(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "Dataset027_ACDC"
    assert body["modality_count"] == 1


def test_get_dataset_not_found(client):
    r = client.get("/api/datasets/Dataset999_NoSuch")
    assert r.status_code == 404


def test_get_dataset_plans(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC/plans")
    assert r.status_code == 200
    body = r.json()
    # populated_paths created runs with default plans.json containing "plans_name"
    assert "plans_name" in body or "configurations" in body


def test_get_dataset_plans_not_found_for_unpreprocessed(client):
    r = client.get("/api/datasets/Dataset027_ACDC/plans")
    assert r.status_code == 404


def test_get_dataset_fingerprint(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC/fingerprint")
    assert r.status_code == 200
    body = r.json()
    assert "spacings" in body
