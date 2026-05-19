from __future__ import annotations

from pathlib import Path

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.gui.state.models import (
    Model, ModelFold, Checkpoint, list_models, get_model, list_checkpoints,
)


def _cfg(populated_paths, monkeypatch) -> GuiConfig:
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)
    return cfg


def test_list_models_groups_runs_by_dataset_config(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    models = list_models(cfg)
    # populated_paths fixture builds 3d_fullres and 2d, both on Dataset027_ACDC
    ids = sorted(m.id for m in models)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres",
    ]


def test_model_enumerates_folds(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    build_run(populated_paths["results"], dataset_folder="Dataset027_ACDC",
              configuration="3d_fullres", fold="1", completed=True)
    build_run(populated_paths["results"], dataset_folder="Dataset027_ACDC",
              configuration="3d_fullres", fold="2", completed=False)

    cfg = _cfg(populated_paths, monkeypatch)
    m = get_model(cfg, "Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres")
    assert m is not None
    folds = {f.fold: f.status for f in m.folds}
    assert folds == {"0": "completed", "1": "completed", "2": "abandoned"}


def test_get_unknown_model_returns_none(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    assert get_model(cfg, "Dataset999_X", "p", "t", "c") is None


def test_list_checkpoints_returns_sorted_with_size(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_checkpoint
    cfg = _cfg(populated_paths, monkeypatch)
    fold_dir = (
        Path(cfg.results) / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0"
    )
    # populated_paths already builds checkpoint_final.pth
    build_checkpoint(fold_dir, "checkpoint_best.pth")
    build_checkpoint(fold_dir, "checkpoint_latest.pth")

    out = list_checkpoints(fold_dir)
    names = [c.name for c in out]
    assert set(names) == {"checkpoint_final.pth", "checkpoint_best.pth", "checkpoint_latest.pth"}
    for c in out:
        assert c.size_bytes > 0


def test_list_checkpoints_missing_fold_returns_empty(tmp_path):
    assert list_checkpoints(tmp_path / "nope") == []
