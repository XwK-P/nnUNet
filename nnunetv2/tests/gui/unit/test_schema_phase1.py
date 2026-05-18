from __future__ import annotations

import sqlite3

from nnunetv2.gui.db import init_db


def test_init_db_creates_dataset_table(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    cols = {r[1] for r in raw.execute("PRAGMA table_info('dataset')")}
    raw.close()
    assert {"id", "dataset_id_int", "name", "raw_path", "preprocessed_path",
            "last_scanned_at", "fingerprint_json", "case_count", "modality_count"} <= cols


def test_init_db_creates_run_table(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    cols = {r[1] for r in raw.execute("PRAGMA table_info('run')")}
    raw.close()
    assert {"id", "dataset_id", "plans_name", "trainer_name", "configuration",
            "fold", "output_folder", "status", "source", "created_at",
            "last_seen_at", "tags_json", "notes"} <= cols


def test_run_table_indexed_on_dataset_id(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    indexes = {r[1] for r in raw.execute("PRAGMA index_list('run')")}
    raw.close()
    assert any("dataset_id" in i for i in indexes)
