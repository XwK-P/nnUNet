"""Runs router."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.runs import Run, RunFilter, list_runs, get_run


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["runs"])

    @router.get("", response_model=list[Run])
    def list_all(
        request: Request,
        dataset_id: Optional[str] = None,
        plans_name: Optional[str] = None,
        trainer_name: Optional[str] = None,
        configuration: Optional[str] = None,
        fold: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[Run]:
        flt = RunFilter(
            dataset_id=dataset_id,
            plans_name=plans_name,
            trainer_name=trainer_name,
            configuration=configuration,
            fold=fold,
            status=status,
        )
        return list_runs(request.app.state.gui_config, flt)

    # Run IDs contain slashes — use path: converter to capture the full string.
    @router.get("/{run_id:path}", response_model=Run)
    def get_one(run_id: str, request: Request) -> Run:
        r = get_run(request.app.state.gui_config, run_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return r

    return router
