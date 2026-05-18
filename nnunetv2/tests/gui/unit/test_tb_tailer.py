from __future__ import annotations

import asyncio

import pytest

from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir
from nnunetv2.gui.services.tb_tailer import read_all_metrics, tail_metrics


def test_read_all_metrics_simple(tmp_path):
    build_tb_event_dir(tmp_path, scalars={"train_loss": [(0, 1.0), (1, 0.5), (2, 0.25)]})
    metrics = read_all_metrics(tmp_path)
    keys = sorted(m["key"] for m in metrics)
    assert "train_loss" in keys
    losses = sorted([m for m in metrics if m["key"] == "train_loss"], key=lambda m: m["step"])
    assert [m["value"] for m in losses] == [1.0, 0.5, 0.25]


def test_read_all_metrics_empty(tmp_path):
    assert read_all_metrics(tmp_path) == []


@pytest.mark.asyncio
async def test_tail_metrics_picks_up_new(tmp_path):
    build_tb_event_dir(tmp_path, scalars={"train_loss": [(0, 1.0)]})
    seen: list[dict] = []

    async def producer():
        await asyncio.sleep(0.1)
        build_tb_event_dir(tmp_path, scalars={"train_loss": [(1, 0.7)]})

    async def consumer():
        async for m in tail_metrics(tmp_path, poll_interval=0.05):
            seen.append(m)
            if any(s["step"] == 1 for s in seen):
                return

    await asyncio.wait_for(asyncio.gather(producer(), consumer()), timeout=3.0)
    assert any(s["step"] == 1 and s["key"] == "train_loss" for s in seen)
