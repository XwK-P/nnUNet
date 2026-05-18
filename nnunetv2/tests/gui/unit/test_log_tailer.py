from __future__ import annotations

import asyncio

import pytest

from nnunetv2.gui.services.log_tailer import tail_lines


@pytest.mark.asyncio
async def test_tail_picks_up_existing_lines(tmp_path):
    log = tmp_path / "training_log.txt"
    log.write_text("hello\nworld\n")
    out: list[str] = []
    async def consume():
        async for line in tail_lines(log, poll_interval=0.01, stop_on_eof=True):
            out.append(line)
    await asyncio.wait_for(consume(), timeout=2.0)
    assert out == ["hello", "world"]


@pytest.mark.asyncio
async def test_tail_picks_up_appends(tmp_path):
    log = tmp_path / "training_log.txt"
    log.write_text("first\n")
    seen: list[str] = []

    async def producer():
        await asyncio.sleep(0.05)
        with log.open("a") as f:
            f.write("second\n")
            f.flush()
        await asyncio.sleep(0.05)
        with log.open("a") as f:
            f.write("third\n")
            f.flush()

    async def consumer():
        async for line in tail_lines(log, poll_interval=0.01):
            seen.append(line)
            if len(seen) >= 3:
                return

    await asyncio.wait_for(asyncio.gather(producer(), consumer()), timeout=2.0)
    assert seen == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_tail_handles_missing_file(tmp_path):
    log = tmp_path / "not_yet.txt"
    seen: list[str] = []

    async def producer():
        await asyncio.sleep(0.05)
        log.write_text("a\nb\n")

    async def consumer():
        async for line in tail_lines(log, poll_interval=0.01):
            seen.append(line)
            if len(seen) >= 2:
                return

    await asyncio.wait_for(asyncio.gather(producer(), consumer()), timeout=2.0)
    assert seen == ["a", "b"]
