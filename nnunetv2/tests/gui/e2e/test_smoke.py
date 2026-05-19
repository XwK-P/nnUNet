"""E2E smoke: boot the GUI, navigate Dashboard → Datasets → Monitor."""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_dashboard_loads_and_shows_counts(page, gui_server_subprocess):
    page.goto(gui_server_subprocess)
    page.wait_for_selector("text=Dashboard")
    # Synthetic tree has 1 dataset + 1 run
    page.wait_for_selector("text=Datasets")
    # Cards include the word "preprocessed"
    page.wait_for_selector("text=preprocessed")


def test_datasets_page_lists_synthetic_dataset(page, gui_server_subprocess):
    page.goto(f"{gui_server_subprocess}/#/datasets")
    page.wait_for_selector("text=Dataset027_E2EDemo")
    page.click("text=Dataset027_E2EDemo")
    page.wait_for_selector("text=Plans")


def test_monitor_page_shows_synthetic_run(page, gui_server_subprocess):
    page.goto(f"{gui_server_subprocess}/#/monitor")
    page.wait_for_selector("text=3d_fullres")
    page.wait_for_selector("text=completed")
