"""Models router — list trained models + per-model actions."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.models import Model, list_models, get_model


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/models", tags=["models"])

    @router.get("", response_model=list[Model])
    def list_all(request: Request) -> list[Model]:
        return list_models(request.app.state.gui_config)

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
