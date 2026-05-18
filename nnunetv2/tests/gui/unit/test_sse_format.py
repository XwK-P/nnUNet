from __future__ import annotations

import asyncio
import json

import pytest

from nnunetv2.gui.services.sse import sse_format, RunStreamHub


def test_sse_format_metric():
    out = sse_format("metric", {"key": "loss", "step": 1, "value": 0.5})
    assert out.startswith("event: metric\n")
    assert "data: " in out
    payload = out.split("data: ", 1)[1].strip()
    assert json.loads(payload) == {"key": "loss", "step": 1, "value": 0.5}
    assert out.endswith("\n\n")


def test_sse_format_log():
    out = sse_format("log", {"line": "hello", "ts": 0.0})
    assert out.startswith("event: log\n")


@pytest.mark.asyncio
async def test_hub_broadcast():
    hub = RunStreamHub()
    q1 = hub.subscribe("r1")
    q2 = hub.subscribe("r1")
    await hub.publish("r1", "metric", {"k": 1})
    a = await asyncio.wait_for(q1.get(), 1.0)
    b = await asyncio.wait_for(q2.get(), 1.0)
    assert a == b
    assert a[0] == "metric"
    hub.unsubscribe("r1", q1)
    hub.unsubscribe("r1", q2)


@pytest.mark.asyncio
async def test_hub_isolated_per_run():
    hub = RunStreamHub()
    q1 = hub.subscribe("r1")
    q2 = hub.subscribe("r2")
    await hub.publish("r1", "metric", {"v": 1})
    a = await asyncio.wait_for(q1.get(), 1.0)
    assert a[1]["v"] == 1
    assert q2.empty()
