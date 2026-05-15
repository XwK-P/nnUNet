import os

import numpy as np
import pytest

from nnunetv2.training.logging.nnunet_logger import MetaLogger, TensorboardLogger


def _read_events(logdir):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    ea = EventAccumulator(
        str(logdir),
        size_guidance={"scalars": 0, "images": 0, "tensors": 0, "histograms": 0},
    )
    ea.Reload()
    return ea


def test_log_scalar_is_readable(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.log("train_losses", 0.5, step=0)
    logger.log("train_losses", 0.4, step=1)
    logger.close()

    ea = _read_events(tmp_path / "tensorboard")
    events = ea.Scalars("train_losses")
    assert [e.step for e in events] == [0, 1]
    assert pytest.approx([e.value for e in events], rel=1e-5) == [0.5, 0.4]


def test_log_summary_numeric_writes_scalar(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.log_summary("final_val/foreground_dice", 0.85)
    logger.close()

    ea = _read_events(tmp_path / "tensorboard")
    events = ea.Scalars("summary/final_val/foreground_dice")
    assert len(events) == 1
    assert pytest.approx(events[0].value, rel=1e-5) == 0.85


def test_log_images_is_readable(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    img = np.zeros((3, 16, 48), dtype=np.float32)
    img[0, 4:10, 4:10] = 1.0
    logger.log_images("val_samples/sample_0", img, step=10)
    logger.close()

    ea = _read_events(tmp_path / "tensorboard")
    events = ea.Images("val_samples/sample_0")
    assert len(events) == 1
    assert events[0].step == 10


def test_resume_archives_existing_logdir_when_not_resuming(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.log("loss", 1.0, 0)
    logger.close()

    # Second init with resume=False should archive the old directory, not delete it.
    logger2 = TensorboardLogger(str(tmp_path), resume=False)
    logger2.log("loss", 2.0, 0)
    logger2.close()

    archived = list((tmp_path / "tensorboard").glob("old_*"))
    assert len(archived) == 1, "expected archived old/ directory"
    # New event file is in the top-level tensorboard dir
    new_events = [p for p in (tmp_path / "tensorboard").glob("events.out.tfevents.*")]
    assert len(new_events) >= 1


def test_resume_appends_to_same_logdir(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.log("loss", 1.0, 0)
    logger.close()

    logger2 = TensorboardLogger(str(tmp_path), resume=True)
    logger2.log("loss", 2.0, 1)
    logger2.close()

    ea = _read_events(tmp_path / "tensorboard")
    events = ea.Scalars("loss")
    assert sorted(e.step for e in events) == [0, 1]


def test_logdir_override_env(tmp_path, monkeypatch):
    override = tmp_path / "centralized"
    monkeypatch.setenv("nnUNet_tb_logdir", str(override))
    logger = TensorboardLogger(str(tmp_path / "out"), resume=False)
    logger.log("loss", 0.1, 0)
    logger.close()

    # Override directory should contain a single run subdirectory.
    runs = [p for p in override.iterdir() if p.is_dir()]
    assert len(runs) == 1


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses chmod read-only restrictions",
)
def test_unwritable_logdir_raises_in_init(tmp_path, monkeypatch):
    bad = tmp_path / "nope"
    bad.mkdir()
    bad.chmod(0o400)  # read-only
    monkeypatch.setenv("nnUNet_tb_logdir", str(bad))
    try:
        with pytest.raises(Exception):
            TensorboardLogger(str(tmp_path / "out"), resume=False)
    finally:
        bad.chmod(0o700)


def test_log_after_self_disable_is_noop(tmp_path):
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger._disabled = True  # simulate prior failure
    logger.log("loss", 0.5, 0)         # must not raise
    logger.log_images("x", np.zeros((3, 4, 4), dtype=np.float32), 0)
    logger.log_summary("y", 0.1)
    logger.close()


def test_logdir_override_does_not_collide_in_same_second(tmp_path, monkeypatch):
    """Two instantiations within the same wall-clock second must get distinct logdirs."""
    override = tmp_path / "centralized"
    monkeypatch.setenv("nnUNet_tb_logdir", str(override))
    logger_a = TensorboardLogger(str(tmp_path / "out"), resume=False)
    logger_b = TensorboardLogger(str(tmp_path / "out"), resume=False)
    try:
        assert logger_a.logdir != logger_b.logdir, \
            "back-to-back inits must get distinct logdirs (microsecond precision)"
    finally:
        logger_a.close()
        logger_b.close()


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_log_summary_non_finite_is_not_paired_with_hparams(tmp_path, bad_value):
    """NaN/Inf summary values still get logged as scalars but must not corrupt the hparams view."""
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.update_config({"lr": 0.001})
    logger.log_summary("final_val/foreground_dice", bad_value)
    logger.close()

    assert "final_val/foreground_dice" not in logger._summary_metrics, \
        f"non-finite value {bad_value} must not be stored in _summary_metrics"


def test_log_summary_non_finite_preserves_prior_finite_value(tmp_path):
    """A later non-finite update must not evict a previously-stored finite metric."""
    logger = TensorboardLogger(str(tmp_path), resume=False)
    logger.log_summary("final_val/foreground_dice", 0.85)
    logger.log_summary("final_val/foreground_dice", float("nan"))
    logger.close()

    assert logger._summary_metrics["final_val/foreground_dice"] == pytest.approx(0.85)


def test_flatten_for_hparams_coerces_numpy_scalars():
    from nnunetv2.training.logging.nnunet_logger import _flatten_for_hparams
    config = {
        "patch_size": np.int64(128),
        "spacing": np.float32(1.5),
        "nested": {"depth": np.int32(5)},
    }
    flat = _flatten_for_hparams(config)
    assert flat["patch_size"] == 128 and isinstance(flat["patch_size"], int)
    assert flat["spacing"] == pytest.approx(1.5) and isinstance(flat["spacing"], float)
    assert flat["nested.depth"] == 5 and isinstance(flat["nested.depth"], int)
def test_metalogger_registers_tensorboard_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("nnUNet_tensorboard_disabled", raising=False)
    ml = MetaLogger(str(tmp_path), resume=False, local_rank=0)
    try:
        assert any(type(l).__name__ == "TensorboardLogger" for l in ml.loggers)
    finally:
        ml.close()


def test_metalogger_skips_tensorboard_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("nnUNet_tensorboard_disabled", "1")
    ml = MetaLogger(str(tmp_path), resume=False, local_rank=0)
    try:
        assert not any(type(l).__name__ == "TensorboardLogger" for l in ml.loggers)
    finally:
        ml.close()


def test_metalogger_skips_tensorboard_on_nonzero_rank(tmp_path, monkeypatch):
    monkeypatch.delenv("nnUNet_tensorboard_disabled", raising=False)
    ml = MetaLogger(str(tmp_path), resume=False, local_rank=1)
    try:
        assert not any(type(l).__name__ == "TensorboardLogger" for l in ml.loggers)
    finally:
        ml.close()


def test_metalogger_log_images_dispatches_to_tensorboard(tmp_path, monkeypatch):
    monkeypatch.delenv("nnUNet_tensorboard_disabled", raising=False)
    ml = MetaLogger(str(tmp_path), resume=False, local_rank=0)
    img = np.zeros((3, 8, 24), dtype=np.float32)
    ml.log_images("val/x", img, step=5)
    ml.close()

    ea = _read_events(tmp_path / "tensorboard")
    events = ea.Images("val/x")
    assert len(events) == 1 and events[0].step == 5


def test_metalogger_close_is_safe_to_call_twice(tmp_path):
    ml = MetaLogger(str(tmp_path), resume=False, local_rank=0)
    ml.close()
    ml.close()  # must not raise
