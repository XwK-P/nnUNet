"""Runs router."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from nnunetv2.gui.services.predictions import (
    find_prediction_for_case,
    is_prediction_file,
    render_prediction_preview,
    strip_pred_suffix,
    suffix_rank,
)
from nnunetv2.gui.state.runs import Run, RunFilter, list_runs, get_run


class RunUpdateRequest(BaseModel):
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


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
        # Sort by (stem, suffix preference, name) so duplicate stems cluster
        # and the preferred suffix (e.g. .nii.gz over .nii) wins the dedup.
        # Plain `sorted()` would put 'case.nii' before 'case.nii.gz'
        # because it is lexicographically shorter.
        files = [
            f for f in pred_dir.iterdir()
            if f.is_file() and is_prediction_file(f.name)
        ]
        files.sort(key=lambda f: (strip_pred_suffix(f.name), suffix_rank(f.name), f.name))
        seen_stems: set[str] = set()
        out: list[dict] = []
        for f in files:
            stem = strip_pred_suffix(f.name)
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
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
        match = find_prediction_for_case(Path(run.output_folder) / "predictions", case_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        return render_prediction_preview(match, axis=axis, slice=slice, window=window)

    @router.get("/{run_id:path}/predictions/{case_id}/shape")
    def prediction_shape(run_id: str, case_id: str, request: Request) -> dict:
        """Volume shape of the matched prediction file for ``case_id``.

        The Predict viewer slider needs real per-axis bounds to keep
        navigation honest on volumes whose extent differs from the
        previous hard-coded 256 default. Re-uses
        ``find_prediction_for_case`` so the same suffix-preference
        rules apply. 415 (rather than 200 with a placeholder) for
        formats we don't decode here, matching prediction_preview.
        """
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        match = find_prediction_for_case(Path(run.output_folder) / "predictions", case_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        name_lower = match.name.lower()
        if name_lower.endswith((".nii.gz", ".nii")):
            from nnunetv2.gui.services.images import volume_shape
            d0, d1, d2 = volume_shape(match)
            return {"shape": [d0, d1, d2]}
        if name_lower.endswith(".png"):
            from PIL import Image
            with Image.open(str(match)) as img:
                w, h = img.size
            return {"shape": [h, w, 1]}
        if name_lower.endswith((".tif", ".tiff")):
            from PIL import Image
            with Image.open(str(match)) as img:
                w, h = img.size
                n_frames = int(getattr(img, "n_frames", 1))
            return {"shape": [n_frames, h, w]}
        raise HTTPException(
            status_code=415,
            detail=f"Shape not supported for {match.suffix!r}",
        )

    @router.get("/{run_id:path}/metrics_history")
    def metrics_history(run_id: str, request: Request) -> list[dict]:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        from nnunetv2.gui.services.tb_tailer import read_all_metrics
        return read_all_metrics(Path(run.output_folder) / "tensorboard")

    @router.get("/{run_id:path}/log_tail", response_class=PlainTextResponse)
    def log_tail(run_id: str, request: Request, bytes: int = 8192) -> str:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        for log in Path(run.output_folder).glob("training_log_*.txt"):
            size = log.stat().st_size
            with log.open("rb") as f:
                f.seek(max(0, size - bytes))
                data = f.read()
            return data.decode("utf-8", errors="replace")
        return ""

    # Run IDs contain slashes — use path: converter to capture the full string.
    @router.get("/{run_id:path}", response_model=Run)
    def get_one(run_id: str, request: Request) -> Run:
        r = get_run(request.app.state.gui_config, run_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return r

    @router.put("/{run_id:path}", response_model=Run)
    def update_run(run_id: str, body: RunUpdateRequest, request: Request) -> Run:
        from nnunetv2.gui.state.runs import update_run_meta
        cfg = request.app.state.gui_config
        tags_json = json.dumps(body.tags) if body.tags is not None else None
        result = update_run_meta(cfg, run_id, tags_json=tags_json, notes=body.notes)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return result

    return router
