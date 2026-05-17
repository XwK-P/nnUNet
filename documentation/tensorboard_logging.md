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
