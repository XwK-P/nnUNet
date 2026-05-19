"""Read-only Jobs router. Phase 3 lists GUI-tracked jobs; Phase 4 adds write actions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.jobs import Job, JobFilter, get_job, list_jobs


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("", response_model=list[Job])
    def list_all(
        request: Request,
        kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[Job]:
        return list_jobs(request.app.state.gui_config, JobFilter(kind=kind, status=status))

    @router.get("/{job_id}", response_model=Job)
    def get_one(job_id: int, request: Request) -> Job:
        j = get_job(request.app.state.gui_config, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return j

    return router
