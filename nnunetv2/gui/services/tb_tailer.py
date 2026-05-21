"""Read TensorBoard event files incrementally with tbparse.

Yields metric dicts: {kind: 'metric', key, step, value, wall_time}.
Image samples (Phase 3+): {kind: 'image_sample', tag, step, url}.
"""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import AsyncIterator, Optional


def read_all_metrics(event_dir: Path) -> list[dict]:
    """One-shot read of every scalar in `event_dir`.

    Non-finite scalar values (NaN / +/-Inf) are dropped at this
    boundary. TensorBoard can record those when training diverges and
    they would otherwise crash JSON serialisation downstream in
    /api/runs/{id}/metrics_history and /api/compare — returning 500 on
    exactly the unstable runs the user is trying to inspect.
    """
    from tbparse import SummaryReader
    if not event_dir.is_dir():
        return []
    try:
        reader = SummaryReader(str(event_dir), pivot=False, extra_columns={"wall_time"})
        df = reader.scalars
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for _, row in df.iterrows():
        value = float(row.get("value"))
        if not math.isfinite(value):
            continue
        out.append({
            "kind": "metric",
            "key": str(row.get("tag")),
            "step": int(row.get("step")),
            "value": value,
            "wall_time": float(row.get("wall_time", 0.0)),
        })
    return out


async def tail_metrics(
    event_dir: Path,
    *,
    poll_interval: float = 1.0,
    last_step_seen: Optional[dict[str, int]] = None,
) -> AsyncIterator[dict]:
    """Polling tailer; emits only metrics newer than last_step_seen[key]."""
    seen: dict[str, int] = dict(last_step_seen or {})
    while True:
        batch = read_all_metrics(event_dir)
        for m in batch:
            k = m["key"]
            if k not in seen or m["step"] > seen[k]:
                seen[k] = m["step"]
                yield m
        await asyncio.sleep(poll_interval)


def read_image_samples(event_dir: Path) -> list[dict]:
    """Best-effort read of image-tagged events; degrades to [] on failure."""
    from tbparse import SummaryReader
    if not event_dir.is_dir():
        return []
    try:
        reader = SummaryReader(str(event_dir), pivot=False)
        df = getattr(reader, "images", None)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for _, row in df.iterrows():
        out.append({
            "kind": "image_sample",
            "tag": str(row.get("tag")),
            "step": int(row.get("step")),
        })
    return out
