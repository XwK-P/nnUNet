# nnU-Net GUI — Phase 7 (Polish & System) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Final polish. Settings page (read-only env-var inspector, theme switcher already from Phase 0, server log-level toggle), tags/notes editing on Runs, system notifications on job completion, end-to-end Playwright test that boots the server in a subprocess against a synthetic dataset, optional `--gui` flag wired into `run_integration_test.sh`, and a complete `documentation/gui.md` rewrite.

**Architecture:**
- **Settings.** Extend `routers/system.py` with `GET /api/system/env` (read-only allowlist of nnUNet env vars), `GET/PUT /api/system/log_level` (in-memory toggle: DEBUG / INFO / WARNING). Theme switcher is already wired in Phase 0 — Settings UI just exposes it. A new `routers/runs.py` `PUT /api/runs/{run_id:path}` partial-updates a Run's `tags_json` / `notes`.
- **Notifications.** Pure-frontend helper `useNotifications.ts` subscribes to job-completion events on the Phase 3 SSE pipe (re-uses `connectRunEvents` for in-flight runs and the existing jobs SSE for terminal transitions). On completion, calls the browser `Notification` API (permission-prompted on first use).
- **E2E.** A new pytest module under `nnunetv2/tests/gui/e2e/` uses `pytest-playwright` to: (a) build a synthetic dataset via the Phase 1 fixture builders + a tiny checked-in `.nii.gz`, (b) boot `nnUNetv2_gui` in a subprocess on a free port, (c) drive a Chromium browser through Dashboard / Datasets / Monitor, asserting key DOM elements appear. The fixture builder ships a `build_minimal_niigz` helper to emit a small valid NIfTI on demand without external downloads.
- **Hippocampus integration.** `run_integration_test.sh` learns a `--gui` flag. When set, the script boots the GUI in the background, runs the existing integration test, hits `/api/dashboard` to snapshot the state, then kills the GUI. No CI changes; the Phase 5 (existing) integration tier already runs separately.
- **CI workflow.** `.github/workflows/gui.yml` grows a Playwright tier (Linux-only). The job installs Playwright browsers (cached) and runs `pytest nnunetv2/tests/gui/e2e/`. The rest of the workflow is untouched.
- **Docs rewrite.** `documentation/gui.md` becomes a complete user guide: install, launch, every page, troubleshooting, security notes, OS notes.

**Tech Stack:** Adds Python `pytest-playwright` (CI only, pinned to a known version) and npm `@playwright/test` (for the underlying browsers — `pytest-playwright` reuses the same browsers). No runtime production dependencies. The browser `Notification` API is W3C-standard and needs no library.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "UI Pages" → "Settings", "Notifications" decision in the foundational table, and "Testing Strategy" tier 4 (E2E smoke). Architectural decisions (locked-in): Playwright fixtures use the Phase 1 builders + **one** tiny `.nii.gz` checked into the repo at `nnunetv2/tests/gui/fixtures/data/tiny.nii.gz` (Phase 2 already added it). Linux-only CI tier.

**TDD discipline:** Tags/notes endpoint + env-var endpoint + log-level toggle are all TDD'd in tier 2 (`TestClient`). The frontend `useNotifications` helper is TDD'd in vitest. The E2E test is itself the test artifact for the Settings/Notifications UI changes; the deliverable is "the test passes locally and in CI."

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/routers/system.py` (mod) | Add `GET /api/system/env`, `GET /api/system/log_level`, `PUT /api/system/log_level` |
| `nnunetv2/gui/routers/runs.py` (mod) | Add `PUT /api/runs/{run_id:path}` partial-update for `tags_json` + `notes` |
| `nnunetv2/gui/state/runs.py` (mod) | Add `update_run_meta(cfg, run_id, *, tags_json=None, notes=None)` |
| `nnunetv2/gui/config.py` (mod) | Add `EDITABLE_ENV_VARS` allowlist constant |
| `nnunetv2/tests/gui/api/test_system_env.py` | Env-vars endpoint contract |
| `nnunetv2/tests/gui/api/test_system_log_level.py` | Log-level GET/PUT round-trip |
| `nnunetv2/tests/gui/api/test_runs_update.py` | PUT /api/runs round-trip |
| `nnunetv2/tests/gui/fixtures/builders.py` (mod) | `build_minimal_niigz(path, shape=(8,8,8))` — pure-Python writer if nibabel is available; falls back to copying the checked-in `tiny.nii.gz` otherwise |
| `nnunetv2/tests/gui/e2e/__init__.py` | Package marker |
| `nnunetv2/tests/gui/e2e/conftest.py` | Pytest fixtures: `gui_server_subprocess` (boots `nnUNetv2_gui` on a free port against a synthetic dataset tree), `page` (re-exports playwright's) |
| `nnunetv2/tests/gui/e2e/test_smoke.py` | Single end-to-end journey: navigate Dashboard → Datasets → Monitor; assert key elements |
| `nnunetv2/tests/integration_tests/run_integration_test.sh` (mod) | Add `--gui` flag handling |
| `frontend/src/lib/types.ts` (mod) | `EnvVar`, `EnvVarsResponse`, `LogLevel`, `RunUpdateRequest` |
| `frontend/src/lib/api.ts` (mod) | `getEnvVars`, `getLogLevel`, `putLogLevel`, `updateRun` |
| `frontend/src/lib/useNotifications.ts` | Pure helper: request permission, dedupe by job_id, fire on terminal transitions |
| `frontend/src/lib/useNotifications.test.ts` | vitest: permission flow + dedup |
| `frontend/src/routes/Settings.svelte` (mod) | Replace stub with env-var table, theme switcher (Phase 0 store), log-level dropdown, run tags/notes editor (live filtered) |
| `frontend/src/components/RunMetaEditor.svelte` | Inline editor for `tags` (comma-separated → JSON list) + `notes`; PUTs to the new endpoint |
| `frontend/src/routes/Datasets.svelte` (mod) | Pass an `onEditMeta` hook through `<RunsTable/>` (RunsTable is reused from Phase 1; tweak it to emit row clicks) |
| `frontend/src/App.svelte` (mod) | Call `useNotifications()` once at app boot |
| `.github/workflows/gui.yml` (mod) | Add `playwright` job (Linux only) that runs `pytest nnunetv2/tests/gui/e2e/` |
| `pyproject.toml` (mod) | Add `pytest-playwright` to `[gui]`-test extra (or a new `[dev]` group); pin minor version |
| `documentation/gui.md` (full rewrite) | Final user guide |

---

## Task 1: `routers/system.py` — env vars + log-level toggle (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/system.py`
- Modify: `nnunetv2/gui/config.py`
- Create: `nnunetv2/tests/gui/api/test_system_env.py`
- Create: `nnunetv2/tests/gui/api/test_system_log_level.py`

