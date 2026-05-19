"""Pure functions mapping Pydantic form payloads to argv lists.

These are the *only* place CLI flags are emitted, so the equivalent-CLI
preview shown in the UI is guaranteed identical to what's executed.
"""
from __future__ import annotations

import shlex
from typing import Optional

from pydantic import BaseModel, Field


class PreprocessRequest(BaseModel):
    dataset_id: int
    verify_dataset_integrity: bool = False
    planner: Optional[str] = None
    configurations: Optional[list[str]] = None  # subset of 2d/3d_fullres/3d_lowres
    no_pp: bool = False  # --no_pp
    npfp: Optional[int] = None  # num fingerprint processes
    np: Optional[int] = None    # num preprocess processes


class TrainRequest(BaseModel):
    dataset_id: int
    configuration: str
    fold: str  # '0'..'4' or 'all'
    trainer: Optional[str] = None
    plans: Optional[str] = None
    pretrained_weights: Optional[str] = None
    num_gpus: int = 1
    npz: bool = False
    continue_training: bool = False  # --c
    val_only: bool = False           # --val
    val_best: bool = False           # --val_best
    disable_checkpointing: bool = False
    device: str = "cuda"


class PredictRequest(BaseModel):
    dataset_id: int
    configuration: str
    input_folder: str
    output_folder: str
    folds: list[str] = Field(default_factory=lambda: ["all"])
    trainer: Optional[str] = None
    plans: Optional[str] = None
    checkpoint: str = "checkpoint_final"  # or 'checkpoint_best'
    step_size: float = 0.5
    disable_tta: bool = False
    save_probabilities: bool = False
    continue_prediction: bool = False  # -c
    device: str = "cuda"


def render_preprocess(req: PreprocessRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_plan_and_preprocess", "-d", str(req.dataset_id)]
    if req.verify_dataset_integrity:
        argv.append("--verify_dataset_integrity")
    if req.planner:
        argv += ["-pl", req.planner]
    if req.configurations:
        argv += ["-c", *req.configurations]
    if req.no_pp:
        argv.append("--no_pp")
    if req.npfp is not None:
        argv += ["-npfp", str(req.npfp)]
    if req.np is not None:
        argv += ["-np", str(req.np)]
    return argv


def render_train(req: TrainRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_train", str(req.dataset_id), req.configuration, req.fold]
    if req.trainer:
        argv += ["-tr", req.trainer]
    if req.plans:
        argv += ["-p", req.plans]
    if req.pretrained_weights:
        argv += ["-pretrained_weights", req.pretrained_weights]
    if req.num_gpus > 1:
        argv += ["-num_gpus", str(req.num_gpus)]
    if req.npz:
        argv.append("--npz")
    if req.continue_training:
        argv.append("--c")
    if req.val_only:
        argv.append("--val")
    if req.val_best:
        argv.append("--val_best")
    if req.disable_checkpointing:
        argv.append("--disable_checkpointing")
    if req.device != "cuda":
        argv += ["-device", req.device]
    return argv


def render_predict(req: PredictRequest) -> list[str]:
    argv: list[str] = [
        "nnUNetv2_predict",
        "-i", req.input_folder,
        "-o", req.output_folder,
        "-d", str(req.dataset_id),
        "-c", req.configuration,
        "-f", *req.folds,
    ]
    if req.trainer:
        argv += ["-tr", req.trainer]
    if req.plans:
        argv += ["-p", req.plans]
    if req.checkpoint != "checkpoint_final":
        argv += ["-chk", req.checkpoint]
    if req.step_size != 0.5:
        argv += ["-step_size", str(req.step_size)]
    if req.disable_tta:
        argv.append("--disable_tta")
    if req.save_probabilities:
        argv.append("--save_probabilities")
    if req.continue_prediction:
        argv.append("-c")
    if req.device != "cuda":
        argv += ["-device", req.device]
    return argv


def argv_to_cli_string(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)
