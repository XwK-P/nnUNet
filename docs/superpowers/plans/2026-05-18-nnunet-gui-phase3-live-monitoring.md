# nnU-Net GUI — Phase 3 (Live Monitoring) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can launch any nnUNet CLI command in a terminal and watch it live in the browser. Streaming metric curves, log tail, and image samples land on the Monitor route. The Jobs page becomes a read-only registry that picks up GUI-tracked records, ready for Phase 4 to add write actions.

**Architecture:** Two long-running tailers per active run — `log_tailer.py` (line-oriented `aiofiles` reader on `training_log_*.txt`) and `tb_tailer.py` (`tbparse` incremental scalar/image read against the per-run `tensorboard/` event files). Both emit to a single multiplexed SSE endpoint `/sse/runs/{run_id:path}/events` that fans the event-typed stream (`event: metric`, `event: log`, `event: image_sample`, `event: status`) to all subscribers. A `state/jobs.py` table records GUI-tracked jobs (read-only in Phase 3 — populated by `discovery.reconcile_jobs` when scanning the run filesystem for evidence of in-flight training; Phase 4 will add the launcher to write the same rows). The Monitor page upgrades from a static table to live `uPlot` charts + log pane + image-sample strip.

**Tech Stack:** Adds Python `tbparse` (read TF event files without TF) and `uplot` (already declared in spec; verify and add as npm dep). Re-uses `watchfiles` (already a backend dep). No nnUNet core changes.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "Live metrics pipeline", "Log streaming", and "UI Pages" → "Monitor". Architectural decisions: single multiplexed SSE per run via `event:` typing; tailers self-disable after 5 consecutive failures.

**TDD discipline:** Tailers tested against synthetic event files + log files written by tests. SSE endpoints tested via FastAPI `TestClient` consuming the stream until end-of-stream (server-side test signals close). One commit per task.

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/services/log_tailer.py` | `LogTailer` async iterator over a file, debounce + EOF retry, emits `{kind:'log', line, ts}` |
| `nnunetv2/gui/services/tb_tailer.py` | `TbTailer` async iterator over a `tensorboard/` directory; wraps `tbparse.SummaryReader`, emits `{kind:'metric',key,step,value,wall_time}` and `{kind:'image_sample',tag,step,url}` |
| `nnunetv2/gui/services/sse.py` | Helpers: `sse_format(event, data)`, broadcast registry `RunStreamHub` (per-run pub/sub) |
| `nnunetv2/gui/state/jobs.py` | `Job` Pydantic model (no PID logic in Phase 3 — adds `started_at`/`status` columns; full lifecycle lands Phase 4); `list_jobs`, `get_job`, `upsert_job` repository functions |
| `nnunetv2/gui/db.py` (mod) | Schema for `job` table (matches the spec) |
| `nnunetv2/gui/state/discovery.py` (mod) | Add `scan_active_runs(cfg)` returning runs that look in-flight (no `checkpoint_final.pth` but `tensorboard/` exists and was touched in last 10 min) |
| `nnunetv2/gui/routers/monitor.py` | `GET /sse/runs/{run_id:path}/events` — single multiplexed SSE stream |
| `nnunetv2/gui/routers/runs.py` (mod) | Add `/{run_id:path}/metrics_history` (replay cache from sqlite for charts on page load) and `/{run_id:path}/log_tail?bytes=N` for non-SSE one-shot fetch |
| `nnunetv2/gui/routers/jobs.py` | `GET /api/jobs`, `GET /api/jobs/{id}` (read-only). Phase 4 will add write actions. |
| `nnunetv2/gui/server.py` (mod) | Include new routers; init the per-app `RunStreamHub`; on shutdown, cancel any per-run tailer tasks. |
| `nnunetv2/tests/gui/unit/test_log_tailer.py` | Async tests against a `tmp_path` log file |
| `nnunetv2/tests/gui/unit/test_tb_tailer.py` | Against a fixture event-file directory; uses `tbparse`'s programmatic write API or a small helper |
| `nnunetv2/tests/gui/unit/test_sse_format.py` | Pure function tests |
| `nnunetv2/tests/gui/unit/test_jobs_repo.py` | Job repo CRUD |
| `nnunetv2/tests/gui/api/test_monitor_sse.py` | TestClient + EventSource-style stream consumption |
| `nnunetv2/tests/gui/api/test_jobs_api.py` | Jobs router contract |
| `nnunetv2/tests/gui/fixtures/builders.py` (mod) | `build_tb_event_dir(out, scalars=[...], image_samples=[...])` helper that writes synthetic event files compatible with tbparse |
| `frontend/src/lib/types.ts` (mod) | `MetricEvent`, `LogEvent`, `ImageSampleEvent`, `RunStatusEvent`, `Job` types |
| `frontend/src/lib/api.ts` (mod) | `getMetricsHistory`, `getLogTail`, `getJobs`, `getJob` |
| `frontend/src/lib/sse.ts` | `connectRunEvents(runId)` returns an EventSource with typed-listener helpers |
| `frontend/src/lib/charts/LineChart.svelte` | uPlot wrapper, fixed-width ring buffer of N=2000 points |
| `frontend/src/lib/stores/runStream.ts` | Reactive store for a single run's metric history + log buffer + image samples |
| `frontend/src/components/CurvesPanel.svelte` | Grid of LineCharts (train_loss / val_loss / mean_fg_dice / lr / epoch_duration) |
| `frontend/src/components/LogPanel.svelte` | Auto-scrolling terminal-style log view (50k-line ring buffer) |
| `frontend/src/components/ImageSamplesPanel.svelte` | Strip of recent image-sample triplets (image url from SSE) |
| `frontend/src/components/RunDetail.svelte` (mod) | Add tabs: Predictions (Phase 2) / Curves / Log / Image samples |
| `frontend/src/routes/Jobs.svelte` (mod) | Replace stub with a sortable `JobsTable` (read-only) |
| `frontend/src/lib/stores/jobs.ts` | Async store of `Job[]` |
| `frontend/src/components/JobsTable.svelte` | Read-only table; expandable rows show log tail (one-shot fetch, no live yet) |
| `pyproject.toml` (mod) | Add `tbparse` to `[gui]` extra |
| `frontend/package.json` (mod) | Add `uplot` |

---

## Task 1: Declare new deps + `job` table schema (TDD)

**Files:**
- Modify: `pyproject.toml`
- Modify: `frontend/package.json`
- Modify: `nnunetv2/gui/db.py`
- Create: `nnunetv2/tests/gui/unit/test_jobs_schema.py`

- [ ] **Step 1: Add `tbparse` and `uplot`**

```bash
pip install tbparse  # check it imports
cd frontend && npm install --save uplot
```

Add to `pyproject.toml` `[gui]` extra: `"tbparse>=0.0.8"`.

- [ ] **Step 2: Write the failing schema test**

```python
# nnunetv2/tests/gui/unit/test_jobs_schema.py
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
```

- [ ] **Step 3: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_jobs_schema.py -v
```

