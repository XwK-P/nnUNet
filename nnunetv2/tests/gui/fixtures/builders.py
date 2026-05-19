"""Build minimal fake nnUNet directory trees for tests.

Each builder writes a small but valid-shape tree under the given root and
returns the canonical ids it created, so tests can assert against them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def build_dataset_raw(
    raw_root: Path,
    *,
    dataset_id: int,
    name: str,
    case_ids: Iterable[str] = ("case_001", "case_002", "case_003"),
    channels: dict[str, str] | None = None,
    file_ending: str = ".nii.gz",
) -> str:
    """Create a Dataset<XXX>_<Name> directory under raw_root.

    Returns the dataset folder name (e.g. 'Dataset027_ACDC').
    """
    channels = channels or {"0": "CT"}
    folder = f"Dataset{dataset_id:03d}_{name}"
    base = raw_root / folder
    (base / "imagesTr").mkdir(parents=True)
    (base / "labelsTr").mkdir()
    for cid in case_ids:
        for chan_idx in sorted(int(c) for c in channels):
            (base / "imagesTr" / f"{cid}_{chan_idx:04d}{file_ending}").touch()
        (base / "labelsTr" / f"{cid}{file_ending}").touch()
    dataset_json = {
        "channel_names": channels,
        "labels": {"background": 0, "foreground": 1},
        "numTraining": len(list(case_ids)) if not hasattr(case_ids, "__len__") else len(case_ids),
        "file_ending": file_ending,
    }
    (base / "dataset.json").write_text(json.dumps(dataset_json))
    return folder


def build_dataset_preprocessed(
    preprocessed_root: Path,
    *,
    dataset_folder: str,
    fingerprint: dict | None = None,
) -> Path:
    """Mark a dataset as preprocessed by creating its directory + fingerprint."""
    base = preprocessed_root / dataset_folder
    base.mkdir(parents=True, exist_ok=True)
    fp = fingerprint or {
        "spacings": [[1.0, 1.0, 1.0]],
        "foreground_intensity_properties_per_channel": {"0": {"mean": 100.0, "std": 50.0}},
    }
    (base / "dataset_fingerprint.json").write_text(json.dumps(fp))
    return base


def build_run(
    results_root: Path,
    *,
    dataset_folder: str,
    plans_name: str = "nnUNetPlans",
    trainer_name: str = "nnUNetTrainer",
    configuration: str = "3d_fullres",
    fold: str = "0",
    completed: bool = True,
    plans: dict | None = None,
    dataset_json: dict | None = None,
) -> tuple[Path, str]:
    """Create a fold directory with the standard nnUNet output files.

    Returns (fold_path, canonical_run_id).
    """
    base = results_root / dataset_folder / f"{plans_name}__{trainer_name}__{configuration}"
    fold_dir = base / f"fold_{fold}"
    fold_dir.mkdir(parents=True, exist_ok=True)
    (base / "plans.json").write_text(json.dumps(plans or {"plans_name": plans_name, "configurations": {configuration: {}}}))
    (base / "dataset.json").write_text(json.dumps(dataset_json or {"channel_names": {"0": "CT"}, "labels": {"background": 0, "foreground": 1}}))
    if completed:
        (fold_dir / "checkpoint_final.pth").write_bytes(b"")
        (fold_dir / "validation").mkdir(exist_ok=True)
        (fold_dir / "validation" / "summary.json").write_text(json.dumps({"foreground_mean": {"Dice": 0.9}}))
    canonical_id = f"{dataset_folder}/{plans_name}__{trainer_name}__{configuration}/fold_{fold}"
    return fold_dir, canonical_id


def build_case_nifti(folder: Path, name: str, shape: tuple[int, int, int] = (16, 16, 16)) -> Path:
    """Write a tiny synthetic NIfTI under `folder/name`. Returns the file path.

    Uses nibabel to produce a real, openable file with deterministic content
    (a per-voxel index gradient). Roughly 4 KB for shape (16,16,16) float32.
    """
    import numpy as np
    import nibabel as nib
    folder.mkdir(parents=True, exist_ok=True)
    arr = np.arange(int(np.prod(shape)), dtype=np.float32).reshape(shape)
    img = nib.Nifti1Image(arr, affine=np.eye(4))
    path = folder / name
    nib.save(img, str(path))
    return path


def build_run_predictions(
    fold_dir: Path,
    *,
    case_ids: Iterable[str] = ("case_001",),
    use_real_nifti: bool = False,
) -> Path:
    """Create a fold_<n>/predictions/ directory with one .nii.gz per case_id."""
    pred_dir = fold_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        path = pred_dir / f"{cid}.nii.gz"
        if use_real_nifti:
            build_case_nifti(pred_dir, f"{cid}.nii.gz", shape=(8, 16, 16))
        else:
            path.touch()
    return pred_dir


def build_tb_event_dir(
    out: Path,
    *,
    scalars: dict[str, list[tuple[int, float]]]
    | list[tuple[str, list[tuple[int, float]]]]
    | None = None,
) -> Path:
    """Write a minimal TensorBoard event file using torch.utils.tensorboard.SummaryWriter.

    `scalars` may be either a {key: points} dict or an ordered list of
    `(key, points)` tuples (order is preserved when iterating).
    """
    from torch.utils.tensorboard import SummaryWriter
    out.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(log_dir=str(out))
    items: list[tuple[str, list[tuple[int, float]]]]
    if scalars is None:
        items = []
    elif isinstance(scalars, dict):
        items = list(scalars.items())
    else:
        items = list(scalars)
    for key, points in items:
        for step, val in points:
            writer.add_scalar(key, val, global_step=step)
    writer.flush()
    writer.close()
    return out


def build_run_summary(
    fold_dir: Path,
    *,
    foreground_mean_dice: float = 0.9,
    per_case: dict[str, float] | None = None,
) -> Path:
    """Write a validation/summary.json under a fold directory.

    `per_case` maps case_id -> Dice (single-class) for the `metric_per_case` block;
    `foreground_mean_dice` is the overall mean.
    """
    val_dir = fold_dir / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "foreground_mean": {"Dice": foreground_mean_dice},
        "mean": {"1": {"Dice": foreground_mean_dice}},
    }
    if per_case:
        payload["metric_per_case"] = [
            {"reference_file": cid, "metrics": {"1": {"Dice": dice}}}
            for cid, dice in per_case.items()
        ]
    (val_dir / "summary.json").write_text(json.dumps(payload))
    return val_dir / "summary.json"
