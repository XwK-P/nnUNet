"""POST /api/train — fan a multi-fold request into N queued jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from nnunetv2.gui.config import job_env
from nnunetv2.gui.services.cli_renderer import (
    TrainRequest,
    argv_to_cli_string,
    render_train,
)


class TrainBatchRequest(BaseModel):
    dataset_id: int
    configuration: str
    folds: list[str] = Field(default_factory=lambda: ["0"])
    trainer: Optional[str] = None
    plans: Optional[str] = None
    pretrained_weights: Optional[str] = None
    num_gpus: int = 1
    npz: bool = False
    continue_training: bool = False
    val_only: bool = False
    val_best: bool = False
    disable_checkpointing: bool = False
    device: str = "cuda"


def _per_fold_requests(batch: TrainBatchRequest) -> list[TrainRequest]:
    out: list[TrainRequest] = []
    for f in batch.folds:
        out.append(TrainRequest(
            dataset_id=batch.dataset_id,
            configuration=batch.configuration,
            fold=f,
            trainer=batch.trainer,
            plans=batch.plans,
            pretrained_weights=batch.pretrained_weights,
            num_gpus=batch.num_gpus,
            npz=batch.npz,
            continue_training=batch.continue_training,
            val_only=batch.val_only,
            val_best=batch.val_best,
            disable_checkpointing=batch.disable_checkpointing,
            device=batch.device,
        ))
    return out


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/train", tags=["train"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def enqueue(
        batch: TrainBatchRequest,
        request: Request,
        response: Response,
        dry_run: bool = False,
    ) -> dict:
        per_fold = _per_fold_requests(batch)
        jobs_render = []
        for r in per_fold:
            argv = render_train(r)
            jobs_render.append({"argv": argv, "cli": argv_to_cli_string(argv)})
        if dry_run:
            response.status_code = status.HTTP_200_OK
            return {"jobs": jobs_render}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        plans = batch.plans or "nnUNetPlans"
        trainer = batch.trainer or "nnUNetTrainer"
        job_ids: list[int] = []
        for fold_req, rendered in zip(per_fold, jobs_render):
            output_run_id = (
                f"Dataset{batch.dataset_id:03d}/"
                f"{plans}__{trainer}__{batch.configuration}/fold_{fold_req.fold}"
            )
            log_path = str(
                Path(cfg.results) / ".nnunet_gui" / "logs"
                / f"train_d{batch.dataset_id}_{batch.configuration}_f{fold_req.fold}.log"
            )
            j = await q.enqueue(
                kind="train", argv=rendered["argv"],
                env=job_env(cfg), log_path=log_path,
                output_run_id=output_run_id,
            )
            job_ids.append(j.id)
        return {"job_ids": job_ids, "jobs": jobs_render}

    return router
