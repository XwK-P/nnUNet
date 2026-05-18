from __future__ import annotations

import sqlite3

from nnunetv2.gui.db import init_db


def test_init_db_creates_job_table(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    cols = {r[1] for r in raw.execute("PRAGMA table_info('job')")}
    raw.close()
    assert {"id", "kind", "args_json", "pid", "pgid", "status", "started_at",
            "ended_at", "exit_code", "log_path", "output_run_id", "created_by",
            "error_message"} <= cols


def test_job_table_indexed_on_status(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    indexes = {r[1] for r in raw.execute("PRAGMA index_list('job')")}
    raw.close()
    assert any("status" in i for i in indexes)
