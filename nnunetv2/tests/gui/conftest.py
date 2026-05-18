from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def gui_paths(tmp_path: Path) -> dict[str, Path]:
    """Three nnUNet root directories rooted under pytest's tmp_path.

    Each test gets a fresh trio. The GUI code never escapes these dirs.
    """
    raw = tmp_path / "raw"
    preprocessed = tmp_path / "preprocessed"
    results = tmp_path / "results"
    for p in (raw, preprocessed, results):
        p.mkdir()
    return {"raw": raw, "preprocessed": preprocessed, "results": results}


@pytest.fixture
def gui_config(gui_paths, monkeypatch):
    """A GuiConfig pointing at the tmp paths, on port 0 (caller-bound), no token."""
    from nnunetv2.gui.config import GuiConfig

    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))

    return GuiConfig.from_env_and_args(
        host="127.0.0.1",
        port=0,
        token=None,
    )


@pytest.fixture
def app(gui_config):
    """A FastAPI app instance built against gui_config — fresh per test."""
    from nnunetv2.gui.server import create_app

    return create_app(gui_config)


@pytest.fixture
def client(app):
    """A FastAPI TestClient bound to the test app."""
    from fastapi.testclient import TestClient

    return TestClient(app)