- [ ] **Step 4: Add `job_table` to `nnunetv2/gui/db.py`**

```python
job_table = Table(
    "job",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String, nullable=False),
    Column("args_json", String, nullable=False),
    Column("pid", Integer, nullable=True),
    Column("pgid", Integer, nullable=True),
    Column("status", String, nullable=False),
    Column("started_at", DateTime, nullable=True),
    Column("ended_at", DateTime, nullable=True),
    Column("exit_code", Integer, nullable=True),
    Column("log_path", String, nullable=True),
    Column("output_run_id", String, nullable=True),
    Column("created_by", String, nullable=True),
    Column("error_message", String, nullable=True),
    Index("ix_job_status", "status"),
)
```

- [ ] **Step 5: Run; confirm pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_jobs_schema.py -v
git add pyproject.toml frontend/package.json frontend/package-lock.json nnunetv2/gui/db.py nnunetv2/tests/gui/unit/test_jobs_schema.py
git commit -m "gui(db): job table schema + tbparse/uplot deps for Phase 3 monitoring"
```

---

## Task 2: `state.jobs` repository (TDD)

**Files:**
- Create: `nnunetv2/gui/state/jobs.py`
- Create: `nnunetv2/tests/gui/unit/test_jobs_repo.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_jobs_repo.py
from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.jobs import (
    Job, JobFilter, insert_job, get_job, list_jobs, update_job_status,
)


def _make(**ov) -> Job:
    base = Job(
        id=None, kind="train", args_json='{"dataset_id":27}',
        pid=None, pgid=None, status="queued",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None,
    )
    return base.model_copy(update=ov)


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_jobs(gui_config, JobFilter()) == []


def test_insert_returns_id(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make())
    assert j.id is not None
    fetched = get_job(gui_config, j.id)
    assert fetched.kind == "train"


def test_filter_by_status(gui_config):
    init_db(gui_config)
    insert_job(gui_config, _make(status="running"))
    insert_job(gui_config, _make(status="completed"))
    running = list_jobs(gui_config, JobFilter(status="running"))
    assert len(running) == 1


def test_filter_by_kind(gui_config):
    init_db(gui_config)
    insert_job(gui_config, _make(kind="train"))
    insert_job(gui_config, _make(kind="predict"))
    train = list_jobs(gui_config, JobFilter(kind="train"))
    assert len(train) == 1


def test_update_status(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="starting", pid=123))
    update_job_status(gui_config, j.id, status="running")
    j2 = get_job(gui_config, j.id)
    assert j2.status == "running"
    assert j2.pid == 123  # unchanged


