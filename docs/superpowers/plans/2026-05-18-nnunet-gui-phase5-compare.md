# nnU-Net GUI — Phase 5 (Compare) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land cross-run analysis — a Compare route where the user picks any N runs from the discovered registry, sees an overlay line chart of any metric on the same axes, browses a sortable/filterable table of summary stats, and exports the table to CSV.

**Architecture:** One new router `routers/compare.py` exposes `GET /api/compare?run_ids=...` returning per-run metric arrays. Metrics are pulled from each run's `tensorboard/` event files via the existing Phase 3 `tb_tailer.read_all_metrics` (one-shot read mode). The aggregate is fronted by `state/compare.py` which exposes a `RunMetrics` Pydantic model and a `gather_run_metrics(cfg, run_ids)` helper. Each run's terminal `validation/summary.json` is also harvested as a row in the comparison table. The Svelte UI adds a `Compare.svelte` route hosting three new components: `RunSelector.svelte` (checkbox list of every run, filterable by dataset/config), `OverlayChart.svelte` (uPlot wrapper with metric/x-axis/smoothing dropdowns), and `ComparisonTable.svelte` (sortable, filter-by-dataset/status, CSV export).

**Tech Stack:** No new Python or npm dependencies. Re-uses `tbparse` (already pulled in Phase 3) and the existing `uplot` frontend dep. The comparison route is purely additive — no Phase 0-4 endpoint is modified.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "UI Pages" → "Compare". Architectural decisions (locked-in): historical metrics are read on demand via the existing Phase 3 `read_all_metrics` helper — no new tailer wiring; SSE multiplexing not needed here because Compare reads finished or paused state.

**TDD discipline:** Every behavioral change starts with a failing test. One commit per task. The `state/compare.py` and `routers/compare.py` tests run against synthetic event-file fixtures (the `build_tb_event_dir(...)` builder already exists from Phase 3).

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/state/compare.py` | `RunMetrics` + `RunSummary` Pydantic models; `gather_run_metrics(cfg, run_ids)` + `gather_run_summaries(cfg, run_ids)`; CSV-row materialization helper |
| `nnunetv2/gui/routers/compare.py` | `GET /api/compare?run_ids=…&metric_keys=…` returning aggregated payload |
| `nnunetv2/gui/server.py` (mod) | Include the new router |
| `nnunetv2/tests/gui/unit/test_compare_state.py` | `gather_run_metrics` + `gather_run_summaries` against fixture trees |
| `nnunetv2/tests/gui/api/test_compare_api.py` | Router contract tests |
| `nnunetv2/tests/gui/fixtures/builders.py` (mod) | Add `build_run_summary(fold_dir, foreground_mean=...)` helper that writes `validation/summary.json` with controllable Dice values |
| `frontend/src/lib/types.ts` (mod) | `RunMetricSeries`, `RunSummary`, `CompareResponse` types |
| `frontend/src/lib/api.ts` (mod) | `getCompare(runIds, metricKeys?)` endpoint helper |
| `frontend/src/lib/stores/compare.ts` | Async store with `load(runIds)` returning a `CompareResponse` |
| `frontend/src/lib/stores/compare.test.ts` | Async store happy + error paths |
| `frontend/src/components/RunSelector.svelte` | Checkbox list of every run, grouped by dataset; emits selected run-id array |
| `frontend/src/components/OverlayChart.svelte` | uPlot wrapper with metric/x-axis (epoch/wall-time)/smoothing dropdowns |
| `frontend/src/components/ComparisonTable.svelte` | Sortable rows, filter chips, CSV-export button |
| `frontend/src/components/csv.ts` | Pure helper `toCsv(rows, cols): string` (browser-safe; no node deps) |
| `frontend/src/components/csv.test.ts` | Pure-function tests for the CSV serializer |
| `frontend/src/routes/Compare.svelte` (mod) | Replace stub with the three components composed into the page |
| `documentation/gui.md` (mod) | Refresh roadmap + "what you can do today" |

---

## Task 1: `state/compare.py` — `RunMetrics` + `gather_run_metrics` (TDD)

**Files:**
- Create: `nnunetv2/gui/state/compare.py`
- Create: `nnunetv2/tests/gui/unit/test_compare_state.py`
- Modify: `nnunetv2/tests/gui/fixtures/builders.py`

- [ ] **Step 1: Add `build_run_summary` to builders**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_run_summary(
    fold_dir: Path,
    *,
    foreground_mean_dice: float = 0.9,
    per_case: dict[str, float] | None = None,
) -> Path:
    """Write a validation/summary.json under a fold directory.

    `per_case` maps case_id -> Dice (single-class) for the `metric_per_case` block;
    `foreground_mean_dice` is the overall mean.
    """
    val_dir = fold_dir / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "foreground_mean": {"Dice": foreground_mean_dice},
        "mean": {"1": {"Dice": foreground_mean_dice}},
    }
    if per_case:
        payload["metric_per_case"] = [
            {"reference_file": cid, "metrics": {"1": {"Dice": dice}}}
            for cid, dice in per_case.items()
        ]
    (val_dir / "summary.json").write_text(json.dumps(payload))
    return val_dir / "summary.json"
```

