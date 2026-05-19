"""Single-host serial job queue.

Each slot has its own asyncio.Lock + worker. v1 ships with a single
'global' slot; future phases shard by dataset/fold.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.launcher import _popen_kwargs
from nnunetv2.gui.jobs.reaper import run_reaper
from nnunetv2.gui.state.jobs import (
    Job,
    JobFilter,
    get_job,
    insert_job,
    list_jobs,
    update_job_status,
)


class JobQueue:
    def __init__(self, cfg: GuiConfig) -> None:
        self.cfg = cfg
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(
        self,
        *, kind: str, argv: list[str], env: dict[str, str], log_path: str,
        output_run_id: Optional[str] = None, slot: str = "global",
    ) -> Job:
        """Persist a queued row and kick the worker if idle."""
        # Persist as 'queued' first so the UI sees it immediately.
        job = insert_job(self.cfg, Job(
            id=None, kind=kind, args_json=json.dumps(argv),
            pid=None, pgid=None, status="queued",
            started_at=None, ended_at=None, exit_code=None,
            log_path=log_path, output_run_id=output_run_id,
            created_by="gui", error_message=None, slot=slot,
        ))
        # Kick worker; it picks up the next 'queued' job in this slot.
        t = asyncio.create_task(self._worker_kick(slot, env))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return job

    async def _worker_kick(self, slot: str, env: dict[str, str]) -> None:
        lock = self._locks[slot]
        if lock.locked():
            return  # another worker is already running
        async with lock:
            while True:
                next_job = self._pop_next_queued(slot)
                if next_job is None:
                    return
                await self._launch_in_place(next_job, env)
                # Reaper runs inline so the lock is held until exit (serial).
                if next_job.pid is None:
                    continue  # spawn failed; row marked failed by launcher
                await run_reaper(self.cfg, next_job.id, next_job.pid)

    async def _launch_in_place(self, queued: Job, env: dict[str, str]) -> None:
        """Promote a queued row to running by spawning the subprocess."""
        argv = json.loads(queued.args_json)
        log_path = queued.log_path or str(Path(self.cfg.results) / f"job_{queued.id}.log")
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            # The child inherits a dup of log_fh as its stdout; closing the
            # parent's reference immediately after Popen returns prevents an
            # fd leak across many queued jobs.
            log_fh = open(log_path, "ab", buffering=0)
            try:
                proc = subprocess.Popen(
                    argv, env=env,
                    stdout=log_fh, stderr=subprocess.STDOUT,
                    close_fds=True, **_popen_kwargs(),
                )
            finally:
                log_fh.close()
            pgid = os.getpgid(proc.pid) if os.name == "posix" else proc.pid
            update_job_status(self.cfg, queued.id, status="running",
                              pid=proc.pid, pgid=pgid,
                              started_at=datetime.now(timezone.utc))
            # Refresh local copy
            queued.pid = proc.pid
            queued.pgid = pgid
            queued.status = "running"
        except Exception as e:
            update_job_status(self.cfg, queued.id, status="failed",
                              ended_at=datetime.now(timezone.utc),
                              error_message=f"spawn failed: {e}")

    def _pop_next_queued(self, slot: str) -> Optional[Job]:
        candidates = [
            j for j in list_jobs(self.cfg, JobFilter(status="queued"))
            if j.slot == slot
        ]
        if not candidates:
            return None
        # list_jobs sorts desc by id; oldest is last.
        return candidates[-1]

    async def cancel(self, job_id: int) -> bool:
        """Cancel a queued job. Returns False if the job is no longer queued."""
        j = get_job(self.cfg, job_id)
        if j is None or j.status != "queued":
            return False
        update_job_status(self.cfg, job_id, status="cancelled",
                          ended_at=datetime.now(timezone.utc))
        return True

    async def kickstart_pending(self, env: Optional[dict[str, str]] = None) -> int:
        """Resume queued slots after a server restart.

        ``enqueue`` is what normally kicks a worker, so jobs left queued by
        a previous boot would otherwise sit forever waiting for a fresh
        enqueue to advance the lane. Walks `job WHERE status = 'queued'`,
        groups by ``slot``, and starts one worker per distinct slot using
        the current process environment by default.
        """
        env = env if env is not None else dict(os.environ)
        queued = [j for j in list_jobs(self.cfg, JobFilter(status="queued"))]
        slots = {j.slot for j in queued}
        for slot in slots:
            if self._locks[slot].locked():
                continue
            t = asyncio.create_task(self._worker_kick(slot, env))
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)
        return len(slots)

    async def drain(self, timeout: float = 30.0) -> None:
        """For tests: await all outstanding workers."""
        if not self._tasks:
            return
        await asyncio.wait_for(
            asyncio.gather(*list(self._tasks), return_exceptions=True),
            timeout=timeout,
        )
