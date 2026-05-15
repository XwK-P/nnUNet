import os
from pathlib import Path

import numpy as np
import pytest

from nnunetv2.training.logging.nnunet_logger import TensorboardLogger


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
