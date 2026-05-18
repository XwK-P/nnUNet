from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.datasets import Dataset, list_datasets, get_dataset, upsert_dataset


def _make(id="Dataset027_ACDC", **overrides) -> Dataset:
    d = Dataset(
        id=id, dataset_id_int=27, name="ACDC",
        raw_path="/raw/Dataset027_ACDC",
        preprocessed_path=None,
        last_scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprint_json=None,
        case_count=3, modality_count=1,
    )
    return d.model_copy(update=overrides)


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_datasets(gui_config) == []


def test_upsert_and_get(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make())
    fetched = get_dataset(gui_config, "Dataset027_ACDC")
    assert fetched is not None
    assert fetched.id == "Dataset027_ACDC"
    assert fetched.case_count == 3


def test_upsert_updates_existing(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make())
    upsert_dataset(gui_config, _make(case_count=5))
    fetched = get_dataset(gui_config, "Dataset027_ACDC")
    assert fetched.case_count == 5
    assert len(list_datasets(gui_config)) == 1


def test_list_sorted_by_dataset_id_int(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make(id="Dataset100_X", dataset_id_int=100))
    upsert_dataset(gui_config, _make(id="Dataset027_ACDC", dataset_id_int=27))
    ids = [d.id for d in list_datasets(gui_config)]
    assert ids == ["Dataset027_ACDC", "Dataset100_X"]


def test_get_missing_returns_none(gui_config):
    init_db(gui_config)
    assert get_dataset(gui_config, "Dataset999_Nope") is None
