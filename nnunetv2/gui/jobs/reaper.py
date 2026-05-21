"""Reaper supervises spawned processes and updates job status on exit.

run_reaper(cfg, job_id, pid, proc=None):
  Spawns a thread executor task awaiting the subprocess. When `proc`
  (the live Popen handle) is provided we use proc.wait() and get a
  definitive exit code; otherwise we fall back to psutil/os.waitpid
  (the attach_on_boot path, where the process isn't our child).

attach_on_boot(cfg):
  Walks all non-terminal jobs and either schedules a reaper coroutine
  (live pid) or transitions to failed/unknown (dead pid).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.signals import is_alive
from nnunetv2.gui.state.jobs import Job, JobFilter, get_job, list_jobs, update_job_status


def _wait_process_blocking(
    pid: int, proc: Optional[subprocess.Popen] = None,
) -> Optional[int]:
    """Block until pid exits; return exit code, or None if it cannot be determined.

    When ``proc`` is supplied we use its .wait() directly. Without that,
    CPython's ``subprocess._active`` cleanup can reap the child between
    Popen returning and the reaper running, leaving psutil with a
    NoSuchProcess race and returning None for in-flight children — the
    cause of intermittent ``status='unknown'`` (and lost exit codes on
    /stop) on busy CI boxes.

    Returns:
      * int (incl. negative for POSIX signal-termination):
          definitive exit status, observed because we held the Popen
          handle (or pid was otherwise our child).
      * None:
          we waited for pid to leave the proc table but could not read
          its exit code — e.g. attach_on_boot is following a process
          from a previous server boot, so it isn't a child of this
          process and neither psutil.Process.wait() nor os.waitpid will
          return a status. Callers should fall back to disk evidence
          rather than treating this as "failed".
    """
    if proc is not None:
        # Authoritative path: the Popen handle ensures the child is
        # ours and gives us its exit code without racing the GC's
        # subprocess._active cleanup. Returncode is signed for POSIX
        # signal termination (e.g. -15 for SIGTERM).
        try:
            return int(proc.wait())
        except Exception:
            return None

    try:
        import psutil
    except ImportError:
        psutil = None  # type: ignore[assignment]

    if psutil is not None:
        try:
            p = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return None
        try:
            rc = p.wait()
            # psutil returns None for non-children on POSIX because it can't
            # read the exit status — that's the "unknown" sentinel we want.
            return int(rc) if rc is not None else None
        except psutil.NoSuchProcess:
            return None

    # Fallback (POSIX only): try os.waitpid, else poll.
    if os.name == "posix":
        try:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            if os.WIFSIGNALED(status):
                return -os.WTERMSIG(status)
            return None
        except ChildProcessError:
            # Not a child; poll until it disappears, then surface "unknown"
            # so run_reaper can fall back to disk evidence.
            import time
            while is_alive(pid):
                time.sleep(0.5)
            return None
    return None


async def run_reaper(
    cfg: GuiConfig, job_id: int, pid: Optional[int],
    *, proc: Optional[subprocess.Popen] = None,
) -> None:
    """Await `pid` exit and write the terminal status row.

    Three branches:
      1. Row was already moved into a terminal state by the stop/cancel
         handler (status == 'killed' or 'cancelled'): record the observed
         exit code for diagnostics only; leave status + ended_at alone.
      2. We know the exit code: 0 = completed, non-zero = failed.
      3. Exit code is unknown (typical when attach_on_boot is following
         a re-attached non-child process): defer to disk evidence
         (`checkpoint_final.pth` for trainings) instead of falsely
         marking the job 'failed'. _disk_evidence_terminal_status
         returns 'completed' when the disk indicates success, otherwise
         'unknown' so an operator can reconcile from the Jobs page.
    """
    if pid is None:
        return
    loop = asyncio.get_running_loop()
    exit_code = await loop.run_in_executor(
        None, _wait_process_blocking, pid, proc,
    )
    cur = get_job(cfg, job_id)
    if cur is not None and cur.status in ("killed", "cancelled"):
        if exit_code is not None:
            update_job_status(cfg, job_id, exit_code=exit_code)
        return
    if exit_code is None:
        # Re-attached non-child: use disk evidence rather than assume failure.
        evidence_job = cur if cur is not None else get_job(cfg, job_id)
        terminal = (
            _disk_evidence_terminal_status(cfg, evidence_job)
            if evidence_job is not None
            else "unknown"
        )
        update_job_status(
            cfg, job_id,
            status=terminal,
            ended_at=datetime.now(timezone.utc),
            error_message=("exit code unrecoverable (re-attached pid)"
                           if terminal == "unknown" else None),
        )
        return
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
            # JobQueue.kickstart_pending() (called from the server startup
            # hook right after reaper_attach) re-kicks workers for any slot
            # that still has queued rows. Nothing pid-shaped to do here.
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
