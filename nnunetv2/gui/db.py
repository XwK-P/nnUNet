from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import MetaData, Table, Column, String, event, create_engine
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
