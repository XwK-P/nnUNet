from __future__ import annotations

import pytest

from nnunetv2.gui.cli import build_parser, _make_app_from_args


def test_parser_accepts_defaults():
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.token is None
    assert args.open is False


def test_parser_accepts_overrides():
    args = build_parser().parse_args(
        ["--host", "0.0.0.0", "--port", "9000", "--token", "hex"]
    )
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.token == "hex"


def test_make_app_from_args_returns_a_fastapi_instance(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    args = build_parser().parse_args(["--port", "0"])
    app = _make_app_from_args(args)

    assert app.title == "nnU-Net GUI"


def test_make_app_rejects_non_loopback_without_token(monkeypatch, tmp_path):
    monkeypatch.setenv("nnUNet_raw", str(tmp_path / "raw"))
    monkeypatch.setenv("nnUNet_preprocessed", str(tmp_path / "pre"))
    monkeypatch.setenv("nnUNet_results", str(tmp_path / "res"))

    args = build_parser().parse_args(["--host", "0.0.0.0", "--port", "0"])
    with pytest.raises(ValueError, match="--token"):
        _make_app_from_args(args)
