# Comprehensive TensorBoard Logging — Design

**Status:** Draft
**Date:** 2026-05-15
**Author:** Puyang Wang (with Claude)

## Summary

Add first-class TensorBoard logging to nnU-Net training as a `TensorboardLogger` plugin inside the existing `MetaLogger`. TB logging is **on by default** and produces:

- All scalars currently logged to W&B (train/val loss, mean & per-class dice, EMA dice, learning rate, epoch duration)
- Hyperparameters and configuration (plans, fold, dataset, derived hparas) via TensorBoard's `add_hparams` API, paired with the final foreground dice for run comparison
- Periodic image samples from the validation set: input, ground-truth overlay, and prediction overlay rendered as a single side-by-side panel (mid-axial slice for 3D)

The change is intentionally narrow: one new logger class, one new image-utility module, one new ~15-line trainer hook for image sampling, and a documentation page. No CLI changes, no plans-file changes, no new trainer subclass required.

## Goals

- Drop-in TB experience: clone, train, point `tensorboard --logdir` at the output folder, see meaningful curves and images.
- Zero impact on training stability — any logging failure self-disables the logger, never crashes training.
- Reuse the existing `MetaLogger` extension pattern that `WandbLogger` established.
- Keep the trainer interface unchanged for users not interested in TB.

## Non-Goals

- Weight or gradient histograms (deferred; can be added later as another optional capability).
- Animated GIFs of full 3D volumes.
- Replacing or deprecating `WandbLogger`.
- A general "logger config" plans-file section. Env vars are sufficient.
- Multi-modal channel rendering — only channel 0 of the input is shown. Power users override the trainer hook.

## Architecture

### File changes

```
nnunetv2/training/logging/
  nnunet_logger.py            # add TensorboardLogger; auto-register in MetaLogger
  tensorboard_image_utils.py  # NEW: render_sample helper

nnunetv2/training/nnUNetTrainer/
  nnUNetTrainer.py            # add _maybe_log_validation_images() and one
                              # call site at the end of on_validation_epoch_end

pyproject.toml                # add `tensorboard` to dependencies

documentation/
  tensorboard_logging.md      # NEW: env vars, viewing logs, customization

nnunetv2/tests/logging/
  test_tensorboard_logger.py  # NEW: unit tests
  test_tensorboard_image_utils.py  # NEW: unit tests
nnunetv2/tests/integration_tests/
  run_integration_test.sh     # extend with TB-output assertions
```

### How it slots into `MetaLogger`

`MetaLogger` already supports a list of plugin loggers and a privileged `LocalLogger`. The `WandbLogger` is conditionally appended via `_is_logger_enabled("nnUNet_wandb_enabled")`. The TB logger uses the same pattern but inverts the gate (default-on, opt-out via `nnUNet_tensorboard_disabled=1`).

Two small `MetaLogger` API changes are required:

1. **Add `local_rank` parameter to `MetaLogger.__init__`** so the logger can avoid spawning rank-1+ TB writers under DDP. The trainer already computes `self.local_rank` (lines 95–96 of `nnUNetTrainer.py`) before constructing the logger, so the call site becomes `MetaLogger(self.output_folder, continue_training, local_rank=self.local_rank)`.
2. **Add a `_is_logger_disabled(env_var)` helper.** Same parsing as `_is_logger_enabled`, but the default and semantics are inverted — unset or `"0"` means "not disabled" (i.e., the logger should run).

```python
# In MetaLogger.__init__, after wandb registration:
if self.local_rank == 0 and not self._is_logger_disabled("nnUNet_tensorboard_disabled"):
    try:
        self.loggers.append(TensorboardLogger(output_folder, resume))
    except Exception as e:
        print(f"[TensorboardLogger] failed to initialize, skipping: {e}")
```

`MetaLogger` gains a new dispatch method `log_images(tag, image, step)` that forwards to any logger implementing `log_images` (currently only `TensorboardLogger`).

### `TensorboardLogger` interface

Mirrors `WandbLogger`'s public surface so `MetaLogger` can dispatch without special-casing:

```python
class TensorboardLogger:
    def __init__(self, output_folder: str, resume: bool): ...
    def update_config(self, config: dict): ...
    def log(self, key: str, value, step: int): ...
    def log_summary(self, key: str, value): ...
    def log_images(self, tag: str, image_chw: np.ndarray, step: int): ...
    def close(self): ...
```

Internal state:

- `self.writer: SummaryWriter`
- `self._hparams: dict[str, int|float|str|bool]` — accumulated and flushed in `close()`
- `self._summary_metrics: dict[str, float]` — paired with hparams in `close()`
- `self._disabled: bool` — flipped to `True` after any failure; subsequent calls are no-ops

### Trainer hook

In `nnUNetTrainer.on_validation_epoch_end`, after existing scalar logging:

