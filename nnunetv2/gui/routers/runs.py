"""Runs router."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from nnunetv2.gui.services.images import get_slice_png_cached
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

    # The same predictions/ folder can hold non-segmentation artifacts:
    # --save_probabilities writes .npz/.pkl/.npy siblings with the same stem,
    # and nnUNet may drop predict_from_raw_data_args.json into the directory.
    # Listing/preview must only surface segmentation files; otherwise the
    # case list grows duplicates and prediction_preview can pick a .npz or
    # JSON file first and fail to decode.
    # _PRED_SUFFIXES is also the suffix-preference ordering: compressed
    # NIfTI wins over uncompressed, then non-NIfTI formats by likelihood.
    _PRED_SUFFIXES = (".nii.gz", ".nii", ".nrrd", ".mha", ".tif", ".tiff", ".png")

    def _is_prediction_file(name: str) -> bool:
        lower = name.lower()
        return any(lower.endswith(suf) for suf in _PRED_SUFFIXES)

    def _strip_pred_suffix(name: str) -> str:
        lower = name.lower()
        for suf in _PRED_SUFFIXES:
            if lower.endswith(suf):
                return name[: -len(suf)]
        return name.split(".")[0]

    def _suffix_rank(name: str) -> int:
        """Index into _PRED_SUFFIXES (lower is preferred). Non-prediction
        names rank last so they never beat a real prediction file.
        """
        lower = name.lower()
        for i, suf in enumerate(_PRED_SUFFIXES):
            if lower.endswith(suf):
                return i
        return len(_PRED_SUFFIXES)

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
        # because it is lexicographically shorter — the opposite of what
        # we want when both formats live in the same predictions/ dir.
        files = [
            f for f in pred_dir.iterdir()
            if f.is_file() and _is_prediction_file(f.name)
        ]
        files.sort(key=lambda f: (_strip_pred_suffix(f.name), _suffix_rank(f.name), f.name))
        seen_stems: set[str] = set()
        out: list[dict] = []
        for f in files:
            stem = _strip_pred_suffix(f.name)
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
        pred_dir = Path(run.output_folder) / "predictions"
        match = None
        if pred_dir.is_dir():
            candidates = [
                f for f in pred_dir.iterdir()
                if f.is_file()
                and _is_prediction_file(f.name)
                and _strip_pred_suffix(f.name) == case_id
            ]
            # Lower suffix rank wins (e.g. .nii.gz over .nii); ties are
            # broken by filename so the result is deterministic.
            candidates.sort(key=lambda f: (_suffix_rank(f.name), f.name))
            if candidates:
                match = candidates[0]
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        png = get_slice_png_cached(str(match), axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")

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
