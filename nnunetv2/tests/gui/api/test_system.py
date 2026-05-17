from __future__ import annotations


def test_healthz_returns_ok(client):
    r = client.get("/api/system/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_includes_nnunet_and_gui(client):
    r = client.get("/api/system/version")
    assert r.status_code == 200
    body = r.json()
    assert "nnunetv2" in body
    assert "gui" in body
    assert body["gui"] == "0.1.0"


def test_diag_dumps_paths_and_environment(client, gui_config):
    r = client.get("/api/system/diag")
    assert r.status_code == 200
    body = r.json()
    assert body["paths"]["raw"] == str(gui_config.raw)
    assert body["paths"]["preprocessed"] == str(gui_config.preprocessed)
    assert body["paths"]["results"] == str(gui_config.results)
    assert body["host"] == gui_config.host
    assert "python" in body
    assert "platform" in body
