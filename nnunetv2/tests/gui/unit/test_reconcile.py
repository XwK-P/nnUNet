from __future__ import annotations

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.gui.state.datasets import list_datasets, get_dataset
from nnunetv2.gui.state.runs import list_runs, RunFilter


def test_reconcile_empty(gui_config):
    init_db(gui_config)
    reconcile(gui_config)
    assert list_datasets(gui_config) == []
    assert list_runs(gui_config, RunFilter()) == []


def test_reconcile_populates(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)

    datasets = list_datasets(cfg)
    assert len(datasets) == 1
    assert datasets[0].id == "Dataset027_ACDC"
    assert datasets[0].preprocessed_path is not None
    assert datasets[0].fingerprint_json is not None

    runs = list_runs(cfg, RunFilter())
    assert len(runs) == 2


def test_reconcile_is_idempotent(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)

    reconcile(cfg)
    reconcile(cfg)

    assert len(list_datasets(cfg)) == 1
    assert len(list_runs(cfg, RunFilter())) == 2


def test_reconcile_updates_dataset_preprocessed_path(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw, build_dataset_preprocessed
    build_dataset_raw(gui_paths["raw"], dataset_id=99, name="X")
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)

    reconcile(cfg)
    ds = get_dataset(cfg, "Dataset099_X")
    assert ds.preprocessed_path is None

    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder="Dataset099_X")
    reconcile(cfg)
    ds = get_dataset(cfg, "Dataset099_X")
    assert ds.preprocessed_path is not None
    assert ds.fingerprint_json is not None
