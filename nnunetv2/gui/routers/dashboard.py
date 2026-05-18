"""Dashboard router — aggregate stats for the landing page."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Request

from nnunetv2.gui.state.datasets import list_datasets
from nnunetv2.gui.state.runs import RunFilter, list_runs


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

    @router.get("")
    def get_dashboard(request: Request) -> dict:
        cfg = request.app.state.gui_config
        datasets = list_datasets(cfg)
        runs = list_runs(cfg, RunFilter())
        completed = [r for r in runs if r.status == "completed"]
        preprocessed = [d for d in datasets if d.preprocessed_path]

        recent = sorted(
            runs,
            key=lambda r: r.last_seen_at or r.created_at or 0,
            reverse=True,
        )[:6]

        def _disk(path: str) -> dict:
            try:
                usage = shutil.disk_usage(path)
                return {"path": path, "total": usage.total, "free": usage.free}
            except OSError:
                return {"path": path, "total": None, "free": None}

        return {
            "counts": {
                "datasets": len(datasets),
                "preprocessed_datasets": len(preprocessed),
                "runs": len(runs),
                "completed_runs": len(completed),
            },
            "recent_runs": [r.model_dump(mode="json") for r in recent],
            "active_jobs": [],  # Phase 3 fills this
            "system": {
                "disk": {
                    "raw": _disk(str(cfg.raw)),
                    "preprocessed": _disk(str(cfg.preprocessed)),
                    "results": _disk(str(cfg.results)),
                },
                # GPU stats land in Phase 7.
            },
        }

    return router
