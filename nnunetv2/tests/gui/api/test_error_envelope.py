from __future__ import annotations

from fastapi.testclient import TestClient


def test_unhandled_exception_returns_error_envelope(app):
    @app.get("/__test_crash__")
    def crash() -> dict:
        raise RuntimeError("synthetic failure for envelope test")

    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/__test_crash__")

    assert r.status_code == 500
    body = r.json()
    assert body["kind"] == "internal_error"
    assert body["retryable"] is False
    assert body["details"] is None
    assert "message" in body
    # loopback default: full str(exc) is exposed for dev convenience
    assert "synthetic failure" in body["message"]


def test_unhandled_exception_hides_message_on_non_loopback(gui_paths):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    cfg = GuiConfig.from_env_and_args(
        host="0.0.0.0",
        port=0,
        token="testtoken",
        raw_override=gui_paths["raw"],
        preprocessed_override=gui_paths["preprocessed"],
        results_override=gui_paths["results"],
    )
    app = create_app(cfg)

    @app.get("/__test_crash__")
    def crash() -> dict:
        raise RuntimeError("secret path /etc/passwd")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/__test_crash__")

    assert r.status_code == 500
    body = r.json()
    assert body["kind"] == "internal_error"
    assert body["message"] == "Internal server error"
    assert "secret path" not in body["message"]
    assert "/etc/passwd" not in body["message"]
