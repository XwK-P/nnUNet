"""POST /api/predict — render argv, optionally enqueue."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status

from nnunetv2.gui.config import job_env
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
            kind="predict", argv=argv, env=job_env(cfg),
            log_path=log_path,
        )
        return {"job_id": job.id, "argv": argv, "cli": cli}

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
            # Take the first non-background label's Dice
            dice = None
            for label, m in metrics.items():
                if label == "0":
                    continue
                if isinstance(m, dict) and "Dice" in m:
                    dice = float(m["Dice"])
                    break
            cases.append({"case_id": Path(cid).name, "dice": dice})
        return {"foreground_mean_dice": fg, "cases": cases}

    return router