- [ ] **Step 1: Failing tests**

`nnunetv2/tests/gui/api/test_system_env.py`:
```python
from __future__ import annotations


def test_env_returns_known_vars(client, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", "/tmp/raw")
    monkeypatch.setenv("nnUNet_preprocessed", "/tmp/pre")
    monkeypatch.setenv("nnUNet_results", "/tmp/res")
    monkeypatch.setenv("nnUNet_n_proc_DA", "8")

    r = client.get("/api/system/env")
    assert r.status_code == 200
    body = r.json()
    names = {v["name"] for v in body["vars"]}
    assert {"nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"} <= names
    raw = [v for v in body["vars"] if v["name"] == "nnUNet_raw"][0]
    assert raw["value"] == "/tmp/raw"
    assert raw["editable"] is True


def test_env_omits_unrelated_vars(client, monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "shhh")
    r = client.get("/api/system/env")
    names = {v["name"] for v in r.json()["vars"]}
    assert "SOME_SECRET" not in names


def test_env_marks_unset_var_with_null_value(client, monkeypatch):
    monkeypatch.delenv("nnUNet_tb_logdir", raising=False)
    r = client.get("/api/system/env")
    by = {v["name"]: v for v in r.json()["vars"]}
    if "nnUNet_tb_logdir" in by:  # allowlist controls presence
        assert by["nnUNet_tb_logdir"]["value"] is None
```

`nnunetv2/tests/gui/api/test_system_log_level.py`:
```python
from __future__ import annotations


def test_get_log_level_default(client):
    r = client.get("/api/system/log_level")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] in ("DEBUG", "INFO", "WARNING", "ERROR")


def test_put_log_level_round_trip(client):
    r = client.put("/api/system/log_level", json={"level": "DEBUG"})
    assert r.status_code == 200
    assert client.get("/api/system/log_level").json()["level"] == "DEBUG"


def test_put_log_level_rejects_unknown(client):
    r = client.put("/api/system/log_level", json={"level": "BANANAS"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_system_env.py nnunetv2/tests/gui/api/test_system_log_level.py -v
```

- [ ] **Step 3: Add the allowlist in `config.py`**

Append to `nnunetv2/gui/config.py`:

```python
# Allowlist of nnUNet-related env vars surfaced in the Settings UI.
EDITABLE_ENV_VARS: tuple[str, ...] = (
    "nnUNet_raw",
    "nnUNet_preprocessed",
    "nnUNet_results",
    "nnUNet_def_n_proc",
    "nnUNet_n_proc_DA",
    "nnUNet_tb_logdir",
    "nnUNet_wandb_enabled",
    "nnUNet_tb_image_every_n_epochs",
    "nnUNet_compile",
)
```

- [ ] **Step 4: Extend `routers/system.py`**

Add at the top:

```python
import logging
import os

from pydantic import BaseModel, field_validator

from nnunetv2.gui.config import EDITABLE_ENV_VARS

_LOG_LEVEL: dict[str, str] = {"level": "INFO"}


class LogLevelUpdate(BaseModel):
    level: str

    @field_validator("level")
    @classmethod
    def _validate(cls, v: str) -> str:
        if v.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError("invalid level")
        return v.upper()
```

Inside `make_router()`, add:

```python
    @router.get("/env")
    def env() -> dict:
        return {
            "vars": [
                {
                    "name": name,
                    "value": os.environ.get(name),
                    "editable": True,
                }
                for name in EDITABLE_ENV_VARS
            ],
        }

    @router.get("/log_level")
    def get_log_level() -> dict:
        return {"level": _LOG_LEVEL["level"]}

    @router.put("/log_level")
    def put_log_level(update: LogLevelUpdate) -> dict:
        _LOG_LEVEL["level"] = update.level
        logging.getLogger().setLevel(update.level)
        return {"level": _LOG_LEVEL["level"]}
```

