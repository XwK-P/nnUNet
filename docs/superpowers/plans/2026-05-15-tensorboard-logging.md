# TensorBoard Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add comprehensive TensorBoard logging (scalars, hparams, periodic validation image samples) as a default-on plugin in `MetaLogger`, mirroring the existing `WandbLogger` pattern.

**Architecture:** New `TensorboardLogger` class in `nnunet_logger.py` registered unconditionally by `MetaLogger` (rank 0 only) with an env-var opt-out. A small `tensorboard_image_utils.render_sample` helper produces `(3, H, 3*W)` panels (input | input+GT | input+pred) from 2D or 3D nnU-Net batches. The trainer gets one new method `_maybe_log_validation_images` invoked at the end of `on_validation_epoch_end`, plus a single `self.logger.close()` call in `on_train_end`. All failure modes self-disable the logger; training never crashes from logging.

**Tech Stack:** Python 3.10+, PyTorch (`torch.utils.tensorboard.SummaryWriter`), `tensorboard` package (used both for writing and for reading events back in tests via `tensorboard.backend.event_processing.event_accumulator.EventAccumulator`), matplotlib (for categorical colormap), numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-05-15-tensorboard-logging-design.md`

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add `tensorboard` to runtime dependencies |
| `nnunetv2/training/logging/tensorboard_image_utils.py` | Create | Pure rendering helpers (no torch, no nnU-Net imports beyond numpy/matplotlib) |
| `nnunetv2/training/logging/nnunet_logger.py` | Modify | Add `TensorboardLogger` class; add `_is_logger_disabled` helper, `local_rank` param, `log_images`, and `close` to `MetaLogger`; register TB plugin |
| `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py` | Modify | Pass `local_rank` to `MetaLogger`; add `_maybe_log_validation_images`; call it from `on_validation_epoch_end`; call `self.logger.close()` in `on_train_end` |
| `nnunetv2/tests/logging/__init__.py` | Create | Empty package marker |
| `nnunetv2/tests/logging/test_tensorboard_image_utils.py` | Create | Unit tests for `render_sample` |
| `nnunetv2/tests/logging/test_tensorboard_logger.py` | Create | Unit tests for `TensorboardLogger` and `MetaLogger` integration |
| `nnunetv2/tests/integration_tests/run_integration_test.sh` | Modify | Export `nnUNet_tb_image_every_n_epochs=1`; assert TB output exists after first training |
| `documentation/tensorboard_logging.md` | Create | User-facing usage doc |
| `readme.md` | Modify | Add one-line link to the new doc |

---

## Task 1: Add `tensorboard` dependency and create test scaffold

**Files:**
- Modify: `pyproject.toml` (dependencies list, currently lines ~32–57)
- Create: `nnunetv2/tests/logging/__init__.py`

- [ ] **Step 1: Add `tensorboard` to runtime dependencies**

Edit `pyproject.toml`. Find the `dependencies = [ ... ]` block and add `"tensorboard"` as a new line, alphabetically grouped near the other unversioned entries. The block should now contain (showing a few existing lines for context):

```toml
    "scikit-image>=0.19.3",
    "SimpleITK>=2.2.1",
    "pandas",
    "graphviz",
    'tifffile',
    'requests',
    "nibabel",
    "matplotlib",
    "seaborn",
    "imagecodecs",
    "yacs",
    "batchgeneratorsv2>=0.3.2",
    "einops",
    "blosc2>=3.3.2",
    "tensorboard"
]
```

- [ ] **Step 2: Reinstall the package so the new dependency is available**

Run: `pip install -e .`
Expected: installs without error; `python -c "from torch.utils.tensorboard import SummaryWriter; from tensorboard.backend.event_processing.event_accumulator import EventAccumulator; print('ok')"` prints `ok`.

- [ ] **Step 3: Create test package marker**

Create `nnunetv2/tests/logging/__init__.py` as an empty file.

- [ ] **Step 4: Verify pytest can collect from the new directory**

Run: `pytest nnunetv2/tests/logging/ --collect-only`
Expected: exits 0, "no tests ran" (we haven't written any yet) — confirms collection works.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml nnunetv2/tests/logging/__init__.py
git commit -m "Add tensorboard dependency and test package for TB logger"
```

---

## Task 2: Image rendering helper — `render_sample`

