"""SSE format helpers + per-run pub/sub hub."""
from __future__ import annotations

import asyncio
import json
from typing import Any


def sse_format(event: str, data: Any) -> str:
    """Serialize to the SSE wire format. Multi-line JSON kept on one data: line."""
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


class RunStreamHub:
    """Per-run pub/sub for the monitor SSE multiplexer.

    Each subscriber gets its own bounded asyncio.Queue; publishers fan out
    by iterating the hub's current subscriber list.
    """

    def __init__(self, maxsize: int = 1024) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._maxsize = maxsize

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.setdefault(run_id, set()).add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        if run_id in self._subs:
            self._subs[run_id].discard(q)
            if not self._subs[run_id]:
                del self._subs[run_id]

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # Drop oldest on slow consumer
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait((event, data))
                except asyncio.QueueFull:
                    pass

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subs.get(run_id, ()))
