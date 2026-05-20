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


job_table = Table(
    "job",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String, nullable=False),
    Column("args_json", String, nullable=False),
    Column("pid", Integer, nullable=True),
    Column("pgid", Integer, nullable=True),
    Column("status", String, nullable=False),
    Column("started_at", DateTime, nullable=True),
    Column("ended_at", DateTime, nullable=True),
    Column("exit_code", Integer, nullable=True),
    Column("log_path", String, nullable=True),
    Column("output_run_id", String, nullable=True),
    Column("created_by", String, nullable=True),
    Column("error_message", String, nullable=True),
    Column("slot", String, nullable=False, server_default="global"),
    # env_json: JSON-encoded process environment captured at enqueue time.
    # The queue worker uses each row's own env when launching, so a later
    # enqueue with different nnUNet_* paths can't clobber earlier queued
    # jobs by sharing one worker-scoped env dict.
    Column("env_json", String, nullable=True),
    Index("ix_job_status", "status"),
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


_NULLABLE_COLUMN_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    # table_name: [(column_name, sql_type_with_optional_default)]
    # Every entry MUST be nullable (or have a constant default) so SQLite
    # can ALTER TABLE ... ADD COLUMN without a full rewrite.
    "job": [
        # Added in Phase 4 (multi-fold queue). Existing DBs predate it.
        ("slot", "TEXT NOT NULL DEFAULT 'global'"),
        # Added in this PR (env-per-job). Stores os.environ JSON-encoded
        # at enqueue time; nullable so legacy rows still load.
        ("env_json", "TEXT"),
    ],
}


def _apply_nullable_migrations(engine: Engine) -> None:
    """Best-effort ALTER TABLE for columns added after the v1 schema.

    SQLite create_all is a no-op against pre-existing tables, so a
    user who installed the GUI before a column was introduced would
    otherwise get OperationalError ("no such column: env_json") on the
    next enqueue. We probe each table with PRAGMA table_info and add
    any missing columns idempotently. All entries in
    _NULLABLE_COLUMN_ADDITIONS must be nullable / defaulted; SQLite
    refuses non-NULL adds against existing rows.
    """
    with engine.connect() as conn:
        for table, expected in _NULLABLE_COLUMN_ADDITIONS.items():
            # If the table doesn't even exist yet, create_all will make it
            # with every column already present — skip the probe.
            tbl_exists = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not tbl_exists:
                continue
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for name, sql_type in expected:
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                    )
        conn.commit()


def init_db(cfg: GuiConfig) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    engine = _engine_for(cfg)
    # Apply migrations BEFORE create_all so the probe sees the pre-upgrade
    # schema. create_all is then a no-op for existing tables (they already
    # have the columns) and a fresh install for first-run users.
    _apply_nullable_migrations(engine)
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