Note that the bad-level case is reported by FastAPI as 422 by default. Override to 400 by adding a dedicated handler or catch `ValueError` in `put_log_level` and re-raise `HTTPException(400, …)`. Simplest: replace the validator with manual validation in the handler:

```python
    @router.put("/log_level")
    def put_log_level(payload: dict) -> dict:
        from fastapi import HTTPException
        level = (payload.get("level") or "").upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise HTTPException(status_code=400, detail="invalid level")
        _LOG_LEVEL["level"] = level
        logging.getLogger().setLevel(level)
        return {"level": _LOG_LEVEL["level"]}
```

- [ ] **Step 5: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_system_env.py nnunetv2/tests/gui/api/test_system_log_level.py -v
git add nnunetv2/gui/routers/system.py nnunetv2/gui/config.py \
        nnunetv2/tests/gui/api/test_system_env.py nnunetv2/tests/gui/api/test_system_log_level.py
git commit -m "gui(api): /api/system/env + /api/system/log_level read+write"
```

---

## Task 2: Run tags/notes — `PUT /api/runs/{run_id:path}` (TDD)

**Files:**
- Modify: `nnunetv2/gui/state/runs.py`
- Modify: `nnunetv2/gui/routers/runs.py`
- Create: `nnunetv2/tests/gui/api/test_runs_update.py`

- [ ] **Step 1: Failing tests**

`nnunetv2/tests/gui/api/test_runs_update.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_update_tags_and_notes(populated_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    r = populated_client.put(f"/api/runs/{rid}",
                              json={"tags": ["baseline", "v1"], "notes": "initial run"})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "initial run"
    # tags_json stored as JSON; surface back as parsed list
    import json
    assert json.loads(body["tags_json"]) == ["baseline", "v1"]


def test_update_partial_keeps_other_fields(populated_client):
    rid = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    populated_client.put(f"/api/runs/{rid}", json={"tags": ["t1"]})
    populated_client.put(f"/api/runs/{rid}", json={"notes": "n1"})
    r = populated_client.get(f"/api/runs/{rid}")
    body = r.json()
    import json
    assert json.loads(body["tags_json"]) == ["t1"]
    assert body["notes"] == "n1"


def test_update_unknown_run_returns_404(populated_client):
    r = populated_client.put("/api/runs/Dataset999_X/p__t__c/fold_0",
                              json={"notes": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run; confirm fail**

- [ ] **Step 3: Add `update_run_meta` to `state/runs.py`**

Append:

```python
def update_run_meta(
    cfg: GuiConfig,
    run_id: str,
    *,
    tags_json: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Run]:
    """Partial-update the GUI-only fields on a run. None means 'leave as-is'."""
    existing = get_run(cfg, run_id)
    if existing is None:
        return None
    values = {}
    if tags_json is not None:
        values["tags_json"] = tags_json
    if notes is not None:
        values["notes"] = notes
    if not values:
        return existing
    with session_scope(cfg) as s:
        s.execute(run_table.update().where(run_table.c.id == run_id).values(**values))
    return get_run(cfg, run_id)
```

- [ ] **Step 4: Add the PUT route to `routers/runs.py`**

Add near the existing `get_one` handler:

```python
import json
from typing import Optional

from pydantic import BaseModel


class RunUpdateRequest(BaseModel):
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


# inside make_router():
    @router.put("/{run_id:path}", response_model=Run)
    def update_run(run_id: str, body: RunUpdateRequest, request: Request) -> Run:
        from nnunetv2.gui.state.runs import update_run_meta
        cfg = request.app.state.gui_config
        tags_json = json.dumps(body.tags) if body.tags is not None else None
        result = update_run_meta(cfg, run_id, tags_json=tags_json, notes=body.notes)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return result
```

- [ ] **Step 5: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_runs_update.py -v
git add nnunetv2/gui/state/runs.py nnunetv2/gui/routers/runs.py nnunetv2/tests/gui/api/test_runs_update.py
git commit -m "gui(api): PUT /api/runs/{id} partial-update for tags + notes"
```

---

## Task 3: Settings route + RunMetaEditor (frontend)

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/Settings.svelte`
- Create: `frontend/src/components/RunMetaEditor.svelte`

- [ ] **Step 1: Types + endpoints**

Append to `frontend/src/lib/types.ts`:

```ts
export interface EnvVar {
  name: string;
  value: string | null;
  editable: boolean;
}

export interface EnvVarsResponse {
  vars: EnvVar[];
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';

export interface RunUpdateRequest {
  tags?: string[];
  notes?: string;
}
```

Append to `endpoints` in `frontend/src/lib/api.ts`:

```ts
import type { EnvVarsResponse, LogLevel, Run, RunUpdateRequest } from './types';

  // inside endpoints:
  getEnvVars: () => api.get<EnvVarsResponse>('/api/system/env'),
  getLogLevel: () => api.get<{ level: LogLevel }>('/api/system/log_level'),
  putLogLevel: (level: LogLevel) => api.put<{ level: LogLevel }>('/api/system/log_level', { level }),
  updateRun: (id: string, body: RunUpdateRequest) => api.put<Run>(`/api/runs/${id}`, body),
```

If `api.put` does not exist yet, add it next to `api.get` / `api.post`:

```ts
  put<T>(url: string, body: unknown): Promise<T> {
    return request<T>(url, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
```

- [ ] **Step 2: `RunMetaEditor.svelte`**

```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';
  import type { Run } from '../lib/types';

  let { run, onSaved }: { run: Run; onSaved: (updated: Run) => void } = $props();

  let tagsText = $state<string>(parseTags(run.tags_json).join(', '));
  let notes = $state<string>(run.notes ?? '');
  let busy = $state(false);
  let error = $state<string | null>(null);

  function parseTags(s: string | null): string[] {
    if (!s) return [];
    try { return JSON.parse(s); } catch { return []; }
  }

  async function save() {
    busy = true; error = null;
    try {
      const updated = await endpoints.updateRun(run.id, {
        tags: tagsText.split(',').map((t) => t.trim()).filter(Boolean),
        notes,
      });
      onSaved(updated);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally { busy = false; }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">{run.id}</h4>
  <label class="block text-[11px] text-slate-500 mt-2">Tags (comma-separated)</label>
  <input class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
         bind:value={tagsText} placeholder="baseline, v1" />
  <label class="block text-[11px] text-slate-500 mt-2">Notes</label>
  <textarea class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100 min-h-20"
            bind:value={notes}></textarea>
  {#if error}<p class="text-[11px] text-err mt-2">{error}</p>{/if}
  <div class="mt-2 flex justify-end">
    <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={save}>
      {busy ? 'Saving…' : 'Save'}
    </button>
  </div>
</div>
```

- [ ] **Step 3: Settings route**

Replace `frontend/src/routes/Settings.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints } from '../lib/api';
  import type { EnvVarsResponse, LogLevel, Run } from '../lib/types';
  import { createRunsStore } from '../lib/stores/runs';
  import { createThemeStore } from '../lib/stores/theme';
  import RunMetaEditor from '../components/RunMetaEditor.svelte';

  let env = $state<EnvVarsResponse | null>(null);
  let logLevel = $state<LogLevel>('INFO');
  let envError = $state<string | null>(null);

  const theme = createThemeStore();
  let currentTheme = $state(theme.get());

  const runs = createRunsStore();
  let runsState = $state(runs.get());
  let selected = $state<Run | null>(null);

  onMount(() => {
    const unsub = runs.subscribe((s) => (runsState = s));
    runs.load({});
    theme.subscribe((v) => (currentTheme = v));
    endpoints.getEnvVars().then((d) => env = d).catch((e) => envError = String(e));
    endpoints.getLogLevel().then((d) => logLevel = d.level);
    return unsub;
  });

  async function changeLogLevel(next: LogLevel) {
    const res = await endpoints.putLogLevel(next);
    logLevel = res.level;
  }

  function onSaved(updated: Run): void {
    selected = updated;
    runs.load({});  // refresh table
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Settings</h2>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
  <section class="bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Environment variables (read-only)</h3>
    {#if envError}<p class="text-xs text-err">{envError}</p>{/if}
    {#if env}
      <table class="w-full text-xs">
        <thead>
          <tr class="text-slate-500 border-b border-border-soft">
            <th class="text-left py-1">Name</th>
            <th class="text-left py-1">Value</th>
          </tr>
        </thead>
        <tbody>
          {#each env.vars as v}
            <tr>
              <td class="py-1 text-slate-300 font-mono">{v.name}</td>
              <td class="py-1 text-slate-400 font-mono">{v.value ?? <span class="text-slate-600">— unset —</span>}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="text-[11px] text-slate-500 mt-2">Edit these in your shell, restart the server, then refresh this page.</p>
    {/if}
  </section>

  <section class="bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Server</h3>
    <div class="text-xs flex items-center gap-2">
      <label class="text-slate-500">Log level</label>
      <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
              onchange={(e) => changeLogLevel((e.currentTarget as HTMLSelectElement).value as LogLevel)}
              value={logLevel}>
        {#each ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as l}
          <option value={l} selected={logLevel === l}>{l}</option>
        {/each}
      </select>
    </div>

    <h3 class="text-xs uppercase tracking-wider text-slate-500 mt-4 mb-2">Theme</h3>
    <div class="text-xs flex items-center gap-2">
      {#each ['light', 'dark', 'system'] as t}
        <button class="px-2 py-0.5 rounded"
                class:bg-bg-panel={currentTheme === t}
                class:text-slate-100={currentTheme === t}
                class:text-slate-500={currentTheme !== t}
                onclick={() => theme.set(t as 'light' | 'dark' | 'system')}>
          {t}
        </button>
      {/each}
    </div>
  </section>

  <section class="xl:col-span-2 bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Run tags & notes</h3>
    <div class="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-3">
      <div class="bg-bg-base border border-border-soft rounded p-2 max-h-80 overflow-auto">
        {#if runsState.kind === 'loaded'}
          <ul class="text-xs space-y-0.5">
            {#each runsState.data as r}
              <li>
                <button class="text-left w-full px-2 py-1 hover:bg-bg-panel rounded"
                        class:text-accent={selected?.id === r.id}
                        class:text-slate-300={selected?.id !== r.id}
                        onclick={() => selected = r}>
                  {r.id}
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
      <div>
        {#if selected}
          <RunMetaEditor run={selected} {onSaved} />
        {:else}
          <p class="text-sm text-slate-400">Pick a run on the left to add tags or notes.</p>
        {/if}
      </div>
    </div>
  </section>
</div>
```

- [ ] **Step 4: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/lib/types.ts frontend/src/lib/api.ts \
        frontend/src/components/RunMetaEditor.svelte frontend/src/routes/Settings.svelte \
        nnunetv2/gui/web/
git commit -m "gui(frontend): Settings page (env vars / log level / theme / run tags+notes)"
```

---

## Task 4: System notifications — `useNotifications` helper (TDD)

**Files:**
- Create: `frontend/src/lib/useNotifications.ts`
- Create: `frontend/src/lib/useNotifications.test.ts`
- Modify: `frontend/src/App.svelte`

- [ ] **Step 1: Failing tests**

`frontend/src/lib/useNotifications.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createNotifier } from './useNotifications';

describe('createNotifier', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('requests permission once on first event', async () => {
    const requestPermission = vi.fn().mockResolvedValue('granted');
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'default';
    (globalThis as any).Notification.requestPermission = requestPermission;

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect((globalThis as any).Notification).toHaveBeenCalledTimes(1);
  });

  it('does not re-fire for same job_id', async () => {
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'granted';
    (globalThis as any).Notification.requestPermission = vi.fn();

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect((globalThis as any).Notification).toHaveBeenCalledTimes(1);
  });

  it('does nothing when permission denied', async () => {
    const requestPermission = vi.fn().mockResolvedValue('denied');
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'default';
    (globalThis as any).Notification.requestPermission = requestPermission;

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect((globalThis as any).Notification).not.toHaveBeenCalled();
  });

  it('only fires for terminal statuses', async () => {
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'granted';
    (globalThis as any).Notification.requestPermission = vi.fn();

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'running' });
    await n.fire({ jobId: 1, kind: 'train', status: 'starting' });
    await n.fire({ jobId: 1, kind: 'train', status: 'queued' });

    expect((globalThis as any).Notification).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run; confirm fail**

```bash
cd frontend && npm test -- useNotifications
```

- [ ] **Step 3: Implement `useNotifications.ts`**

```ts
type Status = 'queued' | 'starting' | 'running' | 'completed' | 'failed' | 'killed' | 'cancelled' | 'unknown';

interface JobEvent {
  jobId: number;
  kind: string;
  status: Status;
}

const TERMINAL: Set<Status> = new Set(['completed', 'failed', 'killed', 'cancelled']);

export function createNotifier() {
  const seen = new Set<number>();
  let permission: NotificationPermission | null = null;

  async function ensurePermission(): Promise<NotificationPermission> {
    if (typeof Notification === 'undefined') return 'denied';
    if (permission) return permission;
    if (Notification.permission === 'default') {
      permission = await Notification.requestPermission();
    } else {
      permission = Notification.permission;
    }
    return permission;
  }

  return {
    async fire(ev: JobEvent): Promise<void> {
      if (!TERMINAL.has(ev.status)) return;
      if (seen.has(ev.jobId)) return;
      const perm = await ensurePermission();
      if (perm !== 'granted') return;
      seen.add(ev.jobId);
      new Notification(`Job #${ev.jobId} ${ev.status}`, {
        body: `${ev.kind} job finished`,
        tag: `job-${ev.jobId}`,
      });
    },
    reset(): void {
      seen.clear();
      permission = null;
    },
  };
}