**Files:**
- Create: `nnunetv2/training/logging/tensorboard_image_utils.py`
- Create: `nnunetv2/tests/logging/test_tensorboard_image_utils.py`

- [ ] **Step 1: Write the failing tests**

Create `nnunetv2/tests/logging/test_tensorboard_image_utils.py`:

```python
import numpy as np
import pytest

from nnunetv2.training.logging.tensorboard_image_utils import render_sample


def test_render_sample_2d_shape_and_range():
    data = np.random.randn(1, 16, 24).astype(np.float32)  # C, H, W
    target = np.zeros((16, 24), dtype=np.int64)
    target[4:10, 6:14] = 1
    pred = np.zeros((16, 24), dtype=np.int64)
    pred[5:11, 7:15] = 1

    out = render_sample(data, target, pred)

    assert out.shape == (3, 16, 24 * 3), f"unexpected shape {out.shape}"
    assert out.dtype == np.float32
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_render_sample_3d_uses_mid_axial_slice():
    data = np.random.randn(1, 8, 16, 24).astype(np.float32)  # C, D, H, W
    target = np.zeros((8, 16, 24), dtype=np.int64)
    target[4, 4:10, 6:14] = 1  # only mid slice has GT
    pred = np.zeros((8, 16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)

    assert out.shape == (3, 16, 24 * 3)
    assert out.dtype == np.float32


def test_render_sample_region_based_target_collapsed_via_argmax():
    data = np.random.randn(1, 16, 24).astype(np.float32)
    # Region-based: target is (num_regions, H, W) one-hot-ish
    target = np.zeros((3, 16, 24), dtype=np.float32)
    target[1, 4:10, 6:14] = 1.0
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)


def test_render_sample_all_background_is_safe():
    data = np.random.randn(1, 16, 24).astype(np.float32)
    target = np.zeros((16, 24), dtype=np.int64)
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)
    # GT and pred panels should equal the input panel exactly when no overlay
    left = out[:, :, :24]
    mid = out[:, :, 24:48]
    right = out[:, :, 48:]
    np.testing.assert_allclose(mid, left)
    np.testing.assert_allclose(right, left)


def test_render_sample_constant_input_does_not_divide_by_zero():
    data = np.zeros((1, 16, 24), dtype=np.float32)
    target = np.zeros((16, 24), dtype=np.int64)
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)
    assert np.isfinite(out).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_image_utils.py -v`
Expected: all five tests FAIL with `ModuleNotFoundError: No module named 'nnunetv2.training.logging.tensorboard_image_utils'`.

- [ ] **Step 3: Implement `render_sample`**

Create `nnunetv2/training/logging/tensorboard_image_utils.py`:

