from __future__ import annotations

from pathlib import Path

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.compare import (
    RunMetrics, RunSummary,
    gather_run_metrics, gather_run_summaries,
)
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.tests.gui.fixtures.builders import (
    build_run, build_tb_event_dir, build_run_summary,
)


def _cfg(populated_paths, monkeypatch) -> GuiConfig:
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)
    return cfg


def test_gather_metrics_empty_when_no_event_files(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    out = gather_run_metrics(cfg, [run_id])
    assert len(out) == 1
    assert out[0].run_id == run_id
    assert out[0].series == {}  # no events written yet


def test_gather_metrics_reads_tb_events(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0), (1, 0.7), (2, 0.4)]),
                 ("val_loss",   [(0, 1.2), (1, 0.8), (2, 0.5)])],
    )
    out = gather_run_metrics(cfg, [run_id])
    assert len(out) == 1
    rm = out[0]
    assert set(rm.series) >= {"train_loss", "val_loss"}
    assert len(rm.series["train_loss"]) == 3
    pt = rm.series["train_loss"][0]
    assert pt.step == 0 and pt.value == 1.0


def test_gather_metrics_unknown_run_returns_empty_series(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    out = gather_run_metrics(cfg, ["Dataset999_X/p__t__c/fold_0"])
    assert len(out) == 1
    assert out[0].series == {}


def test_gather_metrics_filters_by_keys(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0)]),
                 ("val_loss", [(0, 1.0)]),
                 ("mean_fg_dice", [(0, 0.5)])],
    )
    out = gather_run_metrics(cfg, [run_id], metric_keys=["train_loss", "mean_fg_dice"])
    assert set(out[0].series.keys()) == {"train_loss", "mean_fg_dice"}


def test_gather_summaries_reads_validation_summary(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_run_summary(fold_dir, foreground_mean_dice=0.87)

    out = gather_run_summaries(cfg, [run_id])
    assert len(out) == 1
    s = out[0]
    assert isinstance(s, RunSummary)
    assert s.run_id == run_id
    assert s.foreground_mean_dice == 0.87
    assert s.dataset_id == "Dataset027_ACDC"
    assert s.configuration == "3d_fullres"
    assert s.fold == "0"
    assert s.status == "completed"


def test_gather_summaries_missing_summary_returns_none_fields(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    # populated_paths' build_run writes a placeholder summary.json; remove it
    # so we exercise the "no summary on disk" branch of gather_run_summaries.
    fold_dir = Path(cfg.results) / run_id
    summary_path = fold_dir / "validation" / "summary.json"
    if summary_path.is_file():
        summary_path.unlink()
    out = gather_run_summaries(cfg, [run_id])
    assert len(out) == 1
    assert out[0].foreground_mean_dice is None
