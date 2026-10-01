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


def test_scan_preprocessed_marks_dataset(populated_paths):
    from nnunetv2.gui.state.discovery import scan_preprocessed
    pre = scan_preprocessed(populated_paths["preprocessed"])
    assert pre == {"Dataset027_ACDC": str(populated_paths["preprocessed"] / "Dataset027_ACDC")}


def test_scan_preprocessed_empty(gui_paths):
    from nnunetv2.gui.state.discovery import scan_preprocessed
    assert scan_preprocessed(gui_paths["preprocessed"]) == {}


def test_read_fingerprint_returns_dict(populated_paths):
    from nnunetv2.gui.state.discovery import read_fingerprint
    fp = read_fingerprint(populated_paths["preprocessed"] / "Dataset027_ACDC")
    assert "spacings" in fp


def test_read_fingerprint_missing_returns_none(tmp_path):
    from nnunetv2.gui.state.discovery import read_fingerprint
    (tmp_path / "no_fp").mkdir()
    assert read_fingerprint(tmp_path / "no_fp") is None


def test_scan_results_finds_runs(populated_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs
    runs = scan_results_runs(populated_paths["results"])
    assert len(runs) == 2
    ids = sorted(r.id for r in runs)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d/fold_0",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0",
    ]
    for r in runs:
        assert r.dataset_id == "Dataset027_ACDC"
        assert r.plans_name == "nnUNetPlans"
        assert r.trainer_name == "nnUNetTrainer"
        assert r.fold == "0"
        assert r.status == "completed"  # checkpoint_final.pth exists


def test_scan_results_marks_abandoned_when_no_final_checkpoint(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    from nnunetv2.gui.state.discovery import scan_results_runs

    build_run(gui_paths["results"], dataset_folder="Dataset099_X",
              configuration="3d_fullres", fold="2", completed=False)
    runs = scan_results_runs(gui_paths["results"])
    assert len(runs) == 1
    assert runs[0].status == "abandoned"


def test_scan_results_handles_fold_all(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    from nnunetv2.gui.state.discovery import scan_results_runs

    build_run(gui_paths["results"], dataset_folder="Dataset100_Y",
              configuration="3d_fullres", fold="all")
    runs = scan_results_runs(gui_paths["results"])
    assert len(runs) == 1
    assert runs[0].fold == "all"


def test_scan_results_skips_garbage_dirs(populated_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs

    (populated_paths["results"] / "Dataset027_ACDC" / "junk_not_a_run_dir").mkdir()
    (populated_paths["results"] / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "validation_only_no_fold.txt").touch()
    runs = scan_results_runs(populated_paths["results"])
    # Should still be the 2 runs from populated_paths
    assert len(runs) == 2


def test_scan_results_empty(gui_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs
    assert scan_results_runs(gui_paths["results"]) == []


def test_resolve_dataset_folder_finds_name_from_raw(populated_paths):
    from nnunetv2.gui.state.discovery import resolve_dataset_folder
    name = resolve_dataset_folder(
        populated_paths["raw"], populated_paths["preprocessed"],
        populated_paths["results"], 27,
    )
    assert name == "Dataset027_ACDC"


def test_resolve_dataset_folder_falls_back_to_results(gui_paths):
    """If raw/ has no Dataset099 but results/ does (e.g. user has only
    the trained model checked out), resolution still works.
    """
    from nnunetv2.tests.gui.fixtures.builders import build_run
    from nnunetv2.gui.state.discovery import resolve_dataset_folder
    build_run(gui_paths["results"], dataset_folder="Dataset099_OnlyRes",
              configuration="3d_fullres", fold="0")
    name = resolve_dataset_folder(
        gui_paths["raw"], gui_paths["preprocessed"], gui_paths["results"], 99,
    )
    assert name == "Dataset099_OnlyRes"


def test_resolve_dataset_folder_returns_none_when_missing(gui_paths):
    from nnunetv2.gui.state.discovery import resolve_dataset_folder
    name = resolve_dataset_folder(
        gui_paths["raw"], gui_paths["preprocessed"], gui_paths["results"], 999,
    )
    assert name is None
