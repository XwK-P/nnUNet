"""Jobs router. Phase 3 lists GUI-tracked jobs; Phase 4 adds write actions."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _reap_zombies_in_group(pgid: int) -> None:
    """Best-effort non-blocking reap of any child zombies in ``pgid``.

    After SIGKILL the kernel transitions the child into a zombie that
    sits in the proc table — and ``killpg(pgid, 0)`` reports it as
    alive — until somebody calls wait(). For queue-launched jobs the
    reaper does that via the held Popen handle. For the direct
    ``launcher.spawn()`` path (no queue, no reaper, used by some
    integration tests) nobody is waiting, so the zombie lingers until
    Python's ``subprocess._active`` cleanup runs on the next Popen
    call — well after our /stop grace window. Reap them here so
    ``is_alive(pgid)`` can drop to False as soon as the kernel agrees
    the group is gone.
    """
    if os.name != "posix":
        return
    try:
        while True:
            pid_reaped, _ = os.waitpid(-pgid, os.WNOHANG)
            if pid_reaped == 0:
                break
    except (ChildProcessError, OSError):
        # ECHILD: no children of this process belong to that group
        # (either already reaped by subprocess._active or the job was
        # launched by a different process). Either way nothing to do.
        return

from fastapi import APIRouter, HTTPException, Request, status

from nnunetv2.gui.config import job_env
from nnunetv2.gui.jobs.signals import is_alive, kill_group, terminate
from nnunetv2.gui.state.jobs import (
    Job, JobFilter, JobPublic, get_job, list_jobs, update_job_status,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("", response_model=list[JobPublic])
    def list_all(
        request: Request,
        kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[JobPublic]:
        # JobPublic strips env_json before serialisation so the captured
        # launch env (PATH, CUDA_VISIBLE_DEVICES, absolute cfg paths)
        # doesn't leak through this endpoint.
        rows = list_jobs(request.app.state.gui_config, JobFilter(kind=kind, status=status))
        return [JobPublic.from_job(j) for j in rows]

    @router.get("/{job_id}", response_model=JobPublic)
    def get_one(job_id: int, request: Request) -> JobPublic:
        j = get_job(request.app.state.gui_config, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobPublic.from_job(j)

    @router.post("/{job_id}/stop")
    async def stop(job_id: int, request: Request) -> dict:
        cfg = request.app.state.gui_config
        j = get_job(cfg, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if j.status not in ("starting", "running"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot stop a job in status {j.status!r}",
            )
        # In the 'starting' window the launcher has flipped status but
        # not yet returned from Popen, so pgid can be momentarily None.
        # Poll the row briefly instead of 500'ing the user-visible action.
        loop = asyncio.get_event_loop()
        pgid_deadline = loop.time() + 2.0
        while j.pgid is None and loop.time() < pgid_deadline:
            await asyncio.sleep(0.1)
            refreshed = get_job(cfg, job_id)
            if refreshed is None:
                # Row vanished mid-poll — treat as already-gone.
                raise HTTPException(status_code=404, detail="Job not found")
            j = refreshed
            if j.status not in ("starting", "running"):
                # The launcher landed in a terminal state on its own
                # (e.g. spawn failed); no group to signal.
                return {"ok": True, "status": j.status}
        if j.pgid is None:
            # Still no pgid after the grace window. Don't 500 — surface as
            # 409 so the client can retry once the launcher finishes wiring
            # the row up.
            raise HTTPException(
                status_code=409,
                detail="job has no pgid yet (launcher mid-spawn); retry shortly",
            )
        terminate(j.pgid)
        # Grace period 5s for SIGTERM
        deadline = loop.time() + 5
        while is_alive(j.pgid) and loop.time() < deadline:
            await asyncio.sleep(0.2)
        if is_alive(j.pgid):
            kill_group(j.pgid)
        # After SIGKILL the kernel may keep the child as a zombie in
        # the proc table until somebody wait()s it. killpg(pgid, 0)
        # treats zombies as alive, so this loop polls for either
        # (a) the OS drops the group entirely, or (b) the background
        # reaper records a terminal status — both mean the subprocess
        # is effectively gone. We also reap any zombies WE own on each
        # iteration, so test paths that bypass the queue (and thus the
        # reaper's proc.wait()) still see is_alive go False quickly.
        deadline = loop.time() + 10
        terminal_states = ("killed", "failed", "completed", "cancelled", "unknown")
        while loop.time() < deadline:
            _reap_zombies_in_group(j.pgid)
            if not is_alive(j.pgid):
                break
            refreshed = get_job(cfg, job_id)
            if refreshed is not None and refreshed.status in terminal_states:
                # Reaper already transitioned the row; signals worked,
                # we just lost the foot race against zombification.
                return {"ok": True, "status": refreshed.status}
            await asyncio.sleep(0.1)
        if is_alive(j.pgid):
            # Signals were delivered but the process group is still
            # alive past the grace window (permission edge case,
            # container namespace, uninterruptable kernel state).
            # Don't claim 'killed' — that would hide live GPU usage
            # and mislead operators. Leave the row in its prior state;
            # the reaper will transition it once the process exits.
            raise HTTPException(
                status_code=504,
                detail=(
                    f"sent SIGTERM and SIGKILL to pgid {j.pgid} but the "
                    "process is still alive; retry or wait for the reaper "
                    "to catch the exit"
                ),
            )
        update_job_status(
            cfg, job_id, status="killed",
            ended_at=datetime.now(timezone.utc),
        )
        return {"ok": True, "status": "killed"}

    @router.post("/{job_id}/cancel")
    async def cancel(job_id: int, request: Request) -> dict:
        cfg = request.app.state.gui_config
        j = get_job(cfg, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Job not found")
        q = request.app.state.job_queue
        ok = await q.cancel(job_id)
        if not ok:
            raise HTTPException(
                status_code=409,
                detail="Cannot cancel — job is not queued (use /stop)",
            )
        return {"ok": True, "status": "cancelled"}

    @router.post("/{job_id}/restart", status_code=status.HTTP_201_CREATED)
    async def restart(job_id: int, request: Request) -> dict:
        cfg = request.app.state.gui_config
        old = get_job(cfg, job_id)
        if old is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if old.status not in ("completed", "failed", "killed", "cancelled", "unknown"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot restart a job in status {old.status!r}",
            )
        argv = json.loads(old.args_json)
        log_path = old.log_path or str(
            Path(cfg.results) / ".nnunet_gui" / "logs" / f"restart_{job_id}.log"
        )
        new = await request.app.state.job_queue.enqueue(
            kind=old.kind, argv=argv, env=job_env(cfg),
            log_path=log_path, output_run_id=old.output_run_id,
            slot=old.slot,
        )
        return {"new_job_id": new.id}

    return router