```python
"""Helpers for rendering nnU-Net validation samples for TensorBoard logging.

Pure numpy/matplotlib — no torch or nnU-Net imports. Produces a single
``(3, H, 3*W)`` float32 array in [0, 1] containing
``[input | input + GT overlay | input + pred overlay]``.
"""
from __future__ import annotations

import numpy as np
from matplotlib import cm

_OVERLAY_ALPHA = 0.4
_COLORMAP = cm.get_cmap("tab10")


def _to_label_map(arr: np.ndarray, spatial_ndim: int) -> np.ndarray:
    """Collapse a region-based multi-channel target to a single-channel label map."""
    if arr.ndim == spatial_ndim + 1:
        return np.argmax(arr, axis=0).astype(np.int64)
    return arr.astype(np.int64)


def _mid_axial(arr: np.ndarray) -> np.ndarray:
    """Return the central depth slice of a 3D array. No-op for 2D."""
    if arr.ndim == 3:  # D, H, W
        return arr[arr.shape[0] // 2]
    return arr


def _normalize_to_unit(slice_2d: np.ndarray) -> np.ndarray:
    lo = float(slice_2d.min())
    hi = float(slice_2d.max())
    if hi - lo < 1e-8:
        return np.zeros_like(slice_2d, dtype=np.float32)
    return ((slice_2d - lo) / (hi - lo)).astype(np.float32)


def _grayscale_to_rgb(slice_2d: np.ndarray) -> np.ndarray:
    """Convert (H, W) -> (3, H, W)."""
    return np.stack([slice_2d, slice_2d, slice_2d], axis=0)


def _overlay(rgb_chw: np.ndarray, label_map: np.ndarray) -> np.ndarray:
    """Alpha-blend a categorical color overlay onto an RGB image. Background label 0 is transparent."""
    out = rgb_chw.copy()
    unique_labels = np.unique(label_map)
    for lbl in unique_labels:
        if lbl == 0:
            continue
        color = np.array(_COLORMAP(int(lbl) % 10)[:3], dtype=np.float32)  # (3,)
        mask = (label_map == lbl)
        for c in range(3):
            out[c][mask] = (1 - _OVERLAY_ALPHA) * out[c][mask] + _OVERLAY_ALPHA * color[c]
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def render_sample(data: np.ndarray, target: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """Render a single sample as a 3-panel (input | GT | pred) image.

    Args:
        data: Input volume/image, shape ``(C, H, W)`` for 2D or ``(C, D, H, W)`` for 3D.
              Only channel 0 is rendered.
        target: Ground truth labels. Either ``(H, W)`` / ``(D, H, W)`` integer label map,
                or a region-based one-hot-like array with an extra leading channel dim.
        pred: Predicted label map, same shape conventions as ``target`` (without channel dim).

    Returns:
        ``(3, H, 3*W)`` float32 array in [0, 1].
    """
    # Pick channel 0 of input.
    data_ch0 = data[0]  # (H, W) or (D, H, W)
    spatial_ndim = data_ch0.ndim  # 2 or 3

    target_lm = _to_label_map(target, spatial_ndim)
    pred_lm = _to_label_map(pred, spatial_ndim)

    data_slice = _mid_axial(data_ch0)
    target_slice = _mid_axial(target_lm)
    pred_slice = _mid_axial(pred_lm)

    base = _normalize_to_unit(data_slice)            # (H, W)
    base_rgb = _grayscale_to_rgb(base)               # (3, H, W)
    gt_rgb = _overlay(base_rgb, target_slice)        # (3, H, W)
    pred_rgb = _overlay(base_rgb, pred_slice)        # (3, H, W)

    panel = np.concatenate([base_rgb, gt_rgb, pred_rgb], axis=2)  # (3, H, 3*W)
    return panel.astype(np.float32)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_image_utils.py -v`
Expected: all five tests PASS.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/training/logging/tensorboard_image_utils.py nnunetv2/tests/logging/test_tensorboard_image_utils.py
git commit -m "Add render_sample helper for TB validation image panels"
```

---

## Task 3: `TensorboardLogger` — scalars, summary, image, close

**Files:**
- Modify: `nnunetv2/training/logging/nnunet_logger.py` (add new class at end of file)
- Create: `nnunetv2/tests/logging/test_tensorboard_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `nnunetv2/tests/logging/test_tensorboard_logger.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_logger.py -v`
Expected: all tests FAIL with `ImportError: cannot import name 'TensorboardLogger'`.

- [ ] **Step 3: Implement the class**

Open `nnunetv2/training/logging/nnunet_logger.py`. At the top, add (just after the existing `try: import wandb` block):

```python
try:
    from torch.utils.tensorboard import SummaryWriter
except ImportError:
    SummaryWriter = None

from datetime import datetime as _datetime
import shutil as _shutil
```

Then append a new class at the end of the file:

