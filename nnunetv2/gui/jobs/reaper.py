"""Reaper supervises spawned processes and updates job status on exit.

run_reaper(cfg, job_id, pid):
  Spawns a thread executor task awaiting os.waitpid (POSIX) or psutil wait
  (cross-platform), then transitions the row.

attach_on_boot(cfg):
  Walks all non-terminal jobs and either schedules a reaper coroutine
  (live pid) or transitions to failed/unknown (dead pid).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.signals import is_alive
from nnunetv2.gui.state.jobs import Job, JobFilter, list_jobs, update_job_status


def _wait_process_blocking(pid: int) -> int:
    """Block until pid exits; return exit code (or -1 if it cannot be determined)."""
    try:
        import psutil
    except ImportError:
        psutil = None  # type: ignore[assignment]

    if psutil is not None:
        try:
            p = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return -1
        try:
            rc = p.wait()
            return int(rc) if rc is not None else -1
        except psutil.NoSuchProcess:
            return -1

    # Fallback (POSIX only): try os.waitpid, else poll.
    if os.name == "posix":
        try:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            if os.WIFSIGNALED(status):
                return -os.WTERMSIG(status)
            return -1
        except ChildProcessError:
            # Not a child; poll instead.
            import time
            while is_alive(pid):
                time.sleep(0.5)
            return 0
    return -1


async def run_reaper(cfg: GuiConfig, job_id: int, pid: Optional[int]) -> None:
    """Await `pid` exit and write the terminal status row."""
    if pid is None:
        return
    loop = asyncio.get_running_loop()
    exit_code = await loop.run_in_executor(None, _wait_process_blocking, pid)
    final_status = "completed" if exit_code == 0 else "failed"
    update_job_status(
        cfg, job_id,
        status=final_status,
        ended_at=datetime.now(timezone.utc),
        exit_code=exit_code,
    )


def _disk_evidence_terminal_status(cfg: GuiConfig, job: Job) -> str:
    """Best-effort: train jobs with a final checkpoint = completed; else unknown."""
    if job.kind == "train" and job.output_run_id:
        ckpt = Path(cfg.results) / job.output_run_id / "checkpoint_final.pth"
        if ckpt.is_file():
            return "completed"
    return "unknown"


async def attach_on_boot(cfg: GuiConfig) -> list[asyncio.Task]:
    """Sweep non-terminal jobs; reschedule reapers for live PIDs."""
    scheduled: list[asyncio.Task] = []
    for job in list_jobs(cfg, JobFilter()):
        if job.status not in ("queued", "starting", "running"):
            continue
        if job.status == "queued":
            # Will be picked up by the queue advancer; nothing to do here.
            continue
        if job.pid is None:
            update_job_status(
                cfg, job.id, status="failed",
                ended_at=datetime.now(timezone.utc),
                error_message="no pid recorded",
            )
            continue
        if is_alive(job.pid):
            task = asyncio.create_task(run_reaper(cfg, job.id, job.pid))
            scheduled.append(task)
        else:
            terminal = _disk_evidence_terminal_status(cfg, job)
            update_job_status(
                cfg, job.id, status=terminal,
                ended_at=datetime.now(timezone.utc),
                error_message=("process gone, no disk evidence" if terminal == "unknown" else None),
            )
    return scheduled