```python
def _maybe_log_validation_images(self):
    every_n = _parse_int_env("nnUNet_tb_image_every_n_epochs", default=50, minimum=0)
    if every_n == 0 or self.current_epoch % every_n != 0:
        return
    if self.local_rank != 0:
        return
    num_samples = _parse_int_env("nnUNet_tb_image_num_samples", default=4, minimum=1)
    try:
        self.network.eval()
        with torch.no_grad():
            batch = next(self.dataloader_val)
            data = batch['data'][:num_samples].to(self.device, non_blocking=True)
            target = batch['target'][0] if isinstance(batch['target'], list) else batch['target']
            target = target[:num_samples]
            pred = self.network(data)
            pred = pred[0] if isinstance(pred, (list, tuple)) else pred
            pred_seg = pred.argmax(1).cpu().numpy()
        for i in range(min(num_samples, data.shape[0])):
            img = render_sample(
                data[i].cpu().numpy(),
                target[i].cpu().numpy(),
                pred_seg[i],
            )
            self.logger.log_images(f"val_samples/sample_{i}", img, self.current_epoch)
    except Exception as e:
        self.print_to_log_file(f"[TB image logging] skipped this epoch: {e}")
    finally:
        self.network.train()
```

The hook lives in the base `nnUNetTrainer` so all existing variants inherit it for free.

### Image rendering (`tensorboard_image_utils.render_sample`)

Signature: `render_sample(data, target, pred) -> np.ndarray  # (3, H, 3*W) float32 in [0, 1]`

Steps:

1. Pick channel 0 of `data`.
2. If `data.ndim == 3` (2D config: `C, H, W`), use as-is. If `data.ndim == 4` (3D: `C, D, H, W`), take central axial slice `data[0, D//2, :, :]`. Mirror axis indexing for `target` and `pred`.
3. If `target.ndim` indicates region-based multi-channel labels, collapse to a label map via `argmax` over channels.
4. Min-max normalize the input slice to `[0, 1]`.
5. Convert grayscale to RGB (replicate channel).
6. Apply `matplotlib`'s `tab10` categorical colormap to label/pred. Background label `0` stays transparent (alpha 0).
7. Alpha-blend overlays at 0.4.
8. Concatenate `[input | input+GT | input+pred]` horizontally → return shape `(3, H, 3*W)`.

Edge cases handled inside `render_sample`:

- Empty GT / pred (all zeros) → renders the input panel without overlay; no crash.
- Single-channel binary labels work with the same categorical colormap.
- Integer dtypes for label/pred → cast to int.

## Configuration surface

All controls are environment variables. No new CLI flags, no plans-file fields, no trainer-API changes.

| Env var | Default | Effect |
|---|---|---|
| `nnUNet_tensorboard_disabled` | `0` | Set to `1` to skip registering `TensorboardLogger`. |
| `nnUNet_tb_logdir` | unset | When set, runs go to `<value>/<dataset>__<config>__fold<X>__<timestamp>/` instead of `<output_folder>/tensorboard/`. Use this for centralized aggregation. |
| `nnUNet_tb_image_every_n_epochs` | `50` | Cadence for image-sample logging. `0` disables image logging entirely (scalars + hparams still flow). |
| `nnUNet_tb_image_num_samples` | `4` | Number of validation samples per image-logging epoch. Capped at the actual validation batch size. |

Bad values fall back to defaults with a one-line warning. No exceptions propagate.

## Behavior details

### Scalar logging

- `MetaLogger.log` already splits list values (per-class dice) into `key/class_i` before calling plugin loggers. `TensorboardLogger.log` therefore only ever sees scalars — it routes them to `writer.add_scalar(key, float(value), step)`.
- Non-numeric values (timestamps are numeric, so this is rare) are coerced via `float()`; `TypeError` triggers the self-disable path for that single call only.

### Hparams logging

- `update_config(config)` is called from the trainer at init and after preprocessing details are known. The TB logger flattens nested dicts with dotted keys (e.g., `plans.configurations.3d_fullres.patch_size`), coerces values to TB-compatible scalars (`int|float|str|bool`), and `repr()`s anything else.
- `log_summary("final_val/foreground_dice", value)` is also captured into `self._summary_metrics`.
- `close()` calls `writer.add_hparams(self._hparams, self._summary_metrics)` if both are non-empty, which populates TB's hparams tab with a row per run.

### Image logging

- Lives entirely in the trainer hook; the logger just forwards bytes.
- Default cadence (every 50 epochs, 4 samples) keeps overhead well under 1% of epoch time on a typical 1000-epoch nnU-Net schedule.

### Logdir layout

Default: `<output_folder>/tensorboard/` — sibling to the existing `wandb/` dir. View with `tensorboard --logdir <output_folder>/tensorboard`.

With `nnUNet_tb_logdir` set: `<nnUNet_tb_logdir>/<dataset>__<config>__fold<X>__<timestamp>/`. View aggregated runs with `tensorboard --logdir $nnUNet_tb_logdir`.

## Resume, DDP, error handling

### Resume