```python
class TensorboardLogger:
    """TensorBoard logger for nnU-Net training runs.

    Default logdir: ``<output_folder>/tensorboard/``.
    Override with env var ``nnUNet_tb_logdir`` for centralized aggregation;
    when set, runs go to ``<value>/<basename(output_folder)>__<timestamp>/``.

    Any exception during logging self-disables the logger for the rest of
    the run; training is never interrupted by TB failures.
    """

    def __init__(self, output_folder, resume):
        if SummaryWriter is None:
            raise RuntimeError(
                "tensorboard is not installed. Install it with `pip install tensorboard`."
            )

        self.output_folder = Path(output_folder)
        self.resume = resume
        self._disabled = False
        self._hparams: dict = {}
        self._summary_metrics: dict = {}

        override = os.getenv("nnUNet_tb_logdir")
        if override:
            run_name = f"{self.output_folder.name}__{_datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.logdir = Path(override) / run_name
        else:
            self.logdir = self.output_folder / "tensorboard"

        # If not resuming and a previous logdir exists, archive (don't delete) it.
        if not self.resume and self.logdir.exists() and any(self.logdir.iterdir()):
            archive_name = f"old_{_datetime.now().strftime('%Y%m%d_%H%M%S')}"
            archive_path = self.logdir / archive_name
            archive_path.mkdir(parents=True, exist_ok=True)
            for entry in list(self.logdir.iterdir()):
                if entry.name.startswith("old_"):
                    continue
                _shutil.move(str(entry), str(archive_path / entry.name))

        self.logdir.mkdir(parents=True, exist_ok=True)
        self.writer = SummaryWriter(log_dir=str(self.logdir))

    def update_config(self, config: dict):
        if self._disabled:
            return
        try:
            self._hparams.update(_flatten_for_hparams(config))
        except Exception as e:
            self._fail(f"update_config failed: {e}")

    def log(self, key: str, value, step: int):
        if self._disabled:
            return
        try:
            self.writer.add_scalar(key, float(value), step)
        except Exception as e:
            self._fail(f"log scalar {key} failed: {e}")

    def log_summary(self, key: str, value):
        if self._disabled:
            return
        try:
            numeric = float(value)
            self.writer.add_scalar(f"summary/{key}", numeric)
            self._summary_metrics[key] = numeric
        except (TypeError, ValueError):
            try:
                self.writer.add_text(f"summary/{key}", str(value))
            except Exception as e:
                self._fail(f"log_summary text {key} failed: {e}")
        except Exception as e:
            self._fail(f"log_summary {key} failed: {e}")

    def log_images(self, tag: str, image_chw, step: int):
        if self._disabled:
            return
        try:
            self.writer.add_image(tag, image_chw, step, dataformats="CHW")
        except Exception as e:
            self._fail(f"log_images {tag} failed: {e}")

    def close(self):
        if self._disabled:
            try:
                self.writer.close()
            except Exception:
                pass
            return
        try:
            if self._hparams and self._summary_metrics:
                self.writer.add_hparams(self._hparams, self._summary_metrics)
            self.writer.flush()
            self.writer.close()
        except Exception as e:
            self._fail(f"close failed: {e}")

    def _fail(self, message: str):
        print(f"[TensorboardLogger] {message}; disabling for rest of run")
        self._disabled = True


def _flatten_for_hparams(config: dict, prefix: str = "") -> dict:
    """Flatten nested dicts to dotted keys; coerce values to TB-compatible scalars."""
    flat: dict = {}
    for k, v in config.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            flat.update(_flatten_for_hparams(v, key))
        elif isinstance(v, (int, float, str, bool)):
            flat[key] = v
        elif v is None:
            flat[key] = "None"
        else:
            flat[key] = repr(v)
    return flat
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_logger.py -v`
Expected: all eight tests PASS. If `test_unwritable_logdir_raises_in_init` skips on your platform (some CI runners ignore chmod for the owner), that's acceptable — note it but proceed.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/training/logging/nnunet_logger.py nnunetv2/tests/logging/test_tensorboard_logger.py
git commit -m "Add TensorboardLogger with scalars, summary, images, hparams"
```

---

## Task 4: `MetaLogger` integration — `local_rank`, `_is_logger_disabled`, register TB, dispatch `log_images` and `close`

**Files:**
- Modify: `nnunetv2/training/logging/nnunet_logger.py` (`MetaLogger` class)
- Modify: `nnunetv2/tests/logging/test_tensorboard_logger.py` (add MetaLogger tests)

- [ ] **Step 1: Write the failing tests**

Append to `nnunetv2/tests/logging/test_tensorboard_logger.py`:

```python
from nnunetv2.training.logging.nnunet_logger import MetaLogger


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_logger.py -v -k metalogger`
Expected: all five new tests FAIL — either `TypeError: __init__() got an unexpected keyword argument 'local_rank'`, missing `log_images`, or missing `close`.

- [ ] **Step 3: Modify `MetaLogger`**

In `nnunetv2/training/logging/nnunet_logger.py`, replace the existing `MetaLogger.__init__` and add new methods. The new `__init__` looks like:

```python
    def __init__(self, output_folder, resume, verbose: bool = False, local_rank: int = 0):
        """Initialize the meta logger.

        Args:
            output_folder: The output folder.
            resume: Whether to resume training if possible.
            verbose: Whether to enable verbose logging in the local logger.
            local_rank: DDP local rank. Plugin loggers (W&B, TB) only run on rank 0.
        """
        self.output_folder = output_folder
        self.resume = resume
        self.local_rank = local_rank
        self.loggers = []
        self.local_logger = LocalLogger(verbose)
        if local_rank == 0 and self._is_logger_enabled("nnUNet_wandb_enabled"):
            self.loggers.append(WandbLogger(output_folder, resume))
        if local_rank == 0 and not self._is_logger_disabled("nnUNet_tensorboard_disabled"):
            try:
                self.loggers.append(TensorboardLogger(output_folder, resume))
            except Exception as e:
                print(f"[MetaLogger] failed to initialize TensorboardLogger, skipping: {e}")
