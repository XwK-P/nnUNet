"""Spawn nnUNet CLI subprocesses in their own process group, persist the job row.

The subprocess inherits a clean copy of the parent env (with the three
nnUNet_* vars guaranteed present). stdout+stderr are redirected to log_path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.jobs import Job, get_job, insert_job, update_job_status


def _popen_kwargs() -> dict:
    if os.name == "posix":
        return {"start_new_session": True}
    elif sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {}


def spawn(
    cfg: GuiConfig,
    *,
    kind: str,
    argv: list[str],
    env: dict[str, str],
    log_path: str,
    output_run_id: Optional[str] = None,
    slot: str = "global",
) -> Job:
    """Spawn `argv` in its own process group, persist & return the Job."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    # Insert in 'starting' first so the row exists even if Popen raises.
    started_at = datetime.now(timezone.utc)
    job = insert_job(cfg, Job(
        id=None, kind=kind, args_json=json.dumps(argv),
        pid=None, pgid=None, status="starting",
        started_at=started_at, ended_at=None, exit_code=None,
        log_path=log_path, output_run_id=output_run_id,
        created_by="gui", error_message=None, slot=slot,
    ))
    try:
        # The child inherits a dup of log_fh as stdout; close the parent's
        # reference right after Popen returns to avoid fd leaks across many
        # launches.
        log_fh = open(log_path, "ab", buffering=0)
        try:
            proc = subprocess.Popen(
                argv,
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **_popen_kwargs(),
            )
        finally:
            log_fh.close()
        pgid = os.getpgid(proc.pid) if os.name == "posix" else proc.pid
        update_job_status(cfg, job.id, status="running", pid=proc.pid, pgid=pgid)
    except Exception as e:
        update_job_status(
            cfg, job.id, status="failed",
            ended_at=datetime.now(timezone.utc),
            exit_code=-1, error_message=f"spawn failed: {e}",
        )
        raise
    # Re-fetch to return the updated row
    fresh = get_job(cfg, job.id)
    assert fresh is not None
    return fresh
