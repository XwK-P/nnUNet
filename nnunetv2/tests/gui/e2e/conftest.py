"""Playwright fixtures: boot nnUNetv2_gui against a synthetic dataset tree.

The whole tier is gated behind an importable ``pytest_playwright``; if the
plugin (and its browsers) are not installed locally, the suite is skipped
at collection time. CI installs them — see ``.github/workflows/gui.yml``.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


# Skip the entire e2e tier when pytest-playwright is unavailable. This lets
# `pytest nnunetv2/tests/gui/` work locally without any browser stack.
pytest.importorskip(
    "pytest_playwright",
    reason="pytest-playwright not installed; run `pip install -e .[gui,gui-e2e]` "
    "then `playwright install chromium` to enable the E2E tier.",
)


from nnunetv2.tests.gui.fixtures.builders import (  # noqa: E402
    build_dataset_raw,
    build_dataset_preprocessed,
    build_run,
    build_minimal_niigz,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError(f"server did not come up at {url} within {timeout}s")


@pytest.fixture(scope="session")
def synthetic_tree(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("nnunet_e2e")
    raw = root / "raw"
    pre = root / "preprocessed"
    res = root / "results"
    for d in (raw, pre, res):
        d.mkdir()

    folder = build_dataset_raw(raw, dataset_id=27, name="E2EDemo")
    # Place real tiny NIfTI files so the Cases tab is meaningful.
    ds_dir = raw / folder
    build_minimal_niigz(ds_dir / "imagesTr" / "case_001_0000.nii.gz", shape=(8, 8, 8))
    build_minimal_niigz(ds_dir / "labelsTr" / "case_001.nii.gz", shape=(8, 8, 8))

    build_dataset_preprocessed(pre, dataset_folder=folder)
    build_run(res, dataset_folder=folder, configuration="3d_fullres", fold="0")

    return {"raw": raw, "preprocessed": pre, "results": res}


@pytest.fixture(scope="session")
def gui_server_subprocess(synthetic_tree) -> str:
    port = _free_port()
    env = os.environ.copy()
    env.update(
        nnUNet_raw=str(synthetic_tree["raw"]),
        nnUNet_preprocessed=str(synthetic_tree["preprocessed"]),
        nnUNet_results=str(synthetic_tree["results"]),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "nnunetv2.gui.cli", "--port", str(port), "--host", "127.0.0.1"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{url}/api/system/healthz")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