def test_update_status_with_terminal_fields(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make(status="running"))
    ended = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    update_job_status(gui_config, j.id, status="completed", ended_at=ended, exit_code=0)
    j2 = get_job(gui_config, j.id)
    assert j2.status == "completed"
    assert j2.exit_code == 0
    assert j2.ended_at is not None
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_jobs_repo.py -v
```

- [ ] **Step 3: Implement `state/jobs.py`**

```python
"""Job records and lifecycle. Phase 3 = read-only listing; Phase 4 adds launcher."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import job_table, session_scope


class Job(BaseModel):
    id: Optional[int]
    kind: str
    args_json: str
    pid: Optional[int]
    pgid: Optional[int]
    status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    exit_code: Optional[int]
    log_path: Optional[str]
    output_run_id: Optional[str]
    created_by: Optional[str]
    error_message: Optional[str]


class JobFilter(BaseModel):
    kind: Optional[str] = None
    status: Optional[str] = None


def _row_to_model(row) -> Job:
    return Job(
        id=row.id, kind=row.kind, args_json=row.args_json,
        pid=row.pid, pgid=row.pgid, status=row.status,
        started_at=row.started_at, ended_at=row.ended_at,
        exit_code=row.exit_code, log_path=row.log_path,
        output_run_id=row.output_run_id, created_by=row.created_by,
        error_message=row.error_message,
    )


def list_jobs(cfg: GuiConfig, flt: JobFilter) -> list[Job]:
    stmt = select(job_table)
    if flt.kind:
        stmt = stmt.where(job_table.c.kind == flt.kind)
    if flt.status:
        stmt = stmt.where(job_table.c.status == flt.status)
    stmt = stmt.order_by(job_table.c.id.desc())
    with session_scope(cfg) as s:
        rows = s.execute(stmt).all()
    return [_row_to_model(r) for r in rows]


def get_job(cfg: GuiConfig, job_id: int) -> Optional[Job]:
    with session_scope(cfg) as s:
        row = s.execute(select(job_table).where(job_table.c.id == job_id)).first()
    return _row_to_model(row) if row else None


def insert_job(cfg: GuiConfig, job: Job) -> Job:
    values = job.model_dump()
    values.pop("id", None)  # SQLite assigns
    with session_scope(cfg) as s:
        result = s.execute(job_table.insert().values(**values))
        new_id = result.inserted_primary_key[0]
    fetched = get_job(cfg, new_id)
    assert fetched is not None
    return fetched


def update_job_status(
    cfg: GuiConfig, job_id: int, *,
    status: Optional[str] = None,
    pid: Optional[int] = None,
    pgid: Optional[int] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    exit_code: Optional[int] = None,
    error_message: Optional[str] = None,
    log_path: Optional[str] = None,
    output_run_id: Optional[str] = None,
) -> None:
    update_values = {k: v for k, v in {
        "status": status, "pid": pid, "pgid": pgid,
        "started_at": started_at, "ended_at": ended_at,
        "exit_code": exit_code, "error_message": error_message,
        "log_path": log_path, "output_run_id": output_run_id,
    }.items() if v is not None}
    if not update_values:
        return
    with session_scope(cfg) as s:
        s.execute(job_table.update().where(job_table.c.id == job_id).values(**update_values))
```

- [ ] **Step 4: Run; confirm pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_jobs_repo.py -v
git add nnunetv2/gui/state/jobs.py nnunetv2/tests/gui/unit/test_jobs_repo.py
git commit -m "gui(state): Job model + repository (insert/get/list/update_status)"
```

---

## Task 3: Log tailer (TDD)

**Files:**
- Create: `nnunetv2/gui/services/log_tailer.py`
- Create: `nnunetv2/tests/gui/unit/test_log_tailer.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_log_tailer.py
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
```

- [ ] **Step 2: Confirm failure** (`pytest-asyncio` may need adding; check existing test conf)

If `pytest-asyncio` is not yet in `[gui]` test deps, add it under `[project.optional-dependencies] dev` or a `tests` extra, plus configure `asyncio_mode = "auto"` in `pyproject.toml`.

- [ ] **Step 3: Implement**

```python
# nnunetv2/gui/services/log_tailer.py
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
```

- [ ] **Step 4: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/unit/test_log_tailer.py -v
```

Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/services/log_tailer.py nnunetv2/tests/gui/unit/test_log_tailer.py
git commit -m "gui(services): async line tailer for training logs"
```

---

## Task 4: TB tailer (TDD)

**Files:**
- Create: `nnunetv2/gui/services/tb_tailer.py`
- Create: `nnunetv2/tests/gui/unit/test_tb_tailer.py`
- Modify: `nnunetv2/tests/gui/fixtures/builders.py` — `build_tb_event_dir`

- [ ] **Step 1: Builder helper for synthetic event files**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_tb_event_dir(
    out: Path,
    *,
    scalars: dict[str, list[tuple[int, float]]] | None = None,
) -> Path:
    """Write a minimal TensorBoard event file using torch.utils.tensorboard.SummaryWriter."""
    from torch.utils.tensorboard import SummaryWriter
    out.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(log_dir=str(out))
    for key, points in (scalars or {}).items():
        for step, val in points:
            writer.add_scalar(key, val, global_step=step)
    writer.flush()
    writer.close()
    return out
```

Note: nnUNet already depends on `torch.utils.tensorboard` for its existing logger, so no new import surface. If `torch` ever moves to optional, this fixture should be skipped.

- [ ] **Step 2: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_tb_tailer.py
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
```

- [ ] **Step 3: Confirm failure**

```bash
pytest nnunetv2/tests/gui/unit/test_tb_tailer.py -v
```

- [ ] **Step 4: Implement `tb_tailer.py`**

```python
# nnunetv2/gui/services/tb_tailer.py
"""Read TensorBoard event files incrementally with tbparse.

Yields metric dicts: {kind: 'metric', key, step, value, wall_time}.
Image samples (Phase 3+): {kind: 'image_sample', tag, step, url}.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator, Optional


