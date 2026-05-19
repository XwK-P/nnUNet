"""GET /api/compare - aggregate per-run metric arrays + summary stats."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from nnunetv2.gui.state.compare import (
    gather_run_metrics, gather_run_summaries,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/compare", tags=["compare"])

    @router.get("")
    def compare(
        request: Request,
        run_ids: list[str] = Query(default_factory=list),
        metric_keys: Optional[list[str]] = Query(default=None),
    ) -> dict:
        cfg = request.app.state.gui_config
        if not run_ids:
            return {"metrics": [], "summaries": []}
        metrics = gather_run_metrics(cfg, run_ids, metric_keys=metric_keys)
        summaries = gather_run_summaries(cfg, run_ids)
        return {
            "metrics": [m.model_dump() for m in metrics],
            "summaries": [s.model_dump() for s in summaries],
        }

    return router