let _singleton: ReturnType<typeof createNotifier> | null = null;
export function useNotifications() {
  if (!_singleton) _singleton = createNotifier();
  return _singleton;
}
```

- [ ] **Step 4: Wire into `App.svelte`**

Add an `onMount` block to `frontend/src/App.svelte` that subscribes to a future jobs SSE stream OR polls `/api/jobs?status=…` every 5 s and pipes new terminal transitions into the notifier. For Phase 7 we use the lightweight polling approach (the heavier SSE option remains a future polish):

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { useNotifications } from './lib/useNotifications';
  import { endpoints } from './lib/api';
  // ... existing imports ...

  onMount(() => {
    const notifier = useNotifications();
    const seen = new Map<number, string>();
    const tick = async () => {
      try {
        const jobs = await endpoints.getJobs();
        for (const j of jobs) {
          if (seen.get(j.id) !== j.status) {
            seen.set(j.id, j.status);
            notifier.fire({ jobId: j.id, kind: j.kind, status: j.status as any });
          }
        }
      } catch { /* swallow */ }
    };
    const id = setInterval(tick, 5000);
    tick();
    return () => clearInterval(id);
  });
</script>
```

(`endpoints.getJobs` already exists from Phase 3 — verify the import surface.)

- [ ] **Step 5: Pass + commit**