- [ ] **Step 2: Write failing tests**

`nnunetv2/tests/gui/unit/test_compare_state.py`:
```python
from __future__ import annotations

from pathlib import Path

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.compare import (
    RunMetrics, RunSummary,
    gather_run_metrics, gather_run_summaries,
)
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.tests.gui.fixtures.builders import (
    build_run, build_tb_event_dir, build_run_summary,
)


def _cfg(populated_paths, monkeypatch) -> GuiConfig:
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)
    return cfg


def test_gather_metrics_empty_when_no_event_files(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    out = gather_run_metrics(cfg, [run_id])
    assert len(out) == 1
    assert out[0].run_id == run_id
    assert out[0].series == {}  # no events written yet


def test_gather_metrics_reads_tb_events(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0), (1, 0.7), (2, 0.4)]),
                 ("val_loss",   [(0, 1.2), (1, 0.8), (2, 0.5)])],
    )
    out = gather_run_metrics(cfg, [run_id])
    assert len(out) == 1
    rm = out[0]
    assert set(rm.series) >= {"train_loss", "val_loss"}
    assert len(rm.series["train_loss"]) == 3
    pt = rm.series["train_loss"][0]
    assert pt.step == 0 and pt.value == 1.0


def test_gather_metrics_unknown_run_returns_empty_series(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    out = gather_run_metrics(cfg, ["Dataset999_X/p__t__c/fold_0"])
    assert len(out) == 1
    assert out[0].series == {}


def test_gather_metrics_filters_by_keys(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0)]),
                 ("val_loss", [(0, 1.0)]),
                 ("mean_fg_dice", [(0, 0.5)])],
    )
    out = gather_run_metrics(cfg, [run_id], metric_keys=["train_loss", "mean_fg_dice"])
    assert set(out[0].series.keys()) == {"train_loss", "mean_fg_dice"}


def test_gather_summaries_reads_validation_summary(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / run_id
    build_run_summary(fold_dir, foreground_mean_dice=0.87)

    out = gather_run_summaries(cfg, [run_id])
    assert len(out) == 1
    s = out[0]
    assert isinstance(s, RunSummary)
    assert s.run_id == run_id
    assert s.foreground_mean_dice == 0.87
    assert s.dataset_id == "Dataset027_ACDC"
    assert s.configuration == "3d_fullres"
    assert s.fold == "0"
    assert s.status == "completed"


def test_gather_summaries_missing_summary_returns_none_fields(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    out = gather_run_summaries(cfg, [run_id])
    assert len(out) == 1
    assert out[0].foreground_mean_dice is None
```

- [ ] **Step 3: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_compare_state.py -v
```
Expected: import errors / module missing.

- [ ] **Step 4: Implement `nnunetv2/gui/state/compare.py`**

```python
"""Cross-run aggregation: metric histories + summary stats."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.runs import get_run


class MetricPoint(BaseModel):
    step: int
    value: float
    wall_time: Optional[float] = None


class RunMetrics(BaseModel):
    run_id: str
    series: dict[str, list[MetricPoint]]  # metric key -> ordered points


class RunSummary(BaseModel):
    run_id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    status: str
    foreground_mean_dice: Optional[float] = None
    per_class_dice: Optional[dict[str, float]] = None


def gather_run_metrics(
    cfg: GuiConfig,
    run_ids: list[str],
    *,
    metric_keys: Optional[list[str]] = None,
) -> list[RunMetrics]:
    """Read tensorboard events for each run id; return per-run metric series.

    Uses the existing Phase 3 `read_all_metrics` helper for a one-shot scalar read.
    Unknown / non-existent runs return `RunMetrics(run_id=..., series={})`.
    """
    from nnunetv2.gui.services.tb_tailer import read_all_metrics

    out: list[RunMetrics] = []
    for rid in run_ids:
        run = get_run(cfg, rid)
        series: dict[str, list[MetricPoint]] = {}
        if run is not None:
            event_dir = Path(run.output_folder) / "tensorboard"
            if event_dir.is_dir():
                try:
                    for ev in read_all_metrics(event_dir):
                        key = ev.get("key")
                        if metric_keys is not None and key not in metric_keys:
                            continue
                        series.setdefault(key, []).append(
                            MetricPoint(step=int(ev["step"]),
                                        value=float(ev["value"]),
                                        wall_time=ev.get("wall_time"))
                        )
                except Exception:  # pragma: no cover - degraded mode
                    series = {}
            # Ensure deterministic order by step
            for k, pts in series.items():
                pts.sort(key=lambda p: p.step)
        out.append(RunMetrics(run_id=rid, series=series))
    return out


def gather_run_summaries(cfg: GuiConfig, run_ids: list[str]) -> list[RunSummary]:
    """Read each run's row + validation/summary.json into a flat RunSummary."""
    out: list[RunSummary] = []
    for rid in run_ids:
        run = get_run(cfg, rid)
        if run is None:
            # Synthesize a placeholder so the caller sees a 1:1 alignment.
            out.append(RunSummary(
                run_id=rid, dataset_id="?", plans_name="?", trainer_name="?",
                configuration="?", fold="?", status="unknown",
            ))
            continue
        fg, per_class = _read_summary(Path(run.output_folder))
        out.append(RunSummary(
            run_id=run.id,
            dataset_id=run.dataset_id,
            plans_name=run.plans_name,
            trainer_name=run.trainer_name,
            configuration=run.configuration,
            fold=run.fold,
            status=run.status,
            foreground_mean_dice=fg,
            per_class_dice=per_class,
        ))
    return out


