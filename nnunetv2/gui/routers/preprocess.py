"""POST /api/preprocess — render argv, optionally enqueue."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response, status

from nnunetv2.gui.config import job_env
from nnunetv2.gui.services.cli_renderer import (
    PreprocessRequest,
    argv_to_cli_string,
    render_preprocess,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/preprocess", tags=["preprocess"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def enqueue(
        req: PreprocessRequest,
        request: Request,
        response: Response,
        dry_run: bool = False,
    ) -> dict:
        argv = render_preprocess(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            response.status_code = status.HTTP_200_OK
            return {"argv": argv, "cli": cli}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        log_path = str(
            Path(cfg.results) / ".nnunet_gui" / "logs"
            / f"preprocess_d{req.dataset_id}.log"
        )
        job = await q.enqueue(
            kind="preprocess", argv=argv, env=job_env(cfg),
            log_path=log_path,
        )
        return {"job_id": job.id, "argv": argv, "cli": cli}

    return router
