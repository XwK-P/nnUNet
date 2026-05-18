from __future__ import annotations

from nnunetv2.gui.state.discovery import scan_raw_datasets


def test_scan_raw_empty_returns_empty(gui_paths):
    found = scan_raw_datasets(gui_paths["raw"])
    assert found == []


def test_scan_raw_finds_dataset(populated_paths):
    found = scan_raw_datasets(populated_paths["raw"])
    assert len(found) == 1
    d = found[0]
    assert d.id == "Dataset027_ACDC"
    assert d.dataset_id_int == 27
    assert d.name == "ACDC"
    assert d.case_count == 3
    assert d.modality_count == 1
    assert d.raw_path == str(populated_paths["raw"] / "Dataset027_ACDC")


def test_scan_raw_skips_non_dataset_dirs(populated_paths, tmp_path):
    # Create a noise directory that shouldn't be picked up
    (populated_paths["raw"] / "not_a_dataset").mkdir()
    (populated_paths["raw"] / "README.md").write_text("ignore me")

    found = scan_raw_datasets(populated_paths["raw"])
    ids = [d.id for d in found]
    assert ids == ["Dataset027_ACDC"]


def test_scan_raw_handles_multi_modality(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    build_dataset_raw(
        gui_paths["raw"],
        dataset_id=42,
        name="BraTS",
        case_ids=["c1", "c2"],
        channels={"0": "T1", "1": "T1ce", "2": "T2", "3": "FLAIR"},
    )
    found = scan_raw_datasets(gui_paths["raw"])
    assert len(found) == 1
    assert found[0].modality_count == 4
    assert found[0].case_count == 2