```

Add the helper next to `_is_logger_enabled`:

```python
    def _is_logger_disabled(self, env_var):
        env_var_result = str(os.getenv(env_var, "0"))
        if env_var_result in ("0", "False", "false"):
            return False
        elif env_var_result in ("1", "True", "true"):
            return True
        else:
            raise RuntimeError(
                "nnU-Net logger environment variable has the wrong value. "
                "Must be '0' (not disabled / run) or '1' (disabled / skip)."
            )
```

Add two new methods on `MetaLogger`:

```python
    def log_images(self, tag: str, image, step: int):
        """Forward an image to any plugin logger that supports it."""
        for logger in self.loggers:
            if hasattr(logger, "log_images"):
                logger.log_images(tag, image, step)

    def close(self):
        """Close any plugin loggers that support it. Idempotent."""
        for logger in self.loggers:
            if hasattr(logger, "close"):
                try:
                    logger.close()
                except Exception as e:
                    print(f"[MetaLogger] close failed for {type(logger).__name__}: {e}")
        # Drop references so a second close() is a no-op.
        self.loggers = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest nnunetv2/tests/logging/test_tensorboard_logger.py -v`
Expected: all tests PASS (the previously passing TensorboardLogger tests AND the five new MetaLogger tests).

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/training/logging/nnunet_logger.py nnunetv2/tests/logging/test_tensorboard_logger.py
git commit -m "Wire TensorboardLogger into MetaLogger with rank-aware dispatch"
```

---

## Task 5: Trainer — pass `local_rank` to `MetaLogger`

**Files:**
- Modify: `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py` (line 182)

- [ ] **Step 1: Update the construction call**

Open `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py`. Find this line (around line 182):

```python
        self.logger = MetaLogger(self.output_folder, continue_training)
```

Replace with:

```python
        self.logger = MetaLogger(self.output_folder, continue_training, local_rank=self.local_rank)
```

`self.local_rank` is already initialized at line 96, before this call site.

- [ ] **Step 2: Run a quick sanity import**

Run: `python -c "from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py
git commit -m "Pass local_rank to MetaLogger from nnUNetTrainer"
```

---

## Task 6: Trainer — `_maybe_log_validation_images` hook + call site

**Files:**
- Modify: `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py` (`on_validation_epoch_end` ~line 1133, plus a new method)

- [ ] **Step 1: Add the import for `render_sample`**

Near the top of `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py`, with the other intra-package imports, add:

```python
from nnunetv2.training.logging.tensorboard_image_utils import render_sample
```

- [ ] **Step 2: Add the helper method on the trainer**

Add this method to the `nnUNetTrainer` class (a good location is right after `on_validation_epoch_end`, before `on_epoch_start`):

```python
    def _maybe_log_validation_images(self):
        """Periodically log a small batch of validation samples to TB-style loggers."""
        if self.local_rank != 0:
            return
        every_n = self._parse_int_env("nnUNet_tb_image_every_n_epochs", default=50, minimum=0)
        if every_n == 0 or self.current_epoch % every_n != 0:
            return
        num_samples = self._parse_int_env("nnUNet_tb_image_num_samples", default=4, minimum=1)
        try:
            self.network.eval()
            with torch.no_grad():
                batch = next(self.dataloader_val)
                data = batch['data'][:num_samples].to(self.device, non_blocking=True)
                target = batch['target'][0] if isinstance(batch['target'], list) else batch['target']
                target = target[:num_samples]
                output = self.network(data)
                output = output[0] if isinstance(output, (list, tuple)) else output
                pred_seg = output.argmax(1).cpu().numpy()
                data_np = data.cpu().numpy()
                target_np = target.detach().cpu().numpy() if hasattr(target, 'detach') else np.asarray(target)
            n = min(num_samples, data_np.shape[0])
            for i in range(n):
                img = render_sample(data_np[i], target_np[i], pred_seg[i])
                self.logger.log_images(f"val_samples/sample_{i}", img, self.current_epoch)
        except Exception as e:
            self.print_to_log_file(f"[TB image logging] skipped this epoch: {e}")
        finally:
            self.network.train()

    @staticmethod
    def _parse_int_env(name: str, default: int, minimum: int = 0) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"[nnUNetTrainer] env {name}={raw!r} is not an int, using default {default}")
            return default
        if value < minimum:
            print(f"[nnUNetTrainer] env {name}={value} below minimum {minimum}, using default {default}")
            return default
        return value
```

