"""POST /api/predict — render argv, optionally enqueue."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status

from nnunetv2.gui.config import job_env
from nnunetv2.gui.services.cli_renderer import (
    PredictRequest,
    argv_to_cli_string,
    render_predict,
)
from nnunetv2.gui.services.predictions import (
    find_prediction_for_case,
    render_prediction_preview,
    strip_pred_suffix,
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
            kind="predict", argv=argv, env=job_env(cfg),
            log_path=log_path,
        )
        return {"job_id": job.id, "argv": argv, "cli": cli}

    @router.get("/preview")
    def preview_by_folder(
        prediction_folder: str, case_id: str,
        axis: int = 0, slice: int = 0,
        window_lo: Optional[float] = None, window_hi: Optional[float] = None,
    ) -> Response:
        """Folder-scoped variant of /api/runs/.../predictions/{case_id}.

        The Predict page lets the user paste an arbitrary predictions/
        folder (typically alongside a summary.json from a CLI run).
        That folder isn't tied to a GUI-managed Run, so the run-scoped
        endpoint can't reach it; this mirror takes the folder directly
        and reuses the same suffix-preference + format-dispatch rules.
        """
        match = find_prediction_for_case(Path(prediction_folder), case_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        window = (
            (window_lo, window_hi)
            if (window_lo is not None and window_hi is not None)
            else None
        )
        return render_prediction_preview(match, axis=axis, slice=slice, window=window)

    @router.get("/per_case_metrics")
    def per_case_metrics(prediction_folder: str) -> dict:
        fp = Path(prediction_folder) / "summary.json"
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="no summary.json next to predictions")
        try:
            data = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=500, detail=f"failed to parse summary.json: {e}")
        fg = (data.get("foreground_mean") or {}).get("Dice")
        cases = []
        for entry in data.get("metric_per_case") or []:
            cid = entry.get("reference_file") or entry.get("case_id") or ""
            metrics = entry.get("metrics") or {}
            # Average over all non-background label Dice values that are
            # actually finite. nnUNet writes NaN for classes absent in a
            # given case; including those poisons the mean to NaN and
            # FastAPI's JSON encoder rejects non-finite floats, so the
            # endpoint would 500 on common multiclass datasets.
            fg_dices: list[float] = []
            for label, m in metrics.items():
                if label == "0":
                    continue
                if isinstance(m, dict) and "Dice" in m:
                    val = float(m["Dice"])
                    if math.isfinite(val):
                        fg_dices.append(val)
            dice = sum(fg_dices) / len(fg_dices) if fg_dices else None
            # Strip the file extension from reference_file so the case_id
            # the UI receives matches the suffix-stripped stems used by
            # find_prediction_for_case in /api/predict/preview. Without
            # this, clicking a row would 404 because "case_001.nii.gz"
            # never equals the stored stem "case_001".
            cases.append({"case_id": strip_pred_suffix(Path(cid).name), "dice": dice})
        return {"foreground_mean_dice": fg, "cases": cases}

    return router
