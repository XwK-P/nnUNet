"""POST /api/postproc/apply — enqueue nnUNetv2_apply_postprocessing."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nnunetv2.gui.services.cli_renderer import (
    PostprocRequest, render_postproc, argv_to_cli_string,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/postproc", tags=["postproc"])

    @router.post("/apply", status_code=status.HTTP_201_CREATED)
    async def apply(req: PostprocRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_postproc(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / "postproc.log")
        j = await q.enqueue(kind="postproc", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}

    return router
