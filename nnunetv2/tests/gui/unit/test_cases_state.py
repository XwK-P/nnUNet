from __future__ import annotations

from pathlib import Path

import pytest

from nnunetv2.gui.state.cases import Case, list_cases_for_dataset


def test_list_cases_empty(gui_config):
    assert list_cases_for_dataset(gui_config, "Dataset999_None") == []


def test_list_cases_basic(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    cases = list_cases_for_dataset(cfg, "Dataset027_ACDC")
    assert len(cases) == 3
    case_ids = sorted(c.id for c in cases)
    assert case_ids == ["case_001", "case_002", "case_003"]
    for c in cases:
        assert len(c.channels) == 1
        assert c.label_path is not None


def test_list_cases_attaches_label_for_dotted_case_id(gui_paths, monkeypatch):
    """Case identifiers can legally contain dots (e.g. ``patient.v1``).
    Earlier code matched labels via ``f.name.split('.')[0] == case_id``
    which truncated at the first dot, so the dotted case lost its
    ``label_path`` and /labels returned 404 despite the file existing.
    """
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    build_dataset_raw(
        gui_paths["raw"], dataset_id=43, name="DottedIDs",
        case_ids=["patient.v1", "patient.v2"],
        channels={"0": "CT"},
    )
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    cases = list_cases_for_dataset(cfg, "Dataset043_DottedIDs")
    assert sorted(c.id for c in cases) == ["patient.v1", "patient.v2"]
    for c in cases:
        assert c.label_path is not None, (
            f"label not attached for dotted case id {c.id!r}: "
            "the label file exists in labelsTr/ but the matcher dropped it"
        )
        # The matched label should end with the case id plus the dataset's
        # file ending — never the truncated 'patient' prefix.
        assert Path(c.label_path).name.startswith(c.id + ".")


def test_list_cases_multimodal(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    build_dataset_raw(
        gui_paths["raw"], dataset_id=42, name="BraTS",
        case_ids=["c1", "c2"],
        channels={"0": "T1", "1": "T1ce", "2": "T2", "3": "FLAIR"},
    )
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    cases = list_cases_for_dataset(cfg, "Dataset042_BraTS")
    assert len(cases) == 2
    for c in cases:
        assert len(c.channels) == 4
