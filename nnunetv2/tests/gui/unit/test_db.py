from __future__ import annotations

import sqlite3

from sqlalchemy import text

from nnunetv2.gui.db import init_db, session_scope


def test_init_db_creates_state_dir_and_db(gui_config):
    assert not gui_config.state_db.exists()

    init_db(gui_config)

    assert gui_config.state_dir.is_dir()
    assert gui_config.state_db.is_file()


def test_init_db_creates_settings_table(gui_config):
    init_db(gui_config)

    raw = sqlite3.connect(gui_config.state_db)
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    raw.close()

    assert "settings" in tables


def test_init_db_uses_wal_mode(gui_config):
    init_db(gui_config)

    raw = sqlite3.connect(gui_config.state_db)
    mode = raw.execute("PRAGMA journal_mode").fetchone()[0]
    raw.close()

    assert mode.lower() == "wal"


def test_session_scope_round_trips_a_setting(gui_config):
    init_db(gui_config)

    with session_scope(gui_config) as s:
        s.execute(text("INSERT INTO settings(key, value) VALUES (:k, :v)"),
                  {"k": "theme", "v": "dark"})

    with session_scope(gui_config) as s:
        row = s.execute(text("SELECT value FROM settings WHERE key=:k"),
                        {"k": "theme"}).first()

    assert row is not None
    assert row[0] == "dark"


def test_init_db_is_idempotent(gui_config):
    init_db(gui_config)
    init_db(gui_config)  # no exception, no data loss

    with session_scope(gui_config) as s:
        n = s.execute(text("SELECT count(*) FROM settings")).first()[0]

    assert n == 0