- `continue_training=True`: reopen the same `tensorboard/` directory. `SummaryWriter` appends a new event file in the same dir; TB merges them at view time, so the timeline is continuous. First post-resume `log` call uses `step=current_epoch` (the loaded checkpoint's epoch), which matches the last pre-resume entry.
- `continue_training=False` with an existing logdir: move it to `tensorboard/old_<timestamp>/` rather than delete (less destructive than wandb's behavior). Documented in the user doc.
- Hparams are re-accumulated from `update_config()` calls during trainer init (called the same way on resume), so the final `add_hparams()` still has the full config.

### DDP

- `MetaLogger.__init__` receives `local_rank` from the trainer and only instantiates `TensorboardLogger` when `local_rank == 0`. On other ranks, the plugin is not appended; `log` calls become no-ops.
- The image-logging hook early-returns on non-zero ranks. The forward pass it runs happens only on rank 0, which is fine because it's a single-batch eval, not a sync barrier.

### Error handling philosophy

Training comes first. Every public method on `TensorboardLogger` is wrapped in `try/except Exception`. On first failure: print a one-line warning prefixed `[TensorboardLogger]`, set `self._disabled = True`, return. All subsequent calls are no-ops. Concretely covered:

- `tensorboard` package missing despite being a hard dep → import guard at top of `nnunet_logger.py` (mirrors the wandb pattern), MetaLogger logs a warning and skips registration.
- Disk full / write failure → first failed `add_scalar` self-disables the logger.
- `nnUNet_tb_logdir` unwritable → `__init__` raises, `MetaLogger` catches and logs, never adds the plugin.
- Validation batch shape unexpected (custom dataloader) → `render_sample` raises, the trainer hook's own `try/except` catches it, scalar logging is unaffected.
- `close()` failure on training end → `try/except` around the call, no impact on the saved checkpoints.

## Testing

### Unit tests — `nnunetv2/tests/logging/test_tensorboard_logger.py`

- Scalar logging: `log("loss", 0.5, step=3)` produces a readable scalar event with the right tag, value, and step (use `tbparse` or the lightweight TF-free event reader).
- Hparams: after `update_config({...})` and `log_summary("final_val/foreground_dice", 0.8)` and `close()`, the events file contains an hparams record with the flattened keys and the metric.
- Image logging: `log_images("val/x", np.zeros((3, 16, 48), dtype=np.float32), 0)` produces an image event with shape `(3, 16, 48)`.
- Failure mode: instantiate with an unwritable logdir, assert no exceptions propagate, subsequent `log` is a no-op.
- Disable env: `nnUNet_tensorboard_disabled=1` → `MetaLogger` does not register the plugin (verify via `len(logger.loggers)`).

### Unit tests — `nnunetv2/tests/logging/test_tensorboard_image_utils.py`

- 2D input shape `(C, H, W)` → output shape `(3, H, 3*W)`.
- 3D input shape `(C, D, H, W)` → output shape `(3, H, 3*W)` from mid-axial slice.
- Region-based target (multi-channel) → handled via argmax, no crash.
- All-background GT/pred → renders the input panel without overlay.
- Output dtype `float32`, values within `[0, 1]`.

### Integration test — extend `nnunetv2/tests/integration_tests/run_integration_test.sh`

After the existing Hippocampus 2-epoch training, with `nnUNet_tb_image_every_n_epochs=1` exported, assert:

- `tensorboard/` exists under the trainer output folder
- At least one event file is present and non-empty

Keep it cheap — no event-file parsing, just existence and size.

### Manual smoke test (documented, not automated)

Run one full Hippocampus fold, point `tensorboard --logdir` at the output, eyeball that scalars / hparams / images render correctly.

## Documentation

New `documentation/tensorboard_logging.md`:

- TB is on by default; logs land in `<output_folder>/tensorboard/`.
- How to view: `tensorboard --logdir <output_folder>/tensorboard`.
- The four env vars in this spec, each with a one-line example.
- How to aggregate runs: set `nnUNet_tb_logdir` and `tensorboard --logdir $nnUNet_tb_logdir`.
- How to disable: `nnUNet_tensorboard_disabled=1`.
- One paragraph on subclassing the trainer to customize image logging (override `_maybe_log_validation_images`).

The main README's "Common commands" / "Training" section gets a single line linking to the new doc.

## Out of scope / explicit non-decisions

- **Weight/gradient histograms.** Easy to add later by extending the trainer hook and `TensorboardLogger.log_histogram`. Not in this scope.
- **Multi-modal rendering.** Only channel 0 is shown. Multi-modal users override the hook in a subclass.
- **TB profile traces.** Out of scope.
- **Plans-file logger config block.** Not warranted; env vars cover everything.

## Open questions

None remaining at design time. To revisit during implementation:

- Whether to take the event-reader dependency on `tbparse` for tests vs. the heavier `tensorflow` summary iterator. Default to `tbparse` if it's lightweight; otherwise vendor a minimal protobuf reader.
