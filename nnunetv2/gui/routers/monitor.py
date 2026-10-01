"""Multiplexed SSE endpoint for live run events."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from nnunetv2.gui.services.log_tailer import tail_lines
from nnunetv2.gui.services.sse import RunStreamHub, sse_format
from nnunetv2.gui.services.tb_tailer import read_all_metrics, read_image_samples, tail_metrics
from nnunetv2.gui.state.runs import get_run


def make_router() -> APIRouter:
    router = APIRouter(prefix="/sse/runs", tags=["monitor"])

    @router.get("/{run_id:path}/events")
    async def stream_events(run_id: str, request: Request) -> StreamingResponse:
        cfg = request.app.state.gui_config
        hub: RunStreamHub = request.app.state.run_stream_hub
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        fold_dir = Path(run.output_folder)
        tb_dir = fold_dir / "tensorboard"
        log_glob = list(fold_dir.glob("training_log_*.txt"))
        log_path = log_glob[0] if log_glob else None

        async def event_stream() -> AsyncIterator[str]:
            # 1. Replay current metric history so the client gets full curves,
            #    and remember the last step per key so the live tail doesn't
            #    re-emit them on its first poll.
            yield sse_format("status", {"phase": "replay_start"})
            replayed_max_step: dict[str, int] = {}
            for m in read_all_metrics(tb_dir):
                yield sse_format("metric", m)
                k = m["key"]
                step = m["step"]
                if step > replayed_max_step.get(k, -1):
                    replayed_max_step[k] = step
            yield sse_format("status", {"phase": "replay_done"})

            # 2. Live tail via two cooperating tasks. We push into a single queue.
            q: asyncio.Queue = asyncio.Queue(maxsize=1024)
            stop = asyncio.Event()

            async def pump_metrics() -> None:
                try:
                    async for m in tail_metrics(
                        tb_dir,
                        poll_interval=1.0,
                        last_step_seen=dict(replayed_max_step),
                    ):
                        if stop.is_set():
                            return
                        await q.put(("metric", m))
                except Exception as e:
                    await q.put(("status", {"phase": "tb_tailer_error", "message": str(e)}))

            async def pump_logs() -> None:
                if log_path is None:
                    return
                try:
                    async for line in tail_lines(log_path, poll_interval=0.5):
                        if stop.is_set():
                            return
                        await q.put(("log", {"line": line, "ts": time.time()}))
                except Exception as e:
                    await q.put(("status", {"phase": "log_tailer_error", "message": str(e)}))

            # Periodically poll the TB event dir for image-summary entries
            # and emit any newly-seen (tag, step) pair. This is best-effort:
            # tbparse only exposes shape, not bytes, so we route subscribers
            # to the existing /api/runs/{id}/images/{step}/{tag} URL (Phase 6
            # in the design doc) — we just announce that one exists.
            async def pump_image_samples() -> None:
                seen: set[tuple[str, int]] = set()
                # Replay everything that's already on disk once so the client
                # has an initial inventory.
                try:
                    for s in read_image_samples(tb_dir):
                        key = (s["tag"], s["step"])
                        if key in seen:
                            continue
                        seen.add(key)
                        await q.put(("image_sample", s))
                except Exception as e:
                    await q.put(
                        ("status", {"phase": "image_sample_initial_error", "message": str(e)})
                    )
                # Then diff every 2s. Image-sample writes are infrequent
                # (every N epochs) so a slower poll is fine.
                while not stop.is_set():
                    try:
                        await asyncio.sleep(2.0)
                        if stop.is_set():
                            return
                        for s in read_image_samples(tb_dir):
                            key = (s["tag"], s["step"])
                            if key in seen:
                                continue
                            seen.add(key)
                            await q.put(("image_sample", s))
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        await q.put(
                            ("status", {"phase": "image_sample_tailer_error", "message": str(e)})
                        )

            tasks = [
                asyncio.create_task(pump_metrics()),
                asyncio.create_task(pump_logs()),
                asyncio.create_task(pump_image_samples()),
            ]
            # Heartbeat every HEARTBEAT_INTERVAL_S of quiet, but poll
            # is_disconnected more often so TestClient + production proxies
            # both notice disconnects within ~1s instead of 15s.
            HEARTBEAT_INTERVAL_S = 15.0
            DISCONNECT_POLL_S = 1.0
            quiet_for = 0.0
            try:
                while True:
                    if await request.is_disconnected():
                        stop.set()
                        break
                    try:
                        ev, data = await asyncio.wait_for(q.get(), timeout=DISCONNECT_POLL_S)
                        yield sse_format(ev, data)
                        quiet_for = 0.0
                    except asyncio.TimeoutError:
                        quiet_for += DISCONNECT_POLL_S
                        if quiet_for >= HEARTBEAT_INTERVAL_S:
                            # Heartbeat — keeps proxies and clients alive.
                            yield ":\n\n"
                            quiet_for = 0.0
            finally:
                stop.set()
                for t in tasks:
                    t.cancel()
                for t in tasks:
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router