```bash
cd frontend && npm test
git add frontend/src/lib/useNotifications.ts frontend/src/lib/useNotifications.test.ts frontend/src/App.svelte
git commit -m "gui(frontend): useNotifications helper + 5s job-status poll fires browser Notifications"
```

---

## Task 5: Synthetic-dataset fixture for E2E — `build_minimal_niigz` (TDD)

**Files:**
- Modify: `nnunetv2/tests/gui/fixtures/builders.py`
- Modify: `nnunetv2/tests/gui/unit/test_fixture_builders.py` (or create if missing)

- [ ] **Step 1: Failing test**

`nnunetv2/tests/gui/unit/test_fixture_builders.py` (append or create):
```python
from __future__ import annotations

from pathlib import Path

from nnunetv2.tests.gui.fixtures.builders import build_minimal_niigz


def test_build_minimal_niigz_writes_valid_file(tmp_path: Path):
    p = build_minimal_niigz(tmp_path / "case_001_0000.nii.gz", shape=(4, 4, 4))
    assert p.is_file()
    assert p.stat().st_size > 0
    # Confirm nibabel can open it back
    import nibabel as nib
    img = nib.load(str(p))
    arr = img.get_fdata()
    assert arr.shape == (4, 4, 4)
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_fixture_builders.py -v -k niigz
```

