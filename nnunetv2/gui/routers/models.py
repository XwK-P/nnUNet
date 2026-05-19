"""Models router — list trained models + per-model actions."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from nnunetv2.gui.services.cli_renderer import (
    ExportModelRequest,
    ImportModelRequest,
    argv_to_cli_string,
    render_export_model,
    render_import_model,
)
from nnunetv2.gui.state.models import Model, list_models, get_model


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/models", tags=["models"])

    @router.get("", response_model=list[Model])
    def list_all(request: Request) -> list[Model]:
        return list_models(request.app.state.gui_config)

    @router.post("/export", status_code=status.HTTP_201_CREATED)
    async def export(req: ExportModelRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_export_model(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs"
                       / f"export_d{req.dataset_id}.log")
        j = await q.enqueue(kind="export", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}

    @router.post("/import", status_code=status.HTTP_201_CREATED)
    async def import_model(req: ImportModelRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_import_model(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / "import_model.log")
        j = await q.enqueue(kind="import", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}

    @router.get("/{model_id:path}", response_model=Model)
    def get_one(model_id: str, request: Request) -> Model:
        cfg = request.app.state.gui_config
        # model_id format: <dataset>/<plans>__<trainer>__<config>
        try:
            dataset_id, rest = model_id.split("/", 1)
            plans, trainer, configuration = rest.split("__")
        except ValueError:
            raise HTTPException(status_code=400, detail="malformed model id")
        m = get_model(cfg, dataset_id, plans, trainer, configuration)
        if m is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
        return m

    return router