- [ ] **Step 3: Wire the hook into `on_validation_epoch_end`**

Open `on_validation_epoch_end` (around line 1133). The current body ends with:

```python
        self.logger.log('mean_fg_dice', mean_fg_dice, self.current_epoch)
        self.logger.log('dice_per_class_or_region', global_dc_per_class, self.current_epoch)
        self.logger.log('val_losses', loss_here, self.current_epoch)
```

Add one line after the last `self.logger.log(...)` call:

```python
        self._maybe_log_validation_images()
```

- [ ] **Step 4: Sanity import**

Run: `python -c "from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py
git commit -m "Periodically log validation image samples to TB"
```

---

## Task 7: Trainer — close logger in `on_train_end`

**Files:**
- Modify: `nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py` (`on_train_end` ~line 983)

- [ ] **Step 1: Add the close call**

Find the end of `on_train_end` (the `self.print_to_log_file("Training done.")` line at ~line 1007). Insert immediately before that line:

```python
        try:
            self.logger.close()
        except Exception as e:
            self.print_to_log_file(f"[MetaLogger] close raised, ignoring: {e}")
```

- [ ] **Step 2: Sanity import**

Run: `python -c "from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py
git commit -m "Close MetaLogger at end of training"
```

---

## Task 8: Integration test — assert TB output exists

**Files:**
- Modify: `nnunetv2/tests/integration_tests/run_integration_test.sh`

- [ ] **Step 1: Inspect current script**

Run: `cat nnunetv2/tests/integration_tests/run_integration_test.sh`
Expected: a sequence of `nnUNetv2_train` invocations followed by a Python call.

- [ ] **Step 2: Add env export and post-train assertion**

At the very top of the script (line 1, before any `nnUNetv2_train` call), insert:

```bash
#!/usr/bin/env bash
set -e
export nnUNet_tb_image_every_n_epochs=1
```

(If the script already has a shebang or `set -e`, keep them and just add the `export` line.)

After the FIRST `nnUNetv2_train` invocation (the `3d_fullres 0` line), add this assertion block:

```bash
TB_DIR=$(find "$nnUNet_results" -type d -name "tensorboard" | head -n 1)
if [ -z "$TB_DIR" ]; then
    echo "FAIL: no tensorboard/ directory found under \$nnUNet_results"
    exit 1
fi
EVENT_FILE=$(find "$TB_DIR" -maxdepth 1 -name "events.out.tfevents.*" | head -n 1)
if [ -z "$EVENT_FILE" ] || [ ! -s "$EVENT_FILE" ]; then
    echo "FAIL: no non-empty TB event file under $TB_DIR"
    exit 1
fi
echo "OK: TB event file present at $EVENT_FILE"
```

- [ ] **Step 3: Verify shell syntax**

Run: `bash -n nnunetv2/tests/integration_tests/run_integration_test.sh`
Expected: exits 0 (no syntax errors). Do NOT run the full integration test here; it requires a GPU and downloaded data.

- [ ] **Step 4: Commit**

```bash
git add nnunetv2/tests/integration_tests/run_integration_test.sh
git commit -m "Assert TB event file is produced during integration test"
```

---

## Task 9: User documentation

**Files:**
- Create: `documentation/tensorboard_logging.md`
- Modify: `readme.md` (add a one-line link)

- [ ] **Step 1: Write the doc**

Create `documentation/tensorboard_logging.md` with this content:

