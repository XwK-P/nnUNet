"""Run record and repository functions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import run_table, session_scope


class Run(BaseModel):
    id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    output_folder: str
    status: str
    source: str
    created_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    tags_json: Optional[str]
    notes: Optional[str]


class RunFilter(BaseModel):
    dataset_id: Optional[str] = None
    plans_name: Optional[str] = None
    trainer_name: Optional[str] = None
    configuration: Optional[str] = None
    fold: Optional[str] = None
    status: Optional[str] = None


def canonical_run_id(
    dataset_id: str,
    plans_name: str,
    trainer_name: str,
    configuration: str,
    fold: str,
) -> str:
    return f"{dataset_id}/{plans_name}__{trainer_name}__{configuration}/fold_{fold}"


def _row_to_model(row) -> Run:
    return Run(
        id=row.id,
        dataset_id=row.dataset_id,
        plans_name=row.plans_name,
        trainer_name=row.trainer_name,
        configuration=row.configuration,
        fold=row.fold,
        output_folder=row.output_folder,
        status=row.status,
        source=row.source,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        tags_json=row.tags_json,
        notes=row.notes,
    )


def list_runs(cfg: GuiConfig, flt: RunFilter) -> list[Run]:
    stmt = select(run_table)
    if flt.dataset_id:
        stmt = stmt.where(run_table.c.dataset_id == flt.dataset_id)
    if flt.plans_name:
        stmt = stmt.where(run_table.c.plans_name == flt.plans_name)
    if flt.trainer_name:
        stmt = stmt.where(run_table.c.trainer_name == flt.trainer_name)
    if flt.configuration:
        stmt = stmt.where(run_table.c.configuration == flt.configuration)
    if flt.fold:
        stmt = stmt.where(run_table.c.fold == flt.fold)
    if flt.status:
        stmt = stmt.where(run_table.c.status == flt.status)
    stmt = stmt.order_by(run_table.c.last_seen_at.desc().nulls_last())
    with session_scope(cfg) as s:
        rows = s.execute(stmt).all()
    return [_row_to_model(r) for r in rows]


def get_run(cfg: GuiConfig, run_id: str) -> Optional[Run]:
    with session_scope(cfg) as s:
        row = s.execute(
            select(run_table).where(run_table.c.id == run_id)
        ).first()
    return _row_to_model(row) if row else None


def upsert_run(cfg: GuiConfig, run: Run) -> None:
    values = run.model_dump()
    with session_scope(cfg) as s:
        existing = s.execute(
            select(run_table.c.id).where(run_table.c.id == run.id)
        ).first()
        if existing:
            s.execute(
                run_table.update().where(run_table.c.id == run.id).values(**values)
            )
        else:
            s.execute(run_table.insert().values(**values))