def read_all_metrics(event_dir: Path) -> list[dict]:
    """One-shot read of every scalar in `event_dir`."""
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
        out.append({
            "kind": "metric",
            "key": str(row.get("tag")),
            "step": int(row.get("step")),
            "value": float(row.get("value")),
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
```

- [ ] **Step 5: Run; confirm pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_tb_tailer.py -v
git add nnunetv2/gui/services/tb_tailer.py nnunetv2/gui/services/__init__.py nnunetv2/tests/gui/unit/test_tb_tailer.py nnunetv2/tests/gui/fixtures/builders.py
git commit -m "gui(services): tbparse-backed scalar tailer + one-shot reader"
```

---

## Task 5: SSE format + `RunStreamHub` pub/sub (TDD)

**Files:**
- Create: `nnunetv2/gui/services/sse.py`
- Create: `nnunetv2/tests/gui/unit/test_sse_format.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_sse_format.py
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
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
# nnunetv2/gui/services/sse.py
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
```

- [ ] **Step 4: Run; confirm pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_sse_format.py -v
git add nnunetv2/gui/services/sse.py nnunetv2/tests/gui/unit/test_sse_format.py
git commit -m "gui(services): SSE wire-format helper + RunStreamHub pub/sub"
```

---

## Task 6: Monitor SSE endpoint (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/monitor.py`
- Modify: `nnunetv2/gui/server.py` (attach `RunStreamHub` to app.state, start per-run tailers on demand, include router)
- Create: `nnunetv2/tests/gui/api/test_monitor_sse.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/api/test_monitor_sse.py
from __future__ import annotations

import json

import pytest


@pytest.fixture
def run_with_tb(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir
    fold_dir = (populated_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    build_tb_event_dir(fold_dir / "tensorboard",
                       scalars={"train_loss": [(0, 1.0), (1, 0.7), (2, 0.5)]})
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def _parse_one_sse_event(raw: str) -> tuple[str, dict]:
    lines = raw.strip().split("\n")
    ev = next(l[len("event: "):] for l in lines if l.startswith("event: "))
    data_line = next(l[len("data: "):] for l in lines if l.startswith("data: "))
    return ev, json.loads(data_line)


def test_sse_endpoint_returns_metric_events(run_with_tb):
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    # The stream is long-lived; we read a few events and break.
    with run_with_tb.stream("GET", f"/sse/runs/{run_id}/events") as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        events_seen: list[tuple[str, dict]] = []
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                raw_event, buf = buf.split("\n\n", 1)
                events_seen.append(_parse_one_sse_event(raw_event + "\n\n"))
                if len(events_seen) >= 3:
                    break
            if len(events_seen) >= 3:
                break
        kinds = {e[0] for e in events_seen}
        # At least one of the events should be a metric replay
        assert "metric" in kinds


def test_sse_endpoint_404_for_unknown_run(client):
    with client.stream("GET", "/sse/runs/Dataset999_X/x__y__z/fold_0/events") as r:
        assert r.status_code == 404
```

- [ ] **Step 2: Implement `routers/monitor.py`**

```python
# nnunetv2/gui/routers/monitor.py
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
from nnunetv2.gui.services.tb_tailer import read_all_metrics, tail_metrics
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
            # 1. Replay current metric history so the client gets full curves.
            yield sse_format("status", {"phase": "replay_start"})
            for m in read_all_metrics(tb_dir):
                yield sse_format("metric", m)
            yield sse_format("status", {"phase": "replay_done"})

            # 2. Live tail via two cooperating tasks. We push into a single queue.
            q: asyncio.Queue = asyncio.Queue(maxsize=1024)
            stop = asyncio.Event()

            async def pump_metrics() -> None:
                try:
                    async for m in tail_metrics(tb_dir, poll_interval=1.0):
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

            tasks = [asyncio.create_task(pump_metrics()), asyncio.create_task(pump_logs())]
            try:
                while True:
                    if await request.is_disconnected():
                        stop.set()
                        break
                    try:
                        ev, data = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield sse_format(ev, data)
                    except asyncio.TimeoutError:
                        # Heartbeat — keeps proxies and clients alive.
                        yield ":\n\n"
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
```

- [ ] **Step 3: Wire into `create_app`**

In `nnunetv2/gui/server.py`:

```python
from nnunetv2.gui.routers import monitor as monitor_router
from nnunetv2.gui.services.sse import RunStreamHub
# ...
def create_app(cfg: GuiConfig) -> FastAPI:
    # ... existing logic ...
    app.state.run_stream_hub = RunStreamHub()
    app.include_router(monitor_router.make_router())
```

- [ ] **Step 4: Run; confirm pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_monitor_sse.py -v
git add nnunetv2/gui/routers/monitor.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_monitor_sse.py
git commit -m "gui(api): SSE multiplexer /sse/runs/{id}/events (metric+log+status)"
```

---

## Task 7: `/api/runs/{id}/metrics_history` + `/log_tail` (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/runs.py`
- Modify: `nnunetv2/tests/gui/api/test_runs_api.py`

- [ ] **Step 1: Append failing tests**

```python
def test_metrics_history_replay(run_with_tb):
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = run_with_tb.get(f"/api/runs/{run_id}/metrics_history")
    assert r.status_code == 200
    body = r.json()
    keys = {m["key"] for m in body}
    assert "train_loss" in keys


def test_log_tail_returns_tail(populated_paths, monkeypatch):
    fold_dir = (populated_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    (fold_dir / "training_log_x.txt").write_text("a\nb\nc\nd\ne\n")
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get("/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/log_tail?bytes=4")
    assert r.status_code == 200
    assert r.text.endswith("e\n") or r.text.endswith("d\ne\n")
```

(The `run_with_tb` fixture should live in `nnunetv2/tests/gui/conftest.py`.)

- [ ] **Step 2: Implement endpoints**

Inside `routers/runs.py`'s `make_router()`:

```python
    @router.get("/{run_id:path}/metrics_history")
    def metrics_history(run_id: str, request: Request) -> list[dict]:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        from nnunetv2.gui.services.tb_tailer import read_all_metrics
        return read_all_metrics(Path(run.output_folder) / "tensorboard")

    @router.get("/{run_id:path}/log_tail", response_class=PlainTextResponse)
    def log_tail(run_id: str, request: Request, bytes: int = 8192) -> str:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        for log in Path(run.output_folder).glob("training_log_*.txt"):
            size = log.stat().st_size
            with log.open("rb") as f:
                f.seek(max(0, size - bytes))
                data = f.read()
            return data.decode("utf-8", errors="replace")
        return ""
```

Add: `from fastapi.responses import PlainTextResponse`.

- [ ] **Step 3: Run; commit**

```bash
pytest nnunetv2/tests/gui/api/test_runs_api.py -v
git add nnunetv2/gui/routers/runs.py nnunetv2/tests/gui/api/test_runs_api.py nnunetv2/tests/gui/conftest.py
git commit -m "gui(api): metrics_history + log_tail one-shot endpoints"
```

---

## Task 8: Read-only Jobs router + discovery of in-flight runs (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/jobs.py`
- Modify: `nnunetv2/gui/state/discovery.py` — add `scan_active_runs` for marking runs `training`
- Modify: `nnunetv2/gui/server.py` — include router
- Create: `nnunetv2/tests/gui/api/test_jobs_api.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/api/test_jobs_api.py
def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_job_404(client):
    r = client.get("/api/jobs/9999")
    assert r.status_code == 404


def test_list_jobs_after_insert(gui_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.gui.state.jobs import Job, insert_job
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    app = create_app(cfg)
    insert_job(cfg, Job(id=None, kind="train", args_json="{}", pid=None, pgid=None,
                        status="completed", started_at=None, ended_at=None,
                        exit_code=0, log_path=None, output_run_id=None,
                        created_by="cli", error_message=None))
    c = TestClient(app)
    r = c.get("/api/jobs")
    assert r.status_code == 200
    assert len(r.json()) == 1
```

- [ ] **Step 2: Implement `routers/jobs.py`**

```python
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from nnunetv2.gui.state.jobs import Job, JobFilter, list_jobs, get_job


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("", response_model=list[Job])
    def list_all(request: Request,
                  kind: Optional[str] = None,
                  status: Optional[str] = None) -> list[Job]:
        return list_jobs(request.app.state.gui_config, JobFilter(kind=kind, status=status))

    @router.get("/{job_id}", response_model=Job)
    def get_one(job_id: int, request: Request) -> Job:
        j = get_job(request.app.state.gui_config, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return j

    return router
```

- [ ] **Step 3: Wire into server.py + run/commit**

```python
from nnunetv2.gui.routers import jobs as jobs_router
# ...
app.include_router(jobs_router.make_router())
```

```bash
pytest nnunetv2/tests/gui/api/test_jobs_api.py -v
git add nnunetv2/gui/routers/jobs.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_jobs_api.py
git commit -m "gui(api): /api/jobs read-only listing + detail"
```

---

## Task 9: Frontend SSE client + run-stream store (TDD)

**Files:**
- Create: `frontend/src/lib/sse.ts`
- Create: `frontend/src/lib/stores/runStream.ts`
- Create: `frontend/src/lib/stores/runStream.test.ts`
- Modify: `frontend/src/lib/types.ts`

- [ ] **Step 1: Type additions**

```ts
// frontend/src/lib/types.ts
export interface MetricEvent {
  kind: 'metric'; key: string; step: number; value: number; wall_time: number;
}
export interface LogEvent { kind: 'log'; line: string; ts: number; }
export interface ImageSampleEvent { kind: 'image_sample'; tag: string; step: number; url?: string; }
export interface RunStatusEvent { kind: 'status'; phase: string; message?: string; }
export type RunEvent = MetricEvent | LogEvent | ImageSampleEvent | RunStatusEvent;

export interface Job {
  id: number; kind: string; args_json: string;
  pid: number | null; pgid: number | null; status: string;
  started_at: string | null; ended_at: string | null;
  exit_code: number | null; log_path: string | null;
  output_run_id: string | null; created_by: string | null;
  error_message: string | null;
}
```

- [ ] **Step 2: `lib/sse.ts`**

```ts
import type { RunEvent } from './types';

export interface RunEventStream {
  onMetric(cb: (e: Extract<RunEvent, {kind:'metric'}>) => void): void;
  onLog(cb: (e: Extract<RunEvent, {kind:'log'}>) => void): void;
  onImageSample(cb: (e: Extract<RunEvent, {kind:'image_sample'}>) => void): void;
  onStatus(cb: (e: Extract<RunEvent, {kind:'status'}>) => void): void;
  close(): void;
}

export function connectRunEvents(runId: string): RunEventStream {
  const es = new EventSource(`/sse/runs/${runId}/events`);
  const metric: Array<(e: any) => void> = [];
  const log: Array<(e: any) => void> = [];
  const img: Array<(e: any) => void> = [];
  const status: Array<(e: any) => void> = [];

  function bind(type: string, arr: Array<(e: any) => void>): void {
    es.addEventListener(type, (m: MessageEvent) => {
      try {
        const d = JSON.parse(m.data);
        for (const cb of arr) cb({ kind: type, ...d });
      } catch { /* noop */ }
    });
  }
  bind('metric', metric);
  bind('log', log);
  bind('image_sample', img);
  bind('status', status);

  return {
    onMetric(cb) { metric.push(cb); },
    onLog(cb) { log.push(cb); },
    onImageSample(cb) { img.push(cb); },
    onStatus(cb) { status.push(cb); },
    close() { es.close(); },
  };
}
```

- [ ] **Step 3: `stores/runStream.ts` and store test**

```ts
// frontend/src/lib/stores/runStream.ts
import { connectRunEvents } from '../sse';
import type { RunEvent } from '../types';

const MAX_POINTS = 4000;
const MAX_LOG_LINES = 5000;

export interface RunStreamState {
  metrics: Record<string, { steps: number[]; values: number[] }>;
  log: string[];
  imageSamples: Array<{ tag: string; step: number; url?: string }>;
  connected: boolean;
}

type Listener = (s: RunStreamState) => void;

export function createRunStreamStore(runId: string) {
  let state: RunStreamState = { metrics: {}, log: [], imageSamples: [], connected: false };
  const listeners = new Set<Listener>();
  function emit() { for (const l of listeners) l(state); }

  const stream = connectRunEvents(runId);
  stream.onMetric((m) => {
    const cur = state.metrics[m.key] ?? { steps: [], values: [] };
    cur.steps.push(m.step); cur.values.push(m.value);
    if (cur.steps.length > MAX_POINTS) {
      cur.steps.shift(); cur.values.shift();
    }
    state = { ...state, metrics: { ...state.metrics, [m.key]: cur } };
    emit();
  });
  stream.onLog((e) => {
    const log = [...state.log, e.line];
    if (log.length > MAX_LOG_LINES) log.splice(0, log.length - MAX_LOG_LINES);
    state = { ...state, log };
    emit();
  });
  stream.onImageSample((e) => {
    state = { ...state, imageSamples: [...state.imageSamples, e].slice(-12) };
    emit();
  });
  stream.onStatus(() => { state = { ...state, connected: true }; emit(); });

  return {
    get(): RunStreamState { return state; },
    subscribe(l: Listener): () => void { listeners.add(l); l(state); return () => listeners.delete(l); },
    close(): void { stream.close(); },
  };
}
```

Optional test stubs EventSource so the logic can be exercised — note `EventSource` is not in jsdom by default; skip detailed unit tests here and rely on the API contract tests on the server side. A minimal smoke test that exercises ring-buffer semantics on a mock store would suffice.

- [ ] **Step 4: svelte-check + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
git add frontend/src/lib/sse.ts frontend/src/lib/stores/runStream.ts frontend/src/lib/types.ts
git commit -m "gui(frontend): SSE client + run-stream store with ring-buffer metric history"
```

---

## Task 10: `LineChart` uPlot wrapper + `CurvesPanel`

**Files:**
- Create: `frontend/src/lib/charts/LineChart.svelte`
- Create: `frontend/src/components/CurvesPanel.svelte`

- [ ] **Step 1: `LineChart.svelte`** — wraps uPlot, props `{ data: number[][]; series: {label:string}[]; height?: number }`. On `$effect` change, calls `uplot.setData(data)`. Destroys on unmount.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';

  let { data, series, height = 160, title = '' }: {
    data: number[][]; series: { label: string; stroke?: string }[]; height?: number; title?: string;
  } = $props();

  let host: HTMLDivElement | undefined;
  let chart: uPlot | null = null;

  onMount(() => {
    if (!host) return;
    chart = new uPlot({
      width: host.clientWidth,
      height,
      title,
      cursor: { drag: { x: false, y: false } },
      series: [{ label: 'step' }, ...series.map((s) => ({ label: s.label, stroke: s.stroke ?? '#60a5fa' }))],
      axes: [{ grid: { stroke: '#1f2937' } }, { grid: { stroke: '#1f2937' } }],
    }, data, host);
    const ro = new ResizeObserver(() => chart?.setSize({ width: host!.clientWidth, height }));
    ro.observe(host);
    return () => ro.disconnect();
  });

  $effect(() => {
    chart?.setData(data);
  });

  onDestroy(() => { chart?.destroy(); chart = null; });
</script>

<div bind:this={host} class="bg-bg-soft border border-border-soft rounded p-2"></div>
```

- [ ] **Step 2: `CurvesPanel.svelte`** — renders a grid of LineChart components for `train_loss`, `val_loss`, `mean_fg_dice`, `learning_rate`, `epoch_duration`. Reads from `runStream` store.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import LineChart from '../lib/charts/LineChart.svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let state = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });

  const KEYS = ['train_loss', 'val_loss', 'mean_fg_dice', 'learning_rate', 'epoch_duration'];

  function series(key: string): number[][] {
    const m = state.metrics[key];
    if (!m || m.steps.length === 0) return [[0], [null as unknown as number]];
    return [m.steps, m.values];
  }

  onMount(() => {
    store = createRunStreamStore(runId);
    const unsub = store.subscribe((s) => (state = s));
    return () => { unsub(); };
  });
  onDestroy(() => { store?.close(); });
</script>

<div class="grid grid-cols-2 gap-3">
  {#each KEYS as k}
    <LineChart data={series(k)} series={[{ label: k }]} title={k} />
  {/each}
</div>

<p class="text-[10px] text-slate-600 mt-2">{state.connected ? 'live' : 'connecting…'}</p>
```

- [ ] **Step 3: svelte-check + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
git add frontend/src/lib/charts/LineChart.svelte frontend/src/components/CurvesPanel.svelte
git commit -m "gui(frontend): LineChart (uPlot) + CurvesPanel grid"
```

---

## Task 11: `LogPanel` + `ImageSamplesPanel`

**Files:**
- Create: `frontend/src/components/LogPanel.svelte`
- Create: `frontend/src/components/ImageSamplesPanel.svelte`

- [ ] **Step 1: `LogPanel.svelte`** — auto-scrolling, monospaced. Reads `state.log[]`.

```svelte
<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let state = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });
  let pre: HTMLPreElement | undefined;

  onMount(() => {
    store = createRunStreamStore(runId);
    const unsub = store.subscribe(async (s) => {
      state = s;
      await tick();
      if (pre) pre.scrollTop = pre.scrollHeight;
    });
    return () => { unsub(); };
  });
  onDestroy(() => { store?.close(); });
</script>

<pre bind:this={pre} class="bg-black text-slate-200 text-[11px] font-mono p-2 h-80 overflow-auto whitespace-pre-wrap">{state.log.join('\n')}</pre>
```

- [ ] **Step 2: `ImageSamplesPanel.svelte`** — strip of recent samples; placeholder text when none. Phase 6 will swap into NiiVue.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let state = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });

  onMount(() => {
    store = createRunStreamStore(runId);
    const unsub = store.subscribe((s) => (state = s));
    return () => { unsub(); };
  });
  onDestroy(() => { store?.close(); });
</script>

<div class="space-y-2">
  {#if state.imageSamples.length === 0}
    <p class="text-xs text-slate-500">No image samples emitted yet (TB logger writes them every N epochs).</p>
  {:else}
    <ul class="grid grid-cols-3 gap-2">
      {#each state.imageSamples as s}
        <li class="bg-bg-soft border border-border-soft rounded p-2 text-[10px]">
          <p class="text-slate-400">{s.tag} · step {s.step}</p>
          {#if s.url}<img src={s.url} alt={s.tag} class="mt-1 w-full" />{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
```

- [ ] **Step 3: svelte-check + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
git add frontend/src/components/LogPanel.svelte frontend/src/components/ImageSamplesPanel.svelte
git commit -m "gui(frontend): live LogPanel + ImageSamplesPanel"
```

---

## Task 12: RunDetail tabs (Predictions/Curves/Log/Image samples)

**Files:**
- Modify: `frontend/src/components/RunDetail.svelte`

- [ ] **Step 1: Add tab strip**

```svelte
<script lang="ts">
  import PredictionList from './PredictionList.svelte';
  import CurvesPanel from './CurvesPanel.svelte';
  import LogPanel from './LogPanel.svelte';
  import ImageSamplesPanel from './ImageSamplesPanel.svelte';
  import type { Run } from '../lib/types';

  let { run }: { run: Run } = $props();
  type Tab = 'curves' | 'log' | 'samples' | 'predictions';
  let tab = $state<Tab>(run.status === 'completed' ? 'predictions' : 'curves');

  const TABS: { id: Tab; label: string }[] = [
    { id: 'curves', label: 'Curves' },
    { id: 'log', label: 'Log' },
    { id: 'samples', label: 'Image samples' },
    { id: 'predictions', label: 'Predictions' },
  ];
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
  <div class="flex items-center gap-2 text-xs">
    <strong class="text-slate-100">{run.dataset_id}</strong>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">{run.plans_name} · {run.trainer_name} · {run.configuration} · fold_{run.fold}</span>
    <span class="ml-auto" class:text-ok={run.status === 'completed'} class:text-slate-500={run.status !== 'completed'}>{run.status}</span>
  </div>
</div>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex gap-1 border-b border-border-soft pb-2 mb-3">
    {#each TABS as t}
      <button
        class="px-3 py-1 text-xs rounded"
        class:bg-bg-panel={tab === t.id} class:text-slate-100={tab === t.id} class:text-slate-500={tab !== t.id}
        onclick={() => (tab = t.id)}
      >
        {t.label}
      </button>
    {/each}
  </div>

  {#if tab === 'curves'}<CurvesPanel runId={run.id} />
  {:else if tab === 'log'}<LogPanel runId={run.id} />
  {:else if tab === 'samples'}<ImageSamplesPanel runId={run.id} />
  {:else if tab === 'predictions'}<PredictionList runId={run.id} />
  {/if}
</div>
```

- [ ] **Step 2: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/components/RunDetail.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): RunDetail tabs (curves/log/samples/predictions)"
```

---

## Task 13: Jobs route + JobsTable (read-only)

**Files:**
- Create: `frontend/src/lib/stores/jobs.ts`
- Create: `frontend/src/components/JobsTable.svelte`
- Modify: `frontend/src/routes/Jobs.svelte`

- [ ] **Step 1: `stores/jobs.ts`** — async store + a polling helper `pollEvery(ms, signal)`.

```ts
import { api } from '../api';
import type { Job } from '../types';

type State = { kind: 'idle' } | { kind: 'loading' } | { kind: 'loaded'; data: Job[] } | { kind: 'error'; error: Error };
type Listener = (s: State) => void;

export function createJobsStore() {
  let state: State = { kind: 'idle' };
  const listeners = new Set<Listener>();
  function emit() { for (const l of listeners) l(state); }

  let timer: number | undefined;
  async function load() {
    state = { kind: 'loading' }; emit();
    try { state = { kind: 'loaded', data: await api.get<Job[]>('/api/jobs') }; }
    catch (e) { state = { kind: 'error', error: e as Error }; }
    emit();
  }

  return {
    get(): State { return state; },
    subscribe(l: Listener) { listeners.add(l); l(state); return () => listeners.delete(l); },
    load,
    startPolling(intervalMs = 5000) {
      load();
      timer = window.setInterval(load, intervalMs);
    },
    stopPolling() { if (timer !== undefined) window.clearInterval(timer); timer = undefined; },
  };
}
```

- [ ] **Step 2: `JobsTable.svelte`** — table of `id|kind|status|started_at|exit_code|pid|args summary`.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createJobsStore } from '../lib/stores/jobs';

  const jobs = createJobsStore();
  let state = $state(jobs.get());

  onMount(() => {
    const unsub = jobs.subscribe((s) => (state = s));
    jobs.startPolling(5000);
    return unsub;
  });
  onDestroy(() => { jobs.stopPolling(); });
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-xs text-slate-500">Loading jobs…</p>
{:else if state.kind === 'error'}
  <p class="text-xs text-err">{state.error.message}</p>
{:else if state.data.length === 0}
  <p class="text-xs text-slate-500">No jobs tracked. Phase 4 lets you launch trainings + predicts from the GUI.</p>
{:else}
  <table class="w-full text-xs">
    <thead>
      <tr class="text-slate-500 border-b border-border-soft">
        <th class="text-left py-1 px-2">#</th>
        <th class="text-left py-1 px-2">Kind</th>
        <th class="text-left py-1 px-2">Status</th>
        <th class="text-left py-1 px-2">PID</th>
        <th class="text-left py-1 px-2">Started</th>
        <th class="text-left py-1 px-2">Args</th>
      </tr>
    </thead>
    <tbody>
      {#each state.data as j}
        <tr class="border-b border-border-soft">
          <td class="py-1 px-2 text-slate-300">{j.id}</td>
          <td class="py-1 px-2 text-slate-300">{j.kind}</td>
          <td class="py-1 px-2" class:text-ok={j.status === 'completed'} class:text-err={j.status === 'failed'}>{j.status}</td>
          <td class="py-1 px-2 text-slate-400">{j.pid ?? '—'}</td>
          <td class="py-1 px-2 text-slate-500">{j.started_at ?? '—'}</td>
          <td class="py-1 px-2 text-slate-400 truncate max-w-md">{j.args_json}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
```

- [ ] **Step 3: Update `Jobs.svelte`**

```svelte
<script lang="ts">
  import JobsTable from '../components/JobsTable.svelte';
</script>

<h2 class="text-lg font-semibold text-slate-100">Jobs</h2>
<p class="text-xs text-amber-400 mt-1">Stop/Restart actions land in Phase 4. Phase 3 shows tracked jobs (currently only CLI-discovered).</p>

<div class="mt-4">
  <JobsTable />
</div>
```

- [ ] **Step 4: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/lib/stores/jobs.ts frontend/src/components/JobsTable.svelte frontend/src/routes/Jobs.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Jobs route with read-only JobsTable + 5s polling"
```

---

## Task 14: Header job badge live count

**Files:**
- Modify: `frontend/src/components/WorkspaceHeader.svelte`

- [ ] **Step 1: Subscribe to jobs store**, replace the hard-coded "0 jobs" pill with a live count of `status in (queued, starting, running)`.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import WorkspaceSwitcher from './WorkspaceSwitcher.svelte';
  import { createJobsStore } from '../lib/stores/jobs';

  const jobs = createJobsStore();
  let activeCount = $state(0);

  onMount(() => {
    jobs.subscribe((s) => {
      if (s.kind === 'loaded') {
        activeCount = s.data.filter((j) => ['queued', 'starting', 'running'].includes(j.status)).length;
      }
    });
    jobs.startPolling(5000);
    return () => jobs.stopPolling();
  });
</script>

<header class="flex items-center gap-3 bg-bg-panel border-b border-border px-4 py-2 text-xs">
  <strong class="text-slate-100">nnU-Net Manager</strong>
  <WorkspaceSwitcher />
  <span class:bg-emerald-900={activeCount === 0}
        class:bg-amber-700={activeCount > 0}
        class:text-emerald-200={activeCount === 0}
        class:text-amber-100={activeCount > 0}
        class="px-2 py-0.5 rounded-full text-[10px]">
    ● {activeCount} jobs running
  </span>
  <span class="text-amber-400 text-[10px]">GPU: pending</span>
  <span class="flex-1"></span>
  <a href="#/settings" class="text-slate-400 hover:text-slate-200">⚙ Settings</a>
</header>
```

- [ ] **Step 2: Build + commit**

```bash
cd frontend && npm run build
git add frontend/src/components/WorkspaceHeader.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): header job badge tracks live active count"
```

---

## Task 15: Smoke + docs

**Files:**
- Modify: `documentation/gui.md`
- Create: `nnunetv2/tests/gui/api/test_monitor_smoke.py` — boots the app, writes a TB event file mid-stream, asserts an SSE metric appears within 3 s

- [ ] **Step 1: Smoke test**

```python
# nnunetv2/tests/gui/api/test_monitor_smoke.py
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest


def test_live_metric_appears_in_sse(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir
    fold_dir = (populated_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    build_tb_event_dir(fold_dir / "tensorboard",
                       scalars={"train_loss": [(0, 1.0)]})

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    def write_new_metric():
        time.sleep(0.5)
        build_tb_event_dir(fold_dir / "tensorboard", scalars={"train_loss": [(1, 0.4)]})

    t = threading.Thread(target=write_new_metric, daemon=True)
    t.start()

    new_step_seen = False
    with c.stream("GET",
                  "/sse/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/events") as r:
        deadline = time.time() + 5
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                if raw.startswith("event: metric"):
                    data = json.loads(raw.split("data: ", 1)[1])
                    if data.get("step") == 1:
                        new_step_seen = True
                        break
            if new_step_seen or time.time() > deadline:
                break

    assert new_step_seen, "live metric did not arrive via SSE within 5s"
```

- [ ] **Step 2: Update `documentation/gui.md`**

Mark Phase 3 in the Roadmap; append:
```markdown
3. **Live monitoring (passive)** ✓ — SSE multiplexed stream, live curves (uPlot), log tail, image samples panel, read-only Jobs page.
```

- [ ] **Step 3: Full pyramid green**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && cd ..
```

- [ ] **Step 4: Commit + open PR**

```bash
git add nnunetv2/tests/gui/api/test_monitor_smoke.py documentation/gui.md
git commit -m "gui(tests+docs): live SSE smoke + Phase 3 roadmap mark"
```

---

## Done condition

Phase 3 is complete when:

- [ ] All gui pytest tests pass on host + clean env.
- [ ] All frontend vitest tests pass.
- [ ] svelte-check is 0 errors.
- [ ] Boot `nnUNetv2_gui` against a real running nnUNet training job; the Monitor → Curves tab shows live-updating curves within 2 s of TB writes, the Log tab tails the `training_log_*.txt`, and the header job badge increments while jobs are present.
- [ ] Tailer self-disable after 5 consecutive failures is observable (deliberately corrupt the event file → status banner appears).
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 3 completion.

Then move on to Phase 4 (Job launching — Popen with process groups, multi-fold queue, Preprocess/Train/Predict forms, Stop/Restart actions).
