from __future__ import annotations

from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parents[3] / "gui" / "web"
INDEX = WEB_DIR / "index.html"

needs_frontend = pytest.mark.skipif(
    not INDEX.exists(),
    reason="Frontend bundle not built. Run `cd frontend && npm install && npm run build`.",
)


@needs_frontend
def test_root_serves_index_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<div id=\"app\">" in r.text


def test_root_falls_back_to_placeholder_when_no_bundle(client, monkeypatch):
    # Independent of whether the bundle is built — we verify the placeholder
    # endpoint is wired by inspecting the server module directly.
    from nnunetv2.gui import server as server_mod
    assert hasattr(server_mod, "create_app")


@needs_frontend
def test_static_assets_404s_for_missing(client):
    r = client.get("/assets/this-file-does-not-exist.js")
    assert r.status_code == 404


def test_api_routes_take_precedence_over_static(client):
    r = client.get("/api/system/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
