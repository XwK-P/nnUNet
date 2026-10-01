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
    # Renderer .pth-normalizes the checkpoint filename so the CLI can
    # resolve it; see test_render_predict_checkpoint_normalizes_to_pth.
    assert "-chk" in argv and "checkpoint_best.pth" in argv
    assert "-step_size" in argv and "0.25" in argv


def test_render_predict_checkpoint_normalizes_to_pth():
    # nnUNetv2_predict's -chk wants a filename. The form passes the bare
    # stem ("checkpoint_best"); the renderer must append .pth.
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out",
                          checkpoint="checkpoint_best")
    argv = render_predict(req)
    chk_idx = argv.index("-chk")
    assert argv[chk_idx + 1] == "checkpoint_best.pth"


def test_render_predict_checkpoint_passes_through_explicit_pth_suffix():
    # If the caller already supplied the .pth suffix, leave it alone.
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out",
                          checkpoint="checkpoint_best.pth")
    argv = render_predict(req)
    chk_idx = argv.index("-chk")
    assert argv[chk_idx + 1] == "checkpoint_best.pth"


def test_render_predict_skips_chk_for_default_filename_variants():
    # Either "checkpoint_final" or the .pth-suffixed form means "use CLI default".
    for value in ("checkpoint_final", "checkpoint_final.pth"):
        req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                              input_folder="/in", output_folder="/out",
                              checkpoint=value)
        argv = render_predict(req)
        assert "-chk" not in argv, f"should not emit -chk for default value {value!r}"


def test_render_predict_omits_f_when_no_folds():
    # Empty folds (the new default) -> no -f flag, letting nnUNetv2_predict
    # use the documented 5-fold CV ensemble default. Previously the field
    # defaulted to ["all"] which emitted `-f all` and meant "load fold_all
    # specifically" — broken for any model that only has fold_0..fold_4.
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out")
    argv = render_predict(req)
    assert "-f" not in argv, (
        f"-f must not be emitted when no folds are explicitly chosen; argv={argv}"
    )


def test_render_predict_default_folds_is_empty():
    # The Field default itself must be the empty list, not ['all'].
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out")
    assert req.folds == []


def test_render_predict_continue_uses_long_flag():
    # `-c` is the required configuration arg of nnUNetv2_predict, so resume
    # must use the long --continue_prediction flag and never emit a bare -c
    # after the configuration value is already on the line.
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out",
                          continue_prediction=True)
    argv = render_predict(req)
    assert "--continue_prediction" in argv
    # The only -c occurrence is the (configuration) arg, paired with 3d_fullres.
    assert argv.count("-c") == 1
    c_idx = argv.index("-c")
    assert argv[c_idx + 1] == "3d_fullres"


def test_argv_to_cli_string_quotes_paths():
    s = argv_to_cli_string(["nnUNetv2_predict", "-i", "/a path/with space", "-o", "/o"])
    assert "'/a path/with space'" in s or '"/a path/with space"' in s
