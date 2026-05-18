"""Runs router."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from nnunetv2.gui.services.images import get_slice_png_cached
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

    # Prediction routes need to be declared BEFORE the catch-all `/{run_id:path}`
    # because FastAPI evaluates routes in declaration order; the path converter
    # would otherwise swallow the trailing /predictions[/...] segment.
    @router.get("/{run_id:path}/predictions")
    def list_predictions(run_id: str, request: Request) -> list[dict]:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        pred_dir = Path(run.output_folder) / "predictions"
        if not pred_dir.is_dir():
            return []
        out: list[dict] = []
        for f in sorted(pred_dir.iterdir()):
            if not f.is_file():
                continue
            stem = f.name.split(".")[0]
            out.append({"case_id": stem, "path": str(f)})
        return out

    @router.get("/{run_id:path}/predictions/{case_id}")
    def prediction_preview(
        run_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0,
        window_lo: Optional[float] = None, window_hi: Optional[float] = None,
    ) -> Response:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        pred_dir = Path(run.output_folder) / "predictions"
        # Find the file with matching stem
        match = None
        if pred_dir.is_dir():
            for f in pred_dir.iterdir():
                if f.is_file() and f.name.split(".")[0] == case_id:
                    match = f
                    break
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        png = get_slice_png_cached(str(match), axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")

    # Run IDs contain slashes — use path: converter to capture the full string.
    @router.get("/{run_id:path}", response_model=Run)
    def get_one(run_id: str, request: Request) -> Run:
        r = get_run(request.app.state.gui_config, run_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return r

    return router
