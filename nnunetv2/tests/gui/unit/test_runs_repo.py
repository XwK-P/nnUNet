from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.runs import (
    Run, RunFilter, canonical_run_id, list_runs, get_run, upsert_run,
)


def _make(**overrides) -> Run:
    base = Run(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0"),
        dataset_id="Dataset027_ACDC",
        plans_name="nnUNetPlans",
        trainer_name="nnUNetTrainer",
        configuration="3d_fullres",
        fold="0",
        output_folder="/results/.../fold_0",
        status="completed",
        source="cli",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        tags_json=None,
        notes=None,
    )
    return base.model_copy(update=overrides)


def test_canonical_run_id_shape():
    assert canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0") == \
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_runs(gui_config, RunFilter()) == []


def test_upsert_and_get(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    fetched = get_run(gui_config, _make().id)
    assert fetched is not None
    assert fetched.configuration == "3d_fullres"


def test_filter_by_dataset_id(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset042_BraTS", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0"),
        dataset_id="Dataset042_BraTS",
    ))
    runs = list_runs(gui_config, RunFilter(dataset_id="Dataset027_ACDC"))
    assert len(runs) == 1
    assert runs[0].dataset_id == "Dataset027_ACDC"


def test_filter_by_status(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "2d", "0"),
        configuration="2d", status="abandoned",
    ))
    completed = list_runs(gui_config, RunFilter(status="completed"))
    abandoned = list_runs(gui_config, RunFilter(status="abandoned"))
    assert len(completed) == 1
    assert len(abandoned) == 1


def test_filter_by_multiple_fields(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "2d", "1"),
        configuration="2d", fold="1",
    ))
    runs = list_runs(gui_config, RunFilter(configuration="3d_fullres", fold="0"))
    assert len(runs) == 1
