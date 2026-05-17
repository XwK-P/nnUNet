from __future__ import annotations

import pytest

from nnunetv2.gui.config import GuiConfig


def test_from_env_resolves_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=8765, token=None)

    assert cfg.raw == tmp_path / "raw"
    assert cfg.preprocessed == tmp_path / "pre"
    assert cfg.results == tmp_path / "res"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.token is None


def test_cli_overrides_take_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "env_raw"))
    override = tmp_path / "cli_raw"

    cfg = GuiConfig.from_env_and_args(
        host="127.0.0.1", port=0, token=None,
        raw_override=override,
    )

    assert cfg.raw == override


def test_non_loopback_requires_token(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    with pytest.raises(ValueError, match="--token"):
        GuiConfig.from_env_and_args(host="0.0.0.0", port=8765, token=None)


def test_non_loopback_with_token_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    cfg = GuiConfig.from_env_and_args(host="0.0.0.0", port=8765, token="hexhexhex")

    assert cfg.host == "0.0.0.0"
    assert cfg.token == "hexhexhex"


def test_state_db_under_results(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)

    assert cfg.state_db == tmp_path / "res" / ".nnunet_gui" / "state.db"


def test_missing_required_env_raises(monkeypatch):
    monkeypatch.delenv("nnUNet_raw", raising=False)
    monkeypatch.delenv("nnUNet_preprocessed", raising=False)
    monkeypatch.delenv("nnUNet_results", raising=False)

    with pytest.raises(EnvironmentError, match="nnUNet_results"):
        GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