- [ ] **Step 3: Implement `build_minimal_niigz`**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_minimal_niigz(
    target: Path,
    *,
    shape: tuple[int, int, int] = (8, 8, 8),
    seed: int = 0,
) -> Path:
    """Write a tiny valid NIfTI to `target`.

    Uses nibabel if available; otherwise copies the checked-in tiny.nii.gz
    fixture from `fixtures/data/tiny.nii.gz` (Phase 2 added this file).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
        import nibabel as nib
    except ImportError:
        src = Path(__file__).parent / "data" / "tiny.nii.gz"
        if not src.is_file():
            raise RuntimeError(
                "nibabel unavailable and no fallback tiny.nii.gz checked in"
            )
        target.write_bytes(src.read_bytes())
        return target

    rng = np.random.default_rng(seed)
    arr = (rng.random(shape) * 255).astype("float32")
    img = nib.Nifti1Image(arr, affine=np.eye(4))
    nib.save(img, str(target))
    return target
```

- [ ] **Step 4: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_fixture_builders.py -v
git add nnunetv2/tests/gui/fixtures/builders.py nnunetv2/tests/gui/unit/test_fixture_builders.py
git commit -m "gui(tests): build_minimal_niigz fixture helper (nibabel or checked-in fallback)"
```

---

## Task 6: Playwright E2E smoke test

**Files:**
- Modify: `pyproject.toml`
- Create: `nnunetv2/tests/gui/e2e/__init__.py` (empty)
- Create: `nnunetv2/tests/gui/e2e/conftest.py`
- Create: `nnunetv2/tests/gui/e2e/test_smoke.py`

- [ ] **Step 1: Add `pytest-playwright` to a `[gui-e2e]` extras (or `[dev]`)**

In `pyproject.toml`, under `[project.optional-dependencies]`:

```toml
gui-e2e = [
    "pytest-playwright>=0.5.0,<1",
]
```

Document in `documentation/gui.md` (Task 9 below): `pip install -e ".[gui,gui-e2e]" && playwright install --with-deps chromium` for contributors.

- [ ] **Step 2: Conftest — boot the server in a subprocess against a synthetic tree**

`nnunetv2/tests/gui/e2e/conftest.py`:
```python
"""Playwright fixtures: boot nnUNetv2_gui against a synthetic dataset tree."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nnunetv2.tests.gui.fixtures.builders import (
    build_dataset_raw, build_dataset_preprocessed, build_run, build_minimal_niigz,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError(f"server did not come up at {url} within {timeout}s")


