from __future__ import annotations


def test_healthz_returns_ok(client):
    r = client.get("/api/system/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_includes_nnunet_and_gui(client):
    from nnunetv2.gui.routers.system import GUI_VERSION

    r = client.get("/api/system/version")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["nnunetv2"], str) and body["nnunetv2"]
    assert body["gui"] == GUI_VERSION


def test_diag_dumps_paths_and_environment(client, gui_config):
    from nnunetv2.gui.routers.system import GUI_VERSION

    r = client.get("/api/system/diag")
    assert r.status_code == 200
    body = r.json()
    assert body["paths"]["raw"] == str(gui_config.raw)
    assert body["paths"]["preprocessed"] == str(gui_config.preprocessed)
    assert body["paths"]["results"] == str(gui_config.results)
    assert body["paths"]["state_db"] == str(gui_config.state_db)
    assert body["host"] == gui_config.host
    assert body["port"] == gui_config.port
    assert body["gui"] == GUI_VERSION
    assert "python" in body
    assert "platform" in body
