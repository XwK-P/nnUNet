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


def test_dashboard_empty(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["datasets"] == 0
    assert body["counts"]["preprocessed_datasets"] == 0
    assert body["counts"]["runs"] == 0
    assert body["counts"]["completed_runs"] == 0
    assert body["recent_runs"] == []
    # active_jobs is always present, always empty in Phase 1
    assert body["active_jobs"] == []


def test_dashboard_populated(populated_client):
    r = populated_client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["datasets"] == 1
    assert body["counts"]["preprocessed_datasets"] == 1
    assert body["counts"]["runs"] == 2
    assert body["counts"]["completed_runs"] == 2
    assert len(body["recent_runs"]) == 2
    assert "system" in body
    assert "disk" in body["system"]


def test_dashboard_recent_runs_sorted_newest_first(populated_client):
    r = populated_client.get("/api/dashboard")
    body = r.json()
    seen = [run["last_seen_at"] for run in body["recent_runs"] if run["last_seen_at"]]
    assert seen == sorted(seen, reverse=True)
