"""Dataset record and repository functions."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import dataset_table, session_scope


class Dataset(BaseModel):
    id: str
    dataset_id_int: Optional[int]
    name: Optional[str]
    raw_path: Optional[str]
    preprocessed_path: Optional[str]
    last_scanned_at: Optional[datetime]
    fingerprint_json: Optional[str]
    case_count: Optional[int]
    modality_count: Optional[int]


def _row_to_model(row) -> Dataset:
    return Dataset(
        id=row.id,
        dataset_id_int=row.dataset_id_int,
        name=row.name,
        raw_path=row.raw_path,
        preprocessed_path=row.preprocessed_path,
        last_scanned_at=row.last_scanned_at,
        fingerprint_json=row.fingerprint_json,
        case_count=row.case_count,
        modality_count=row.modality_count,
    )


def list_datasets(cfg: GuiConfig) -> list[Dataset]:
    with session_scope(cfg) as s:
        rows = s.execute(
            select(dataset_table).order_by(dataset_table.c.dataset_id_int.asc().nulls_last())
        ).all()
    return [_row_to_model(r) for r in rows]


def get_dataset(cfg: GuiConfig, dataset_id: str) -> Optional[Dataset]:
    with session_scope(cfg) as s:
        row = s.execute(
            select(dataset_table).where(dataset_table.c.id == dataset_id)
        ).first()
    return _row_to_model(row) if row else None


def upsert_dataset(cfg: GuiConfig, dataset: Dataset) -> None:
    values = dataset.model_dump()
    with session_scope(cfg) as s:
        existing = s.execute(
            select(dataset_table.c.id).where(dataset_table.c.id == dataset.id)
        ).first()
        if existing:
            s.execute(
                dataset_table.update()
                .where(dataset_table.c.id == dataset.id)
                .values(**values)
            )
        else:
            s.execute(dataset_table.insert().values(**values))


def fingerprint_dict(dataset: Dataset) -> Optional[dict]:
    if not dataset.fingerprint_json:
        return None
    try:
        return json.loads(dataset.fingerprint_json)
    except json.JSONDecodeError:
        return None
