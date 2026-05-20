"""Job records and lifecycle. Phase 3 = read-only listing; Phase 4 adds launcher."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import job_table, session_scope


class Job(BaseModel):
    id: Optional[int]
    kind: str
    args_json: str
    pid: Optional[int]
    pgid: Optional[int]
    status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    exit_code: Optional[int]
    log_path: Optional[str]
    output_run_id: Optional[str]
    created_by: Optional[str]
    error_message: Optional[str]
    slot: str = "global"
    env_json: Optional[str] = None


class JobFilter(BaseModel):
    kind: Optional[str] = None
    status: Optional[str] = None


def _row_to_model(row) -> Job:
    return Job(
        id=row.id, kind=row.kind, args_json=row.args_json,
        pid=row.pid, pgid=row.pgid, status=row.status,
        started_at=row.started_at, ended_at=row.ended_at,
        exit_code=row.exit_code, log_path=row.log_path,
        output_run_id=row.output_run_id, created_by=row.created_by,
        error_message=row.error_message,
        slot=getattr(row, "slot", None) or "global",
        env_json=getattr(row, "env_json", None),
    )


def list_jobs(cfg: GuiConfig, flt: JobFilter) -> list[Job]:
    stmt = select(job_table)
    if flt.kind:
        stmt = stmt.where(job_table.c.kind == flt.kind)
    if flt.status:
        stmt = stmt.where(job_table.c.status == flt.status)
    stmt = stmt.order_by(job_table.c.id.desc())
    with session_scope(cfg) as s:
        rows = s.execute(stmt).all()
    return [_row_to_model(r) for r in rows]


def get_job(cfg: GuiConfig, job_id: int) -> Optional[Job]:
    with session_scope(cfg) as s:
        row = s.execute(select(job_table).where(job_table.c.id == job_id)).first()
    return _row_to_model(row) if row else None


def insert_job(cfg: GuiConfig, job: Job) -> Job:
    values = job.model_dump()
    values.pop("id", None)  # SQLite assigns
    with session_scope(cfg) as s:
        result = s.execute(job_table.insert().values(**values))
        new_id = result.inserted_primary_key[0]
    fetched = get_job(cfg, new_id)
    assert fetched is not None
    return fetched


def claim_queued_for_launch(cfg: GuiConfig, job_id: int) -> bool:
    """Atomically transition ``queued`` -> ``starting`` for a single row.

    Returns True iff we won the claim — i.e. the row was still queued at
    the moment the UPDATE ran. False covers the race where /cancel ran
    between _pop_next_queued and _launch_in_place, or the row no longer
    exists. The queue worker uses this as the gate that decides whether
    to actually spawn the subprocess.
    """
    stmt = (
        job_table.update()
        .where(job_table.c.id == job_id)
        .where(job_table.c.status == "queued")
        .values(status="starting")
    )
    with session_scope(cfg) as s:
        result = s.execute(stmt)
    return (result.rowcount or 0) > 0


def update_job_status(
    cfg: GuiConfig, job_id: int, *,
    status: Optional[str] = None,
    pid: Optional[int] = None,
    pgid: Optional[int] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    exit_code: Optional[int] = None,
    error_message: Optional[str] = None,
    log_path: Optional[str] = None,
    output_run_id: Optional[str] = None,
) -> None:
    update_values = {k: v for k, v in {
        "status": status, "pid": pid, "pgid": pgid,
        "started_at": started_at, "ended_at": ended_at,
        "exit_code": exit_code, "error_message": error_message,
        "log_path": log_path, "output_run_id": output_run_id,
    }.items() if v is not None}
    if not update_values:
        return
    with session_scope(cfg) as s:
        s.execute(job_table.update().where(job_table.c.id == job_id).values(**update_values))