```markdown
# TensorBoard Logging

nnU-Net writes TensorBoard event files for every training run by default. This includes:

- All scalars: train/val loss, mean & per-class dice, EMA dice, learning rate, epoch duration.
- The full plans and trainer config as hyperparameters, paired with the final foreground dice in TensorBoard's HParams view (so you can compare runs).
- Periodic image samples from the validation set (input | ground-truth overlay | prediction overlay), every 50 epochs by default.

## Where logs live

By default, events are written to `<trainer_output_folder>/tensorboard/`. View a single run with:

```bash
tensorboard --logdir <trainer_output_folder>/tensorboard
```

To centralize multiple runs under one parent directory (recommended for comparing experiments):

```bash
export nnUNet_tb_logdir=/path/to/runs
nnUNetv2_train ...
tensorboard --logdir $nnUNet_tb_logdir
```

Each run is then written to `<nnUNet_tb_logdir>/<output_basename>__<timestamp>/`.

## Resuming

When training resumes (`continue_training=True`), the existing `tensorboard/` directory is reused; TensorBoard merges event files at view time. Starting fresh with an existing logdir present moves the old contents into `tensorboard/old_<timestamp>/` rather than deleting them.

## Configuration (env vars)

| Variable | Default | Effect |
|---|---|---|
| `nnUNet_tensorboard_disabled` | `0` | Set to `1` to disable TensorBoard logging entirely. |
| `nnUNet_tb_logdir` | unset | Centralized parent directory for runs (see above). |
| `nnUNet_tb_image_every_n_epochs` | `50` | Cadence for image-sample logging. `0` disables image logging (scalars + hparams still flow). |
| `nnUNet_tb_image_num_samples` | `4` | Number of validation samples per image-logging epoch. Capped at the validation batch size. |

## Customizing image logging

The default rendering shows the central axial slice of channel 0 with the GT and prediction overlaid in distinct colors. For multi-modal rendering, custom slice selection, or animated GIFs, override `_maybe_log_validation_images` in a `nnUNetTrainer` subclass:

```python
from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer

class MyTrainer(nnUNetTrainer):
    def _maybe_log_validation_images(self):
        # your custom logging here
        ...
```

## DDP

Only the rank-0 process opens a TB writer. Other ranks treat all logging as no-ops, so there is no synchronization overhead and no duplicate events.

## Failure handling

If any TB write fails (disk full, corrupt event file, etc.), the logger prints a single warning to stdout, disables itself for the rest of the run, and lets training continue. A logging failure will never crash a training job.
```

- [ ] **Step 2: Add a link from the main README**

Open `readme.md`. Search for an existing section that lists supplementary docs (often near "How to use", "Documentation", or near the `documentation/` references). Add this line wherever the surrounding pattern matches:

```markdown
- [TensorBoard logging](documentation/tensorboard_logging.md)
```

If no docs list exists in `readme.md`, instead add this line at the end of the "How to use nnU-Net" or top-level usage section:

```markdown
TensorBoard logs are produced for every run by default — see [TensorBoard logging](documentation/tensorboard_logging.md) for env vars and viewer instructions.
```

- [ ] **Step 3: Commit**

```bash
git add documentation/tensorboard_logging.md readme.md
git commit -m "Document TensorBoard logging usage and configuration"
```

---

## Task 10: Final verification

- [ ] **Step 1: Run the full unit test suite for the new code**

Run: `pytest nnunetv2/tests/logging/ -v`
Expected: all tests in `test_tensorboard_image_utils.py` and `test_tensorboard_logger.py` pass.

- [ ] **Step 2: Smoke import the trainer**

Run: `python -c "from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Run any pre-existing tests to confirm no regression**

Run: `pytest nnunetv2/tests/ -v --ignore=nnunetv2/tests/integration_tests`
Expected: all tests pass (or have the same pre-existing pass/skip pattern as before this branch).

- [ ] **Step 4: Manual smoke check (optional, requires data)**

If a Hippocampus dataset is available locally:

```bash
export nnUNet_tb_image_every_n_epochs=1
nnUNetv2_train 4 3d_fullres 0 -tr nnUNetTrainer_5epochs
tensorboard --logdir $nnUNet_results/Dataset004_Hippocampus/nnUNetTrainer_5epochs__nnUNetPlans__3d_fullres/fold_0/tensorboard
```

Visually confirm: loss / dice / lr scalars present, `val_samples/*` images present, `summary/*` and the HParams tab populated after training completes.

- [ ] **Step 5: Final commit (only if step 1–3 surfaced fixups)**

If anything needed fixing, commit with a clear message describing the fix. Otherwise this step is a no-op.