@pytest.fixture(scope="session")
def synthetic_tree(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("nnunet_e2e")
    raw = root / "raw"; pre = root / "preprocessed"; res = root / "results"
    raw.mkdir(); pre.mkdir(); res.mkdir()

    build_dataset_raw(raw, dataset_id=27, name="E2EDemo")
    # Place a real .nii.gz so the Cases tab is meaningful
    ds_dir = raw / "Dataset027_E2EDemo"
    build_minimal_niigz(ds_dir / "imagesTr" / "case_001_0000.nii.gz", shape=(8, 8, 8))
    build_minimal_niigz(ds_dir / "labelsTr" / "case_001.nii.gz", shape=(8, 8, 8))

    build_dataset_preprocessed(pre, dataset_folder="Dataset027_E2EDemo")
    build_run(res, dataset_folder="Dataset027_E2EDemo", configuration="3d_fullres", fold="0")

    return {"raw": raw, "preprocessed": pre, "results": res}


@pytest.fixture(scope="session")
def gui_server_subprocess(synthetic_tree) -> str:
    port = _free_port()
    env = os.environ.copy()
    env.update(
        nnUNet_raw=str(synthetic_tree["raw"]),
        nnUNet_preprocessed=str(synthetic_tree["preprocessed"]),
        nnUNet_results=str(synthetic_tree["results"]),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "nnunetv2.gui.cli", "--port", str(port), "--host", "127.0.0.1"],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{url}/api/system/healthz")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 3: The smoke test**

`nnunetv2/tests/gui/e2e/test_smoke.py`:
```python
"""E2E smoke: boot the GUI, navigate Dashboard → Datasets → Monitor."""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_dashboard_loads_and_shows_counts(page, gui_server_subprocess):
    page.goto(gui_server_subprocess)
    page.wait_for_selector("text=Dashboard")
    # Synthetic tree has 1 dataset + 1 run
    page.wait_for_selector("text=Datasets")
    # Cards include the words "raw" and "preprocessed"
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
```

- [ ] **Step 4: Run locally**

```bash
pip install -e ".[gui,gui-e2e]"
playwright install --with-deps chromium
pytest nnunetv2/tests/gui/e2e/ -v
```
Expected: 3 passes within ~30 s.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml nnunetv2/tests/gui/e2e/__init__.py \
        nnunetv2/tests/gui/e2e/conftest.py nnunetv2/tests/gui/e2e/test_smoke.py
git commit -m "gui(e2e): playwright smoke — boot server, walk Dashboard/Datasets/Monitor"
```

---

## Task 7: Hippocampus integration — `--gui` flag in `run_integration_test.sh`

**Files:**
- Modify: `nnunetv2/tests/integration_tests/run_integration_test.sh`

- [ ] **Step 1: Add the flag plumbing**

Near the top of the script (after the existing argument parsing), add:

```bash
GUI_ENABLED=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --gui) GUI_ENABLED=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]}"
```

Before the existing `nnUNetv2_train` / pipeline invocation, add:

```bash
GUI_PID=""
if [ "$GUI_ENABLED" = "1" ]; then
  echo "[integration] booting nnUNetv2_gui on port 8765"
  nnUNetv2_gui --host 127.0.0.1 --port 8765 >/tmp/nnunet_gui.log 2>&1 &
  GUI_PID=$!
  # Wait until /api/system/healthz returns 200
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8765/api/system/healthz >/dev/null; then break; fi
    sleep 0.5
  done
fi
```

After the pipeline finishes, before the script's normal exit:

```bash
if [ -n "$GUI_PID" ]; then
  echo "[integration] snapshotting dashboard"
  curl -s http://127.0.0.1:8765/api/dashboard > /tmp/nnunet_gui_dashboard.json
  kill "$GUI_PID" || true
  wait "$GUI_PID" 2>/dev/null || true
fi
```

- [ ] **Step 2: Smoke-run locally if a Hippocampus run is feasible**

```bash
bash nnunetv2/tests/integration_tests/run_integration_test.sh 4 --gui
cat /tmp/nnunet_gui_dashboard.json | head -c 400
```

Expected: dashboard JSON includes the Hippocampus dataset / run in the counts.

- [ ] **Step 3: Commit**

```bash
git add nnunetv2/tests/integration_tests/run_integration_test.sh
git commit -m "tests(integration): --gui flag boots GUI alongside the Hippocampus pipeline"
```

---

## Task 8: CI workflow — add Playwright tier

**Files:**
- Modify: `.github/workflows/gui.yml`

- [ ] **Step 1: Append a new job to `gui.yml`**

After the existing Python / Node tiers, add:

```yaml
  playwright:
    runs-on: ubuntu-latest
    needs: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install
        run: |
          pip install -e ".[gui,gui-e2e]"
      - name: Install Playwright browsers (cached)
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ hashFiles('pyproject.toml') }}
      - name: Install browser dependencies
        run: playwright install --with-deps chromium
      - name: Run E2E smoke
        run: pytest nnunetv2/tests/gui/e2e/ -v --tb=short
```

- [ ] **Step 2: Push to a branch, confirm CI runs all four tiers**

Push a draft PR; expected: Python unit/api green, Node green, Playwright green. Total runtime under ~5 min on standard runners.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/gui.yml
git commit -m "ci(gui): add Playwright E2E job on Linux"
```

---

## Task 9: Final `documentation/gui.md` rewrite

**Files:**
- Modify: `documentation/gui.md`

- [ ] **Step 1: Replace the file with the final user guide**

