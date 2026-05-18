from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import MetaData, Table, Column, String, Integer, DateTime, Index, event, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from nnunetv2.gui.config import GuiConfig


_metadata = MetaData()


settings_table = Table(
    "settings",
    _metadata,
    Column("key", String, primary_key=True),
    Column("value", String, nullable=False),
)


dataset_table = Table(
    "dataset",
    _metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id_int", Integer, nullable=True),
    Column("name", String, nullable=True),
    Column("raw_path", String, nullable=True),
    Column("preprocessed_path", String, nullable=True),
    Column("last_scanned_at", DateTime, nullable=True),
    Column("fingerprint_json", String, nullable=True),
    Column("case_count", Integer, nullable=True),
    Column("modality_count", Integer, nullable=True),
)


run_table = Table(
    "run",
    _metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id", String, nullable=False),
    Column("plans_name", String, nullable=False),
    Column("trainer_name", String, nullable=False),
    Column("configuration", String, nullable=False),
    Column("fold", String, nullable=False),
    Column("output_folder", String, nullable=False),
    Column("status", String, nullable=False),
    Column("source", String, nullable=False),
    Column("created_at", DateTime, nullable=True),
    Column("last_seen_at", DateTime, nullable=True),
    Column("tags_json", String, nullable=True),
    Column("notes", String, nullable=True),
    Index("ix_run_dataset_id", "dataset_id"),
)


@event.listens_for(Engine, "connect")
def _enable_wal(dbapi_connection, connection_record):
    # Guard: this listener fires for every SQLAlchemy engine in the process.
    # Only apply SQLite PRAGMAs when the underlying DB-API connection is sqlite3.
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _engine_for(cfg: GuiConfig) -> Engine:
    return create_engine(
        f"sqlite:///{cfg.state_db}",
        connect_args={"check_same_thread": False},
    )


def init_db(cfg: GuiConfig) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    engine = _engine_for(cfg)
    _metadata.create_all(engine)
    engine.dispose()


@contextmanager
def session_scope(cfg: GuiConfig) -> Iterator[Session]:
    engine = _engine_for(cfg)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
