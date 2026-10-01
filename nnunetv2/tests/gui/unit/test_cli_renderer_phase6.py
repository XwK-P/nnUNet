from __future__ import annotations

from nnunetv2.gui.services.cli_renderer import (
    FindBestConfigRequest, EnsembleRequest, PostprocRequest,
    ExportModelRequest, ImportModelRequest,
    render_find_best, render_ensemble, render_postproc,
    render_export_model, render_import_model,
)


def test_find_best_minimal():
    req = FindBestConfigRequest(dataset_id=27)
    argv = render_find_best(req)
    assert argv[0] == "nnUNetv2_find_best_configuration"
    assert "27" in argv


def test_find_best_with_configs_and_disable_ensembling():
    req = FindBestConfigRequest(
        dataset_id=27, configurations=["2d", "3d_fullres"],
        plans=["nnUNetPlans"], trainers=["nnUNetTrainer"],
        folds=["0", "1", "2", "3", "4"], disable_ensembling=True,
    )
    argv = render_find_best(req)
    assert "-c" in argv and "2d" in argv and "3d_fullres" in argv
    assert "-p" in argv and "nnUNetPlans" in argv
    assert "-tr" in argv and "nnUNetTrainer" in argv
    assert "-f" in argv and argv.count("0") >= 1
    assert "--disable_ensembling" in argv


def test_ensemble_minimal():
    req = EnsembleRequest(input_folders=["/a", "/b"], output_folder="/out")
    argv = render_ensemble(req)
    assert argv[0] == "nnUNetv2_ensemble"
    i_idx = argv.index("-i")
    assert argv[i_idx + 1 : i_idx + 3] == ["/a", "/b"]
    assert "-o" in argv and "/out" in argv


def test_ensemble_save_npz():
    req = EnsembleRequest(input_folders=["/a"], output_folder="/out", save_npz=True)
    argv = render_ensemble(req)
    assert "--save_npz" in argv


def test_postproc_minimal():
    req = PostprocRequest(
        input_folder="/in", output_folder="/out",
        pp_pkl_file="/pp.pkl", plans_json="/plans.json", dataset_json="/dataset.json",
    )
    argv = render_postproc(req)
    assert argv[0] == "nnUNetv2_apply_postprocessing"
    assert argv[argv.index("-i") + 1] == "/in"
    assert argv[argv.index("-o") + 1] == "/out"
    assert argv[argv.index("-pp_pkl_file") + 1] == "/pp.pkl"
    assert argv[argv.index("-plans_json") + 1] == "/plans.json"
    assert argv[argv.index("-dataset_json") + 1] == "/dataset.json"


def test_export_model_minimal():
    req = ExportModelRequest(dataset_id=27, output_zip="/out.zip")
    argv = render_export_model(req)
    assert argv[0] == "nnUNetv2_export_model_to_zip"
    assert argv[argv.index("-d") + 1] == "27"
    assert argv[argv.index("-o") + 1] == "/out.zip"


def test_export_model_with_folds_configs_checkpoints():
    req = ExportModelRequest(
        dataset_id=27, output_zip="/out.zip",
        configurations=["3d_fullres", "2d"], folds=["0", "1"],
        trainer="nnUNetTrainer", plans="nnUNetPlans",
        checkpoints=["checkpoint_final.pth", "checkpoint_best.pth"],
    )
    argv = render_export_model(req)
    assert "-c" in argv and "3d_fullres" in argv and "2d" in argv
    assert "-tr" in argv and "nnUNetTrainer" in argv
    assert "-p" in argv and "nnUNetPlans" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1 : f_idx + 3] == ["0", "1"]
    chk_idx = argv.index("-chk")
    assert argv[chk_idx + 1 : chk_idx + 3] == ["checkpoint_final.pth", "checkpoint_best.pth"]


def test_import_model_minimal():
    req = ImportModelRequest(zip_path="/path/model.zip")
    argv = render_import_model(req)
    assert argv == ["nnUNetv2_install_pretrained_model_from_zip", "/path/model.zip"]