def _read_summary(fold_dir: Path) -> tuple[Optional[float], Optional[dict[str, float]]]:
    fp = fold_dir / "validation" / "summary.json"
    if not fp.is_file():
        return None, None
    try:
        data = json.loads(fp.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None
    fg = None
    fg_block = data.get("foreground_mean") or {}
    if isinstance(fg_block, dict):
        fg = fg_block.get("Dice")
    per_class: dict[str, float] = {}
    mean_block = data.get("mean") or {}
    if isinstance(mean_block, dict):
        for label, metrics in mean_block.items():
            if isinstance(metrics, dict) and "Dice" in metrics:
                per_class[str(label)] = float(metrics["Dice"])
    return (float(fg) if fg is not None else None,
            per_class or None)
```

- [ ] **Step 5: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/unit/test_compare_state.py -v
```
Expected: 6 passes. Whole suite still green: `pytest nnunetv2/tests/gui/ -v`.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/state/compare.py nnunetv2/tests/gui/unit/test_compare_state.py nnunetv2/tests/gui/fixtures/builders.py
git commit -m "gui(state): gather_run_metrics + gather_run_summaries for Compare aggregation"
```

---

## Task 2: `routers/compare.py` — `GET /api/compare` (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/compare.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/api/test_compare_api.py`

- [ ] **Step 1: Write failing tests**

`nnunetv2/tests/gui/api/test_compare_api.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def compare_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.tests.gui.fixtures.builders import (
        build_tb_event_dir, build_run_summary,
    )

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)

    # Add a tensorboard dir + summary on one of the populated runs
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = Path(cfg.results) / rid
    build_tb_event_dir(
        fold_dir / "tensorboard",
        scalars=[("train_loss", [(0, 1.0), (1, 0.5)]),
                 ("val_loss",   [(0, 1.1), (1, 0.6)])],
    )
    build_run_summary(fold_dir, foreground_mean_dice=0.88)

    app = create_app(cfg)
    return TestClient(app)


def test_compare_empty_run_ids_returns_empty_payload(compare_client):
    r = compare_client.get("/api/compare")
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"] == []
    assert body["summaries"] == []


def test_compare_single_run(compare_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["metrics"]) == 1
    assert body["metrics"][0]["run_id"] == rid
    assert "train_loss" in body["metrics"][0]["series"]
    assert len(body["summaries"]) == 1
    assert body["summaries"][0]["foreground_mean_dice"] == 0.88


def test_compare_filter_metric_keys(compare_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid}&metric_keys=train_loss")
    body = r.json()
    series = body["metrics"][0]["series"]
    assert set(series.keys()) == {"train_loss"}


def test_compare_multiple_run_ids_preserves_order(compare_client):
    rid1 = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    rid2 = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d/fold_0"
    r = compare_client.get(f"/api/compare?run_ids={rid1}&run_ids={rid2}")
    body = r.json()
    assert [m["run_id"] for m in body["metrics"]] == [rid1, rid2]
    assert [s["run_id"] for s in body["summaries"]] == [rid1, rid2]


def test_compare_unknown_run_returns_placeholder(compare_client):
    rid = "Dataset999_X/p__t__c/fold_3"
    r = compare_client.get(f"/api/compare?run_ids={rid}")
    body = r.json()
    assert body["metrics"][0]["series"] == {}
    assert body["summaries"][0]["status"] == "unknown"
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_compare_api.py -v
```
Expected: route does not exist → 404s.

- [ ] **Step 3: Implement `nnunetv2/gui/routers/compare.py`**

```python
"""GET /api/compare — aggregate per-run metric arrays + summary stats."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from nnunetv2.gui.state.compare import (
    gather_run_metrics, gather_run_summaries,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/compare", tags=["compare"])

    @router.get("")
    def compare(
        request: Request,
        run_ids: list[str] = Query(default_factory=list),
        metric_keys: Optional[list[str]] = Query(default=None),
    ) -> dict:
        cfg = request.app.state.gui_config
        if not run_ids:
            return {"metrics": [], "summaries": []}
        metrics = gather_run_metrics(cfg, run_ids, metric_keys=metric_keys)
        summaries = gather_run_summaries(cfg, run_ids)
        return {
            "metrics": [m.model_dump() for m in metrics],
            "summaries": [s.model_dump() for s in summaries],
        }

    return router
```

- [ ] **Step 4: Include router in `create_app`**

Add to `nnunetv2/gui/server.py`:

```python
from nnunetv2.gui.routers import compare as compare_router
# ... after other include_router calls:
    app.include_router(compare_router.make_router())
```

- [ ] **Step 5: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/api/test_compare_api.py -v
pytest nnunetv2/tests/gui/ -v  # full suite green
```

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/compare.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_compare_api.py
git commit -m "gui(api): GET /api/compare returns per-run metric series + summaries"
```

---

## Task 3: Frontend types + `getCompare` API helper

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/lib/types.ts`:

```ts
export interface MetricPoint {
  step: number;
  value: number;
  wall_time: number | null;
}

export interface RunMetricSeries {
  run_id: string;
  series: Record<string, MetricPoint[]>;
}

export interface RunSummary {
  run_id: string;
  dataset_id: string;
  plans_name: string;
  trainer_name: string;
  configuration: string;
  fold: string;
  status: string;
  foreground_mean_dice: number | null;
  per_class_dice: Record<string, number> | null;
}

export interface CompareResponse {
  metrics: RunMetricSeries[];
  summaries: RunSummary[];
}
```

- [ ] **Step 2: Add `getCompare` to `endpoints`**

In `frontend/src/lib/api.ts`, extend the `endpoints` object:

```ts
import type { CompareResponse } from './types';

// inside the existing endpoints export:
  getCompare: (runIds: string[], metricKeys?: string[]) => {
    const params = new URLSearchParams();
    for (const r of runIds) params.append('run_ids', r);
    if (metricKeys) for (const k of metricKeys) params.append('metric_keys', k);
    const q = params.toString();
    return api.get<CompareResponse>(`/api/compare${q ? `?${q}` : ''}`);
  },
```

- [ ] **Step 3: svelte-check**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "gui(frontend): types + getCompare endpoint helper"
```

---

## Task 4: `stores/compare.ts` async store (TDD)

**Files:**
- Create: `frontend/src/lib/stores/compare.ts`
- Create: `frontend/src/lib/stores/compare.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/lib/stores/compare.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createCompareStore } from './compare';

describe('compare store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('starts idle', () => {
    const s = createCompareStore();
    expect(s.get()).toEqual({ kind: 'idle' });
  });

  it('encodes run_ids as repeated query params', async () => {
    const mock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ metrics: [], summaries: [] }), { status: 200 })
    );
    vi.stubGlobal('fetch', mock);

    const s = createCompareStore();
    await s.load(['a/b/c', 'd/e/f']);

    const url = mock.mock.calls[0][0] as string;
    expect(url).toMatch(/run_ids=a%2Fb%2Fc/);
    expect(url).toMatch(/run_ids=d%2Fe%2Ff/);
  });

  it('transitions to loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ metrics: [{ run_id: 'a/b/c', series: {} }], summaries: [] }),
      { status: 200 },
    )));

    const s = createCompareStore();
    await s.load(['a/b/c']);
    const final = s.get();
    expect(final.kind).toBe('loaded');
    if (final.kind === 'loaded') {
      expect(final.data.metrics).toHaveLength(1);
    }
  });

  it('transitions to error on 5xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ kind: 'internal_error', message: 'boom', retryable: false, details: null }),
      { status: 500 },
    )));

    const s = createCompareStore();
    await s.load(['x/y/z']);
    expect(s.get().kind).toBe('error');
  });
});
```

- [ ] **Step 2: Run; confirm fail**

```bash
cd frontend && npm test -- compare
```

- [ ] **Step 3: Implement the store**

`frontend/src/lib/stores/compare.ts`:
```ts
import { endpoints, ApiError } from '../api';
import type { CompareResponse } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: CompareResponse }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createCompareStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();

  function emit() {
    for (const l of listeners) l(current);
  }

  return {
    get(): State {
      return current;
    },
    subscribe(l: Listener): () => void {
      listeners.add(l);
      l(current);
      return () => listeners.delete(l);
    },
    async load(runIds: string[], metricKeys?: string[]): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getCompare(runIds, metricKeys);
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
```

- [ ] **Step 4: Run; confirm pass**

```bash
cd frontend && npm test
```
Expected: previous tests + 4 new = green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stores/compare.ts frontend/src/lib/stores/compare.test.ts
git commit -m "gui(frontend): async compare store with idle/loading/loaded/error"
```

---

## Task 5: `RunSelector.svelte` — multi-pick from `/api/runs`

**Files:**
- Create: `frontend/src/components/RunSelector.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createRunsStore } from '../lib/stores/runs';
  import type { Run } from '../lib/types';

  let { value = [] as string[], onChange }: { value: string[]; onChange: (ids: string[]) => void } = $props();

  const runs = createRunsStore();
  let state = $state(runs.get());

  // Filter chips: dataset, configuration, status
  let datasetFilter = $state<string>('');
  let configFilter = $state<string>('');

  onMount(() => {
    const unsub = runs.subscribe((s) => (state = s));
    runs.load({});
    return unsub;
  });

  function toggle(id: string): void {
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  }

  function clearAll(): void {
    onChange([]);
  }

  function visible(items: Run[]): Run[] {
    return items.filter((r) => {
      if (datasetFilter && !r.dataset_id.includes(datasetFilter)) return false;
      if (configFilter && r.configuration !== configFilter) return false;
      return true;
    });
  }

  function groupByDataset(items: Run[]): Record<string, Run[]> {
    const groups: Record<string, Run[]> = {};
    for (const r of items) (groups[r.dataset_id] ??= []).push(r);
    return groups;
  }

  function uniqConfigs(items: Run[]): string[] {
    return [...new Set(items.map((r) => r.configuration))].sort();
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2">
    <h3 class="text-xs uppercase tracking-wider text-slate-500">Pick runs</h3>
    <span class="text-[10px] text-slate-500">({value.length} selected)</span>
    {#if value.length > 0}
      <button class="text-[10px] text-slate-400 hover:text-slate-200" onclick={clearAll}>clear</button>
    {/if}
  </div>

  {#if state.kind === 'loading' || state.kind === 'idle'}
    <p class="text-xs text-slate-500">Loading runs…</p>
  {:else if state.kind === 'error'}
    <p class="text-xs text-err">{state.error.message}</p>
  {:else if state.data.length === 0}
    <p class="text-xs text-slate-500">No runs yet — train something first.</p>
  {:else}
    <div class="flex gap-2 mb-2 text-[11px]">
      <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
             placeholder="filter by dataset…" bind:value={datasetFilter} />
      <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
              bind:value={configFilter}>
        <option value="">all configs</option>
        {#each uniqConfigs(state.data) as c}
          <option value={c}>{c}</option>
        {/each}
      </select>
    </div>

    <div class="max-h-80 overflow-auto text-xs">
      {#each Object.entries(groupByDataset(visible(state.data))) as [ds, items]}
        <div class="mt-2">
          <h4 class="text-[11px] text-slate-500 mb-1">{ds}</h4>
          <ul class="space-y-0.5">
            {#each items as r}
              <li>
                <label class="flex items-center gap-2 px-1 py-0.5 hover:bg-bg-panel rounded">
                  <input type="checkbox" checked={value.includes(r.id)} onchange={() => toggle(r.id)} />
                  <span class="text-slate-300">{r.configuration} · fold_{r.fold}</span>
                  <span class="text-slate-500">·</span>
                  <span class="text-slate-500">{r.trainer_name}/{r.plans_name}</span>
                  <span class="text-slate-500">·</span>
                  <span class:text-ok={r.status === 'completed'}
                        class:text-slate-500={r.status !== 'completed'}>{r.status}</span>
                </label>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </div>
  {/if}
</div>
```

- [ ] **Step 2: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RunSelector.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): RunSelector multi-pick with dataset+config filter chips"
```

---

## Task 6: `OverlayChart.svelte` — uPlot overlay with controls

**Files:**
- Create: `frontend/src/components/OverlayChart.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import type { RunMetricSeries } from '../lib/types';

  let { metrics = [] as RunMetricSeries[] }: { metrics: RunMetricSeries[] } = $props();

  type XAxis = 'epoch' | 'wall_time';
  let metricKey = $state<string>('');
  let xAxis = $state<XAxis>('epoch');
  let smoothing = $state<number>(0);  // 0..0.95

  let containerEl: HTMLDivElement | undefined = $state();
  let chart: uPlot | undefined;

  function allKeys(): string[] {
    const keys = new Set<string>();
    for (const m of metrics) for (const k of Object.keys(m.series)) keys.add(k);
    return [...keys].sort();
  }

  function ema(values: number[], alpha: number): number[] {
    if (alpha <= 0) return values;
    const out: number[] = [];
    let last = values[0] ?? 0;
    for (const v of values) {
      last = alpha * last + (1 - alpha) * v;
      out.push(last);
    }
    return out;
  }

  function buildSeries(): { data: uPlot.AlignedData; opts: uPlot.Options } {
    const palette = [
      '#67e8f9', '#fca5a5', '#86efac', '#fcd34d',
      '#a5b4fc', '#f9a8d4', '#fdba74', '#c4b5fd',
    ];
    const allX = new Set<number>();
    const seriesData: { runId: string; xs: number[]; ys: number[] }[] = [];
    for (const m of metrics) {
      const pts = m.series[metricKey] ?? [];
      const xs = pts.map((p) => xAxis === 'epoch' ? p.step : (p.wall_time ?? p.step));
      const ys = ema(pts.map((p) => p.value), smoothing);
      for (const x of xs) allX.add(x);
      seriesData.push({ runId: m.run_id, xs, ys });
    }
    const sortedX = [...allX].sort((a, b) => a - b);
    const aligned: uPlot.AlignedData = [sortedX];
    const opts: uPlot.Options = {
      width: containerEl?.clientWidth ?? 600,
      height: 360,
      scales: { x: { time: false } },
      axes: [
        { stroke: '#94a3b8', grid: { stroke: '#1f2937' } },
        { stroke: '#94a3b8', grid: { stroke: '#1f2937' } },
      ],
      series: [{ label: xAxis }],
    };
    seriesData.forEach((s, i) => {
      const map = new Map<number, number>();
      s.xs.forEach((x, j) => map.set(x, s.ys[j]));
      aligned.push(sortedX.map((x) => map.has(x) ? (map.get(x) as number) : null));
      opts.series.push({
        label: s.runId,
        stroke: palette[i % palette.length],
        width: 1.5,
        spanGaps: true,
      });
    });
    return { data: aligned, opts };
  }

  function render() {
    if (!containerEl || !metricKey) return;
    chart?.destroy();
    const { data, opts } = buildSeries();
    chart = new uPlot(opts, data, containerEl);
  }

  onMount(() => {
    const keys = allKeys();
    if (!metricKey && keys.length) metricKey = keys[0];
    tick().then(render);
    return () => chart?.destroy();
  });

  $effect(() => {
    // re-render on any control change or new metrics payload
    metricKey; xAxis; smoothing; metrics;
    tick().then(render);
  });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-3 mb-2 text-[11px]">
    <label class="text-slate-500">metric</label>
    <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
            bind:value={metricKey}>
      {#each allKeys() as k}
        <option value={k}>{k}</option>
      {/each}
    </select>
    <label class="text-slate-500">x-axis</label>
    <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
            bind:value={xAxis}>
      <option value="epoch">epoch</option>
      <option value="wall_time">wall_time</option>
    </select>
    <label class="text-slate-500">smoothing</label>
    <input type="range" min="0" max="0.95" step="0.05" bind:value={smoothing} />
    <span class="text-slate-400">{smoothing.toFixed(2)}</span>
  </div>

  {#if metrics.length === 0}
    <p class="text-xs text-slate-500">Select runs to plot…</p>
  {:else if allKeys().length === 0}
    <p class="text-xs text-slate-500">Selected runs have no metric history.</p>
  {/if}

  <div bind:this={containerEl} class="w-full"></div>
</div>
```

- [ ] **Step 2: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OverlayChart.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): OverlayChart uPlot wrapper with metric/x-axis/smoothing controls"
```

---

## Task 7: `ComparisonTable.svelte` + CSV serializer (TDD on the CSV pure helper)

**Files:**
- Create: `frontend/src/components/csv.ts`
- Create: `frontend/src/components/csv.test.ts`
- Create: `frontend/src/components/ComparisonTable.svelte`

- [ ] **Step 1: Write failing tests for the CSV serializer**

`frontend/src/components/csv.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('writes header and rows', () => {
    const out = toCsv(
      [{ a: 1, b: 'x' }, { a: 2, b: 'y' }],
      ['a', 'b'],
    );
    expect(out).toBe('a,b\n1,x\n2,y');
  });

  it('quotes values containing commas', () => {
    const out = toCsv([{ a: 'x,y' }], ['a']);
    expect(out).toBe('a\n"x,y"');
  });

  it('escapes double-quotes by doubling them', () => {
    const out = toCsv([{ a: 'he said "hi"' }], ['a']);
    expect(out).toBe('a\n"he said ""hi"""');
  });

  it('renders null/undefined as empty cell', () => {
    const out = toCsv([{ a: null, b: undefined, c: 0 }], ['a', 'b', 'c']);
    expect(out).toBe('a,b,c\n,,0');
  });

  it('preserves column order from cols arg', () => {
    const out = toCsv([{ b: 2, a: 1 }], ['a', 'b']);
    expect(out).toBe('a,b\n1,2');
  });
});
```

- [ ] **Step 2: Run; confirm fail**

```bash
cd frontend && npm test -- csv
```

- [ ] **Step 3: Implement `frontend/src/components/csv.ts`**

```ts
type Row = Record<string, unknown>;

function escape(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  if (/[",\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCsv(rows: Row[], cols: string[]): string {
  const header = cols.join(',');
  const body = rows.map((r) => cols.map((c) => escape(r[c])).join(',')).join('\n');
  return body ? `${header}\n${body}` : header;
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Pass csv tests**

```bash
cd frontend && npm test -- csv
```

- [ ] **Step 5: Implement `ComparisonTable.svelte`**

```svelte
<script lang="ts">
  import type { RunSummary } from '../lib/types';
  import { toCsv, downloadCsv } from './csv';

  let { summaries = [] as RunSummary[] }: { summaries: RunSummary[] } = $props();

  type SortKey = 'dataset_id' | 'configuration' | 'fold' | 'status' | 'foreground_mean_dice';
  let sortBy = $state<SortKey>('foreground_mean_dice');
  let sortDir = $state<'asc' | 'desc'>('desc');
  let statusFilter = $state<string>('');
  let datasetFilter = $state<string>('');

  function visible(): RunSummary[] {
    return summaries.filter((s) => {
      if (statusFilter && s.status !== statusFilter) return false;
      if (datasetFilter && !s.dataset_id.includes(datasetFilter)) return false;
      return true;
    });
  }

  function sorted(): RunSummary[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...visible()].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortBy];
      const bv = (b as unknown as Record<string, unknown>)[sortBy];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (av < bv) return -1 * mult;
      if (av > bv) return 1 * mult;
      return 0;
    });
  }

  function setSort(k: SortKey): void {
    if (sortBy === k) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else { sortBy = k; sortDir = 'desc'; }
  }

  function arrow(k: SortKey): string {
    if (sortBy !== k) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function exportCsv(): void {
    const cols: (keyof RunSummary)[] = [
      'run_id', 'dataset_id', 'plans_name', 'trainer_name', 'configuration',
      'fold', 'status', 'foreground_mean_dice',
    ];
    const csv = toCsv(sorted() as unknown as Record<string, unknown>[], cols as string[]);
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    downloadCsv(`nnunet-compare-${ts}.csv`, csv);
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2 text-[11px]">
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
           placeholder="filter dataset…" bind:value={datasetFilter} />
    <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
            bind:value={statusFilter}>
      <option value="">all statuses</option>
      <option value="completed">completed</option>
      <option value="training">training</option>
      <option value="abandoned">abandoned</option>
      <option value="failed">failed</option>
      <option value="unknown">unknown</option>
    </select>
    <span class="flex-1"></span>
    <button class="text-[11px] bg-bg-panel border border-border-soft rounded px-3 py-0.5 text-slate-200 hover:bg-bg-soft"
            onclick={exportCsv} disabled={summaries.length === 0}>
      Export CSV
    </button>
  </div>

  {#if summaries.length === 0}
    <p class="text-xs text-slate-500">No runs selected.</p>
  {:else}
    <table class="w-full text-xs">
      <thead>
        <tr class="text-slate-500 border-b border-border-soft">
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('dataset_id')}>Dataset{arrow('dataset_id')}</th>
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('configuration')}>Config{arrow('configuration')}</th>
          <th class="text-left py-1 px-2">Trainer</th>
          <th class="text-left py-1 px-2">Plans</th>
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('fold')}>Fold{arrow('fold')}</th>
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('status')}>Status{arrow('status')}</th>
          <th class="text-right py-1 px-2 cursor-pointer" onclick={() => setSort('foreground_mean_dice')}>Mean Dice{arrow('foreground_mean_dice')}</th>
        </tr>
      </thead>
      <tbody>
        {#each sorted() as r}
          <tr class="border-b border-border-soft">
            <td class="py-1 px-2 text-slate-300">{r.dataset_id}</td>
            <td class="py-1 px-2 text-slate-300">{r.configuration}</td>
            <td class="py-1 px-2 text-slate-400">{r.trainer_name}</td>
            <td class="py-1 px-2 text-slate-400">{r.plans_name}</td>
            <td class="py-1 px-2 text-slate-300">{r.fold}</td>
            <td class="py-1 px-2">
              <span class:text-ok={r.status === 'completed'} class:text-slate-500={r.status !== 'completed'}>{r.status}</span>
            </td>
            <td class="py-1 px-2 text-right text-slate-300">{r.foreground_mean_dice?.toFixed(4) ?? '—'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
```

- [ ] **Step 6: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/csv.ts frontend/src/components/csv.test.ts \
        frontend/src/components/ComparisonTable.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): ComparisonTable with sort/filter + CSV export helper"
```

---

## Task 8: `Compare.svelte` route — wire RunSelector + OverlayChart + ComparisonTable

**Files:**
- Modify: `frontend/src/routes/Compare.svelte`

- [ ] **Step 1: Replace stub**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import RunSelector from '../components/RunSelector.svelte';
  import OverlayChart from '../components/OverlayChart.svelte';
  import ComparisonTable from '../components/ComparisonTable.svelte';
  import { createCompareStore } from '../lib/stores/compare';

  const cmp = createCompareStore();
  let state = $state(cmp.get());
  let selected = $state<string[]>([]);

  onMount(() => cmp.subscribe((s) => (state = s)));

  function setSelected(ids: string[]): void {
    selected = ids;
    if (ids.length === 0) return;
    cmp.load(ids);
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Compare</h2>
<p class="text-xs text-slate-500 mt-1">
  Aggregate metric history + summary stats across runs. Reads each run's
  <code class="text-slate-400">tensorboard/</code> events on demand.
</p>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
  <RunSelector value={selected} onChange={setSelected} />

  <div class="space-y-4 min-w-0">
    {#if state.kind === 'loading'}
      <p class="text-sm text-slate-400">Loading metrics…</p>
    {:else if state.kind === 'error'}
      <p class="text-sm text-err">{state.error.message}</p>
    {:else if state.kind === 'loaded'}
      <OverlayChart metrics={state.data.metrics} />
      <ComparisonTable summaries={state.data.summaries} />
    {:else if selected.length === 0}
      <p class="text-sm text-slate-400">Pick runs on the left to compare them.</p>
    {/if}
  </div>
</div>
```

- [ ] **Step 2: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 3: Manual smoke**

Boot the server with the populated fixture (use the Phase 1 Task 20 snippet), open `http://127.0.0.1:8765/#/compare`. Tick at least one run; confirm:
- Overlay chart appears (or a "no metric history" message if the run never wrote TB events).
- The table populates with one row per selected run.
- Sorting by Mean Dice reorders rows.
- "Export CSV" downloads a file with a header row.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/Compare.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Compare route wires RunSelector + OverlayChart + ComparisonTable"
```

---

## Task 9: End-to-end smoke + docs refresh

**Files:**
- Modify: `documentation/gui.md`

- [ ] **Step 1: Full test pyramid**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && cd ..
```
Expected: all green. Phase 4's backend test count grew by ~10; frontend test count grew by ~9 (4 store + 5 CSV).

- [ ] **Step 2: Live smoke**

Re-use the Phase 1 fixture-builder snippet to create a synthetic dataset + 2 runs, and extend it to also write TB event dirs + summary.json per run:

```bash
NNUNET_RAW=$(mktemp -d) NNUNET_PRE=$(mktemp -d) NNUNET_RES=$(mktemp -d)
python -c "
from pathlib import Path
import os
from nnunetv2.tests.gui.fixtures.builders import (
    build_dataset_raw, build_dataset_preprocessed, build_run,
    build_tb_event_dir, build_run_summary,
)
raw = Path(os.environ['NNUNET_RAW']); pre = Path(os.environ['NNUNET_PRE']); res = Path(os.environ['NNUNET_RES'])
build_dataset_raw(raw, dataset_id=27, name='ACDC')
build_dataset_preprocessed(pre, dataset_folder='Dataset027_ACDC')
fold_a, _ = build_run(res, dataset_folder='Dataset027_ACDC', configuration='3d_fullres', fold='0')
fold_b, _ = build_run(res, dataset_folder='Dataset027_ACDC', configuration='2d', fold='0')
for fold, peak in ((fold_a, 0.5), (fold_b, 0.65)):
    build_tb_event_dir(fold / 'tensorboard',
        scalars=[('train_loss', [(i, 1.0/(i+1)) for i in range(20)]),
                 ('val_loss',   [(i, peak + 0.1/(i+1)) for i in range(20)])])
    build_run_summary(fold, foreground_mean_dice=0.9 - peak/10)
print('ok')
"
nnUNet_raw=$NNUNET_RAW \
nnUNet_preprocessed=$NNUNET_PRE \
nnUNet_results=$NNUNET_RES \
  nnUNetv2_gui --port 8765 &
PID=$!
sleep 2
RID1='Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0'
RID2='Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d/fold_0'
curl -s "http://127.0.0.1:8765/api/compare?run_ids=$RID1&run_ids=$RID2" | head -c 400; echo
kill $PID
```

Expected: response includes both runs' metric series + summaries with non-null `foreground_mean_dice`.

- [ ] **Step 3: Update `documentation/gui.md`**

Replace the Phase 5 line in the roadmap with `5. **Compare** ✓ — multi-run overlay + table.` and extend the "What you can do today" section:

```markdown
- Pick any N runs from **Compare**, overlay their training curves with metric/x-axis/smoothing controls.
- Sort & filter the run-summary table; export to CSV for downstream analysis.
```

- [ ] **Step 4: Commit**

```bash
git add documentation/gui.md
git commit -m "gui(docs): refresh Phase 5 roadmap entry + 'what you can do today'"
```

---

## Done condition

Phase 5 is complete when:

- [ ] `pytest nnunetv2/tests/gui/` is fully green.
- [ ] `npm test` + `svelte-check` are fully green.
- [ ] `GET /api/compare?run_ids=…` returns a payload with `metrics` + `summaries` arrays for every requested run id.
- [ ] In the browser, Compare lets the user pick any N runs, switches metrics, applies smoothing, and exports a CSV file with header + body rows.
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 5 completion.
