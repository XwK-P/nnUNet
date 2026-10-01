"""Bearer-token enforcement on /api/* paths.

When the GUI is launched with --token, every /api/* request must carry
``Authorization: Bearer <token>`` or fall through to a 401. Without
this, a documented promise in documentation/gui.md was silently false
and non-loopback deployments were fully open to job launching, model
export/import, and arbitrary summary.json reads.

Loopback deployments without --token keep their existing open
behaviour: the operator IS the user there.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.server import create_app


def _client_with_token(populated_paths, monkeypatch, token: str | None) -> TestClient:
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=token)
    return TestClient(create_app(cfg))


def test_no_token_keeps_api_open(populated_paths, monkeypatch):
    client = _client_with_token(populated_paths, monkeypatch, token=None)
    r = client.get("/api/jobs")
    assert r.status_code == 200


def test_token_required_when_configured(populated_paths, monkeypatch):
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/jobs")
    assert r.status_code == 401
    body = r.json()
    assert body.get("kind") == "unauthorized"


def test_wrong_token_rejected(populated_paths, monkeypatch):
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/jobs", headers={"Authorization": "Bearer not-the-token"})
    assert r.status_code == 401


def test_correct_token_accepted(populated_paths, monkeypatch):
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/jobs", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200


def test_healthz_open_even_with_token(populated_paths, monkeypatch):
    """Monitoring probes shouldn't need to know the token to liveness-check."""
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/system/healthz")
    assert r.status_code == 200


def test_non_api_paths_open_for_spa_bootstrap(populated_paths, monkeypatch):
    """The SPA static files must be reachable without a token so the user
    can load the page and enter their token via the UI. If we gated /,
    a token-required deployment would render a blank page.
    """
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    # If web/ isn't built, the placeholder returns 200; either way the
    # route is not behind the auth wall.
    r = client.get("/")
    assert r.status_code == 200


def test_query_token_accepted_for_img_and_sse(populated_paths, monkeypatch):
    """Browsers can't attach Authorization headers to <img src=...> or
    EventSource, so the middleware also accepts ?token=<token>. Without
    this, slice previews and live monitoring would be unreachable on a
    --token deployment.
    """
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/jobs?token=s3cret")
    assert r.status_code == 200


def test_sse_endpoint_requires_token(populated_paths, monkeypatch):
    """SSE lives at /sse/runs/* (not /api/*) — the middleware predicate
    must include /sse/* or live monitoring would be wide open even on
    --token deployments. Use a known-bogus run id so the middleware
    short-circuits with 401 before any stream is opened.
    """
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/sse/runs/does/not/exist/events")
    assert r.status_code == 401


def test_sse_endpoint_accepts_query_token(populated_paths, monkeypatch):
    """EventSource can't add headers, so the SPA tacks ?token= on. The
    middleware must accept that for SSE the same way it does for /api/.
    With a bogus run_id the handler itself 404s; the assertion is just
    "not 401" — auth was honored.
    """
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/sse/runs/does/not/exist/events?token=s3cret")
    assert r.status_code != 401


def test_query_token_wrong_value_rejected(populated_paths, monkeypatch):
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    r = client.get("/api/jobs?token=not-the-token")
    assert r.status_code == 401


def test_malformed_authorization_rejected(populated_paths, monkeypatch):
    """A bare token (no 'Bearer ' prefix) or a different scheme must
    fail — the comparison is exact-string against 'Bearer <token>'.
    """
    client = _client_with_token(populated_paths, monkeypatch, token="s3cret")
    for header in ("s3cret", "Token s3cret", "Bearer", "Bearer  s3cret"):
        r = client.get("/api/jobs", headers={"Authorization": header})
        assert r.status_code == 401, f"header {header!r} should have been rejected"
