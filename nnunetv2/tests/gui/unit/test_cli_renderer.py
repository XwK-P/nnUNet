from __future__ import annotations

from nnunetv2.gui.services.cli_renderer import (
    PreprocessRequest, TrainRequest, PredictRequest,
    render_preprocess, render_train, render_predict, argv_to_cli_string,
)


def test_render_preprocess_minimal():
    req = PreprocessRequest(dataset_id=27, verify_dataset_integrity=True)
    argv = render_preprocess(req)
    assert argv[0] == "nnUNetv2_plan_and_preprocess"
    assert "-d" in argv and "27" in argv
    assert "--verify_dataset_integrity" in argv


def test_render_preprocess_with_planner():
    req = PreprocessRequest(dataset_id=27, planner="nnUNetPlannerResEncL")
    argv = render_preprocess(req)
    assert "-pl" in argv and "nnUNetPlannerResEncL" in argv


def test_render_preprocess_with_configurations():
    req = PreprocessRequest(dataset_id=27, configurations=["2d", "3d_fullres"])
    argv = render_preprocess(req)
    assert "-c" in argv
    c_idx = argv.index("-c")
    assert argv[c_idx + 1 : c_idx + 3] == ["2d", "3d_fullres"]


def test_render_preprocess_no_pp_and_npfp_and_np():
    req = PreprocessRequest(dataset_id=27, no_pp=True, npfp=4, np=8)
    argv = render_preprocess(req)
    assert "--no_pp" in argv
    assert "-npfp" in argv and "4" in argv
    assert "-np" in argv and "8" in argv


def test_render_train_basic():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0", npz=True)
    argv = render_train(req)
    assert argv == ["nnUNetv2_train", "27", "3d_fullres", "0", "--npz"]


def test_render_train_with_trainer_and_plans():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0",
                       trainer="nnUNetTrainerCustom", plans="nnUNetResEncUNetLPlans")
    argv = render_train(req)
    assert "-tr" in argv and "nnUNetTrainerCustom" in argv
    assert "-p" in argv and "nnUNetResEncUNetLPlans" in argv


def test_render_train_continue_flag():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0", continue_training=True)
    argv = render_train(req)
    assert "--c" in argv


def test_render_train_num_gpus_and_device():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0",
                       num_gpus=4, device="cpu")
    argv = render_train(req)
    assert "-num_gpus" in argv and "4" in argv
    assert "-device" in argv and "cpu" in argv


def test_render_train_val_and_disable_checkpointing():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0",
                       val_only=True, val_best=True, disable_checkpointing=True)
    argv = render_train(req)
    assert "--val" in argv
    assert "--val_best" in argv
    assert "--disable_checkpointing" in argv


def test_render_predict_minimal():
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out", folds=["all"])
    argv = render_predict(req)
    assert argv[0] == "nnUNetv2_predict"
    assert "-i" in argv and "/in" in argv
    assert "-o" in argv and "/out" in argv
    assert "-d" in argv and "27" in argv
    assert "-c" in argv and "3d_fullres" in argv
    assert "-f" in argv and "all" in argv


def test_render_predict_save_probabilities():
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out", folds=["0", "1"],
                          save_probabilities=True, disable_tta=True)
    argv = render_predict(req)
    assert "--save_probabilities" in argv
    assert "--disable_tta" in argv
    # multi-fold: "-f 0 1" — argparse-style
    f_idx = argv.index("-f")
    assert argv[f_idx + 1 : f_idx + 3] == ["0", "1"]


def test_render_predict_checkpoint_and_step_size():
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out",
                          checkpoint="checkpoint_best", step_size=0.25)
    argv = render_predict(req)
    assert "-chk" in argv and "checkpoint_best" in argv
    assert "-step_size" in argv and "0.25" in argv


def test_argv_to_cli_string_quotes_paths():
    s = argv_to_cli_string(["nnUNetv2_predict", "-i", "/a path/with space", "-o", "/o"])
    assert "'/a path/with space'" in s or '"/a path/with space"' in s
