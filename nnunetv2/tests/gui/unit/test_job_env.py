"""Tests for job_env — the helper that builds the env for spawned CLIs.

The GUI may be launched with --raw/--preprocessed/--results overrides
that diverge from the process's own nnUNet_* env vars. Spawned child
processes import nnunetv2.paths at startup, which reads those env vars
once and caches them, so they must match GuiConfig before launch.
"""
from __future__ import annotations

import os
from pathlib import Path

from nnunetv2.gui.config import GuiConfig, job_env


def _make_cfg(tmp_path: Path) -> GuiConfig:
    raw = tmp_path / "raw"
    pre = tmp_path / "pre"
    res = tmp_path / "res"
    for p in (raw, pre, res):
        p.mkdir()
    return GuiConfig(
        raw=raw, preprocessed=pre, results=res,
        host="127.0.0.1", port=0, token=None,
    )


def test_job_env_injects_cfg_paths_into_env(tmp_path, monkeypatch):
    """When the GUI was started with paths that diverge from the
    process env, the spawned child must see the GuiConfig paths — not
    the parent's.
    """
    cfg = _make_cfg(tmp_path)
    # Simulate a stale process env: different paths from what the GUI
    # actually resolved.
    monkeypatch.setenv("nnUNet_raw", "/stale/raw")
    monkeypatch.setenv("nnUNet_preprocessed", "/stale/pre")
    monkeypatch.setenv("nnUNet_results", "/stale/res")
    env = job_env(cfg)
    assert env["nnUNet_raw"] == str(cfg.raw)
    assert env["nnUNet_preprocessed"] == str(cfg.preprocessed)
    assert env["nnUNet_results"] == str(cfg.results)
    # And the helper must not mutate os.environ as a side-effect.
    assert os.environ["nnUNet_raw"] == "/stale/raw"


def test_job_env_passes_through_allowlisted_keys(tmp_path, monkeypatch):
    """Process-bootstrap and GPU/threading env vars on JOB_ENV_KEYS pass
    through; everything else (cloud keys, CI tokens, terminal state)
    is dropped so unrelated secrets don't end up in state.db.
    """
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("MY_UNRELATED_VAR", "should-not-leak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "redacted")
    env = job_env(cfg)
    # Allowlisted keys are present.
    assert env["CUDA_VISIBLE_DEVICES"] == "1,2"
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["OMP_NUM_THREADS"] == "8"
    # Non-allowlisted keys (including a deliberately scary one) are gone.
    assert "MY_UNRELATED_VAR" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env


def test_job_env_passes_through_nnunet_prefix(tmp_path, monkeypatch):
    """Any env var starting with ``nnUNet_`` passes through so users
    can tune runtime knobs (tb_logdir, n_proc_DA, etc.) without
    extending the allowlist.
    """
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("nnUNet_tb_image_every_n_epochs", "1")
    monkeypatch.setenv("nnUNet_compile", "0")
    env = job_env(cfg)
    assert env["nnUNet_tb_image_every_n_epochs"] == "1"
    assert env["nnUNet_compile"] == "0"


def test_job_env_sets_paths_even_when_env_missing(tmp_path, monkeypatch):
    """If the parent env never had nnUNet_* set (e.g. the user launched
    nnUNetv2_gui with --raw/--preprocessed/--results overrides and no
    matching shell env), job_env must still inject the GuiConfig paths
    so the child doesn't fail with 'Required env var(s) not set'.
    """
    cfg = _make_cfg(tmp_path)
    monkeypatch.delenv("nnUNet_raw", raising=False)
    monkeypatch.delenv("nnUNet_preprocessed", raising=False)
    monkeypatch.delenv("nnUNet_results", raising=False)
    env = job_env(cfg)
    assert env["nnUNet_raw"] == str(cfg.raw)
    assert env["nnUNet_preprocessed"] == str(cfg.preprocessed)
    assert env["nnUNet_results"] == str(cfg.results)
