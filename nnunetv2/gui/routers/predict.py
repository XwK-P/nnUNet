"""POST /api/predict — render argv, optionally enqueue."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request, Response, status

from nnunetv2.gui.services.cli_renderer import (
    PredictRequest,
    argv_to_cli_string,
    render_predict,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/predict", tags=["predict"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def enqueue(
        req: PredictRequest,
        request: Request,
        response: Response,
        dry_run: bool = False,
    ) -> dict:
        argv = render_predict(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            response.status_code = status.HTTP_200_OK
            return {"argv": argv, "cli": cli}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        log_path = str(
            Path(cfg.results) / ".nnunet_gui" / "logs"
            / f"predict_d{req.dataset_id}_{req.configuration}.log"
        )
        job = await q.enqueue(
            kind="predict", argv=argv, env=os.environ.copy(),
            log_path=log_path,
        )
        return {"job_id": job.id, "argv": argv, "cli": cli}

    return router
