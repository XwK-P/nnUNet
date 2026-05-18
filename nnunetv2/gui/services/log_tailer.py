"""Async line tailer for nnUNet training log files.

Polls the file for size changes, yields newline-terminated lines.
Robust to file-not-yet-created and to truncation (handled by reopening on shrink).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator


async def tail_lines(
    path: Path,
    *,
    poll_interval: float = 0.5,
    stop_on_eof: bool = False,
) -> AsyncIterator[str]:
    """Yield lines as they appear in `path`. Survives the file not existing yet."""
    pos = 0
    buf = b""
    last_size = -1
    while True:
        if not path.is_file():
            if stop_on_eof:
                return
            await asyncio.sleep(poll_interval)
            continue
        size = path.stat().st_size
        if size < pos:
            # Truncated or rotated — start over.
            pos = 0
            buf = b""
        if size > pos:
            with path.open("rb") as f:
                f.seek(pos)
                chunk = f.read(size - pos)
                pos = size
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.decode("utf-8", errors="replace").rstrip("\r")
            last_size = size
        else:
            if stop_on_eof and last_size == size:
                # Flush any tail bytes without trailing newline.
                if buf:
                    yield buf.decode("utf-8", errors="replace").rstrip("\r")
                return
            await asyncio.sleep(poll_interval)