```markdown
# nnU-Net GUI Manager

A browser-based experiment & dataset manager that wraps every `nnUNetv2_*` CLI command. Local-first, single-user, no auth by default. The GUI never replaces the CLI — it spawns CLI subprocesses, monitors them, and reflects everything on disk.

## Install

```bash
pip install "nnunetv2[gui]"
```

For contributors:

```bash
pip install -e ".[gui,gui-e2e]"
cd frontend && npm install && npm run build
```

To run the E2E test locally, also: `playwright install --with-deps chromium`.

## Launch

```bash
nnUNetv2_gui --open
```

Opens the GUI at http://127.0.0.1:8765 in your default browser.

### Flags

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind host. Non-loopback hosts require `--token`. |
| `--port` | `8765` | Bind port. |
| `--token` | unset | Bearer token; required when `--host` is not loopback. |
| `--raw` | `$nnUNet_raw` | Override the raw-data root. |
| `--preprocessed` | `$nnUNet_preprocessed` | Override the preprocessed-data root. |
| `--results` | `$nnUNet_results` | Override the results root. |
| `--open` | off | Open the GUI in the default browser after startup. |

## Pages

- **Dashboard** — counts, recent runs, disk usage, GPU memory.
- **Datasets** — every `Dataset*` under `$nnUNet_raw`. Per-dataset tabs: Cases (NiiVue viewer), Plans, Fingerprint, Validation, Convert.
- **Train** — multi-fold queue with GPU contention warning. The "Preview CLI" expands the equivalent `nnUNetv2_train …` command.
- **Monitor** — live curves (`uPlot`), log tail, image samples, checkpoint list. SSE-multiplexed on `/sse/runs/{run_id}/events`.
- **Compare** — pick N runs, overlay metric curves, sort & filter the summary table, export CSV.
- **Predict** — launch form + 3-pane viewer (input · GT · prediction) + per-case Dice table.
- **Models** — per-Model fold/checkpoint list, export to zip, import zip, `find_best_configuration`, ensemble across configs, apply postprocessing.
- **Jobs** — every spawned process with Stop / Cancel / Restart actions.
- **Settings** — env-vars table, theme switcher, server log level, run tags & notes.

## Workflow

1. Set environment variables (`nnUNet_raw`, `nnUNet_preprocessed`, `nnUNet_results`).
2. Drop a dataset into `$nnUNet_raw` (or convert via the GUI).
3. Pick **Preprocess** on the dataset detail page.
4. Train: choose folds, configuration, trainer; click Launch.
5. Monitor: switch to Monitor and watch curves stream.
6. Compare: tick the runs you care about; export CSV.
7. Predict: point at an input folder and an output folder; review the 3-pane viewer per case.
8. Postprocess / find_best / ensemble: pick prediction folders, queue the job.
9. Export: turn a Model into a zip; share or archive.

## Notifications

When a job reaches a terminal state (completed / failed / killed / cancelled), the browser fires a desktop notification. Permission is requested on first job completion. Disable in Settings (or in the browser's notification permission UI).

## Security

The server binds to `127.0.0.1` and requires no authentication by default. Binding to a non-loopback host requires `--token <hex>`, which becomes the bearer token required on every request.

The GUI never sends data off your machine. No telemetry. No outgoing network requests.

## OS support

macOS and Linux are first-class. Windows is best-effort:
- Process-group semantics use `CREATE_NEW_PROCESS_GROUP` instead of `setsid`.
- The system-notification helper is a no-op on browsers that block desktop notifications.

## Troubleshooting

- **Browser shows "Loading dashboard…" forever.** Check that the three env vars point at writable directories. Open `/api/system/diag` in a tab and inspect `paths`.
- **No runs show up.** Confirm `$nnUNet_results` contains `DatasetXXX_*/<plans>__<trainer>__<config>/fold_*` directories with at least one file.
- **Live monitor flickers.** The TB tailer self-disables after 5 consecutive failures and surfaces a banner with a Retry button.
- **A subprocess survived a server restart.** That's by design — the GUI re-attaches by PID on boot. Check the Jobs page; the row should flip from `unknown` to a terminal state once the subprocess exits.

## Roadmap

The full design lives at [docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md](../docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md). v1 ships in 8 phases:

0. **Foundation** ✓ — scaffold, CLI, healthz.
1. **Read-only browse** ✓ — filesystem discovery, dataset/run lists, plans/fingerprint inspector, dashboard cards.
2. **Image viewer** ✓ — NiiVue, case browser, prediction review.
3. **Live monitoring** ✓ — TB tailer, Monitor page, Jobs read-only.
4. **Job launching** ✓ — preprocess/train/predict + multi-fold queue + stop/cancel/restart.
5. **Compare** ✓ — multi-run overlay + table + CSV export.
6. **Inference polish + Models** ✓ — 3-pane viewer, per-case metrics, find_best, ensembling, postproc, export/import.
7. **Polish & system** ✓ — settings, env vars, theme, run tags & notes, notifications, e2e, Hippocampus integration.

## Out of v1 scope

- Plans editor (write).
- Multi-machine job queue / remote agents.
- OAuth/OIDC.
- Plugin API for third-party panels.
- Mobile/tablet responsive layout.
- DICOM as a first-class input format end-to-end.
```

- [ ] **Step 2: Commit**

```bash
git add documentation/gui.md
git commit -m "gui(docs): final user-guide rewrite for v1 release"
```

---

## Done condition

Phase 7 — and the v1 GUI — is complete when:

- [ ] `pytest nnunetv2/tests/gui/` is fully green (unit + API).
- [ ] `pytest nnunetv2/tests/gui/e2e/ -v` passes locally (with Playwright installed).
- [ ] `npm test` + `svelte-check` are fully green.
- [ ] CI workflow shows all four tiers green on a PR: Python tier 1+2, Node tier 3, Playwright tier 4.
- [ ] `/api/system/env`, `/api/system/log_level`, `PUT /api/runs/{id}` all behave per the unit tests.
- [ ] Browser: Settings page renders the env-var table, theme switcher, log-level dropdown, and run tags/notes editor. Saving notes persists across navigation and survives a server restart (because the row is in SQLite).
- [ ] A long-running job in the Jobs page fires a browser notification on completion.
- [ ] `bash nnunetv2/tests/integration_tests/run_integration_test.sh 4 --gui` (when a GPU is available) snapshots `/api/dashboard` containing the Hippocampus run.
- [ ] `documentation/gui.md` reads as a complete user guide; the Roadmap shows all 8 phases checked off.
- [ ] No nnUNet core training/inference code was modified across the entire 8-phase build.
