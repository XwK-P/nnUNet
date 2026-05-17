# nnU-Net GUI Experiment & Dataset Manager — Design

**Status:** Draft
**Date:** 2026-05-16
**Author:** Puyang Wang (with Claude)

## Summary

Add a first-class, browser-based experiment-and-dataset manager that wraps every public nnU-Net CLI command and exposes the contents of `nnUNet_raw`, `nnUNet_preprocessed`, and `nnUNet_results` through a coherent UI. The product is a **FastAPI server + Svelte SPA**, installed as an optional extra (`pip install nnunetv2[gui]`) and launched with `nnUNetv2_gui`. The GUI does not replace the CLI: it spawns CLI subprocesses, monitors them, and surfaces their outputs.

In a single browser, a user can browse and validate datasets, view NIfTI cases with overlays, inspect plans/fingerprints, launch and monitor preprocessing/training/inference, compare runs across folds and datasets, review predictions, apply postprocessing/ensembling, and export models.

## Goals

- **Full-coverage v1.** Every workflow currently exposed by `nnUNetv2_*` CLI tools is reachable from the GUI.
- **Don't be a wall.** Users can keep using the CLI in parallel; the GUI discovers anything that lands on disk and tracks GUI-launched jobs in SQLite. The two stay coherent.
- **Disposable scaffolding.** A GUI crash or restart never affects a running training job.
- **Local-first.** Defaults bind `127.0.0.1`, no auth, no telemetry. Works on a single workstation today; works over SSH tunnel tomorrow without rewrite.
- **Don't fork training code.** No re-implementation of nnUNet training, planning, or inference inside the GUI. The GUI spawns the existing CLI entry points.

## Non-Goals (v1)

- Multi-user authentication, RBAC, account systems, SSO.
- Distributed job scheduling across multiple machines (single-host only).
- Replacing TensorBoard. TB stays the source of truth for live metrics; the GUI tails the same event files. A "Open in TensorBoard" escape hatch is provided.
- Pixel-perfect mobile responsiveness. Desktop browser only.
- A plugin/extension API for third-party panels. Subclassable trainer/planner extension already exists in nnUNet; the GUI reflects on those classes.
- Editing `plans.json` from the UI (read-only inspector in v1; editing deferred).
- Telemetry, analytics, or any network traffic outside `localhost`.

## Foundational Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary user | Solo researcher, single workstation | Removes auth/queueing/multi-tenant scope. |
| UI architecture | FastAPI + Svelte 5 SPA | Best in-browser NIfTI viewer (NiiVue) + real charting + SSE for live data; matches TensorBoard's deployment shape. |
| Information architecture | Sidebar nav + persistent dataset "workspace" header | Most nnUNet workflows are dataset-scoped, but Compare/Jobs/Models are cross-cutting. Sidebar covers both. |
| Job lifecycle | Detached process groups (`setsid` / `CREATE_NEW_PROCESS_GROUP`) | Trainings survive GUI restart; the GUI re-attaches by PID. |
| Run discovery | Hybrid: SQLite for GUI-launched + filesystem watcher for CLI-launched | GUI never blocks CLI use. |
| Live metrics source | Tail per-run `tensorboard/` event files via `tbparse` | Zero changes to trainer code; works for in-flight and historical runs. |
| Image viewer | NiiVue (WebGL2) for NIfTI; native canvas for 2D PNG/TIF | Production-grade in-browser; reused across dataset preview and prediction review. |
| Concurrency | No hard cap; soft warning when projected GPU memory > free | Single-user workstation; the warning is enough friction. |
| Persistent state | SQLite at `$nnUNet_results/.nnunet_gui/state.db` (WAL) | Cache + GUI-only metadata; filesystem stays the source of truth for run outputs. |
| Binding / auth | `127.0.0.1` only by default. Non-loopback bind requires `--token <hex>` and enforces bearer auth. | Safe default for an internal tool. |
| Notifications | In-app toast + optional system notification helper | Useful for long-running jobs without being intrusive. |

## In-Scope Capabilities (all required for v1)

1. Dataset browser & image preview (NiiVue with overlays).
2. Dataset validation, conversion (MSD→nnU-Net), plans/fingerprint inspector.
3. Preprocessing launcher.
4. Training launcher (all CLI flags, multi-fold queue, GPU warning, CLI-equivalent preview).
5. Live training monitor (curves, image samples, log, config, checkpoints).
6. Run comparison (multi-run overlay, sortable table, CSV export).
7. Inference launcher & prediction viewer (3-pane + overlay, per-case metrics when GT exists).
8. Postprocessing, `find_best_configuration`, ensembling, model export/import.
9. Job/process manager (running + recent, full logs, stop/restart).

## Architecture

### Process model

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│ Browser (Svelte 5 SPA)      │  HTTP  │ Uvicorn + FastAPI                │
│  • NiiVue viewer            │ ◀────▶ │  • REST routers + SSE streams    │
│  • uPlot charts             │  SSE   │  • SQLite (state.db)             │
│  • forms / tables           │ ◀───── │  • watchfiles filesystem watcher │
└─────────────────────────────┘        │  • tb_tailer / log_tailer        │
                                       │  • subprocess launcher           │
                                       └──────────────┬───────────────────┘
                                                      │ Popen with setsid
                                       ┌──────────────▼───────────────────┐
                                       │ Detached process groups          │
                                       │  • nnUNetv2_train …              │
                                       │  • nnUNetv2_predict …            │
                                       │  • nnUNetv2_plan_and_preprocess… │
                                       └──────────────────────────────────┘
```

The Svelte app is a static bundle served from `/`. All dynamic traffic goes to `/api/*` (REST) and `/sse/*` (one-way streams). The server never imports nnUNet training/inference code at runtime; it only reads on-disk artifacts and shells out for new work.

### Repository layout (additions only)

```
nnunetv2/
  gui/
    __init__.py
    cli.py                  # nnUNetv2_gui entry point (argparse)
    server.py               # FastAPI app factory + router registration
    config.py               # paths, env vars, host/port/token resolution
    db.py                   # SQLAlchemy engine, schema, migrations
    state/
      jobs.py               # Job records, lifecycle, transitions
      runs.py               # Run = on-disk fold folder, identified by canonical key
      datasets.py           # Dataset records
      discovery.py          # watchfiles wiring + initial reconciliation scan
    jobs/
      launcher.py           # Popen wrappers, OS-specific process-group setup
      reaper.py             # background task awaiting PID exits
      log_tailer.py         # aiofiles tail → SSE
      tb_tailer.py          # tbparse incremental read → metric dicts → SSE
    routers/
      datasets.py
      plans.py
      preprocess.py
      train.py
      monitor.py
      compare.py
      predict.py
      postproc.py
      models.py
      jobs.py
      system.py
    services/
      images.py             # NIfTI / PNG slice decoding on demand
      tensorboard_proxy.py  # spawn `tensorboard --logdir` on sub-port
      cli_renderer.py       # form payload → equivalent nnUNetv2_* CLI string
    web/                    # built SPA assets (committed; shipped in wheel)
      index.html
      assets/

frontend/                   # Svelte source (not packaged; built into nnunetv2/gui/web/)
  package.json
  vite.config.ts
  tsconfig.json
  src/
    app.html
    routes/                 # Dashboard, Datasets, Train, Monitor, Compare, Predict, Models, Jobs, Settings
    lib/
      api.ts                # typed REST client (openapi-typescript output)
      sse.ts                # EventSource helpers
      stores/               # workspace, jobs, runs, settings, theme
      viewer/               # NiiVueViewer.svelte + Canvas2DViewer.svelte
      charts/               # LineChart.svelte (uPlot wrapper)
      forms/                # TrainForm, PredictForm, PreprocessForm
    components/             # Sidebar, WorkspaceSwitcher, JobBadge, Toast, Table
docs/
  gui.md                    # user-facing documentation page

nnunetv2/tests/gui/
  unit/                     # pure-Python unit tests
  api/                      # FastAPI TestClient contract tests
  e2e/                      # Playwright (Linux CI only)

frontend/src/**/*.test.ts   # Vitest

.github/workflows/gui.yml   # CI: Python tier 1+2, Node tier 3, Playwright tier 4
```

### Why one subprocess per job, not in-process workers

nnUNet training imports CUDA, owns the GPU, and supports DDP via `torchrun`-style multi-GPU. Running it inside the FastAPI process would (a) couple any GUI crash to training and (b) require us to re-implement DDP launching. Subprocesses also let the user copy the printed CLI-equivalent into a terminal — useful when they want to reproduce a run on a remote box.

## Data Model & Flows

### SQLite schema

Database lives at `$nnUNet_results/.nnunet_gui/state.db` in WAL mode. The FastAPI server is the only writer.

```sql
CREATE TABLE job (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  kind            TEXT NOT NULL,          -- preprocess | train | predict | find_best | ensemble | postproc | export
  args_json       TEXT NOT NULL,
  pid             INTEGER,
  pgid            INTEGER,
  status          TEXT NOT NULL,          -- queued | starting | running | completed | failed | killed
  started_at      TIMESTAMP,
  ended_at        TIMESTAMP,
  exit_code       INTEGER,
  log_path        TEXT,
  output_run_id   TEXT,                   -- FK-ish into run.id (a canonical key)
  created_by      TEXT,                   -- 'gui' (room for future agents)
  error_message   TEXT
);

CREATE TABLE run (
  id              TEXT PRIMARY KEY,       -- canonical key: <dataset>/<plans>__<trainer>__<config>/fold_<n>
  dataset_id      TEXT NOT NULL,
  plans_name      TEXT NOT NULL,
  trainer_name    TEXT NOT NULL,
  configuration   TEXT NOT NULL,
  fold            TEXT NOT NULL,          -- '0'..'4' or 'all'
  output_folder   TEXT NOT NULL,
  status          TEXT NOT NULL,          -- training | completed | failed | abandoned
  source          TEXT NOT NULL,          -- gui | cli | unknown
  created_at      TIMESTAMP,
  last_seen_at    TIMESTAMP,
  tags_json       TEXT,
  notes           TEXT
);

CREATE TABLE run_metric_cache (
  run_id          TEXT NOT NULL,
  step            INTEGER NOT NULL,
  key             TEXT NOT NULL,
  value           REAL NOT NULL,
  wall_time       REAL,
  PRIMARY KEY (run_id, key, step)
);
CREATE INDEX ix_run_metric_cache_run_key ON run_metric_cache(run_id, key);

CREATE TABLE dataset (
  id                  TEXT PRIMARY KEY,    -- 'Dataset027_ACDC'
  dataset_id_int      INTEGER,             -- 27
  name                TEXT,                -- 'ACDC'
  raw_path            TEXT,
  preprocessed_path   TEXT,
  last_scanned_at     TIMESTAMP,
  fingerprint_json    TEXT,
  case_count          INTEGER,
  modality_count      INTEGER
);

CREATE TABLE prediction_set (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_ids_json    TEXT NOT NULL,
  input_folder    TEXT,
  output_folder   TEXT,
  started_at      TIMESTAMP,
  ended_at        TIMESTAMP,
  status          TEXT NOT NULL,
  summary_json    TEXT
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);
```

### Run identity

A run is identified by `dataset_id + plans_name + trainer_name + configuration + fold`, which is exactly the directory key nnU-Net already uses. We do not invent UUIDs. Two GUI installations pointing at the same `nnUNet_results` agree on run identity automatically.

### Job lifecycle state machine

```
POST /jobs                                  reaper sees PID exit
  ─────────────▶ queued ─▶ starting ─▶ running ─┬─▶ completed   (exit 0)
                                                ├─▶ failed      (exit ≠ 0)
                                                └─▶ killed      (POST /jobs/{id}/stop:
                                                                  SIGTERM then SIGKILL after grace)
```

Every transition is persisted. On server boot, the reaper walks `job WHERE status IN (queued, starting, running)` and probes each PID. Alive → re-attach a reaper coroutine. Dead → mark `failed`, or `completed` if `checkpoint_final.pth` exists for trainings.

### Live metrics pipeline

```
disk:   fold_N/tensorboard/events.out.tfevents.*
                  │  watchfiles event → tb_tailer scheduled re-read
                  ▼
server: in-memory ring buffer per run id + insert into run_metric_cache
                  │
                  ▼
        FastAPI SSE  /sse/runs/{id}/metrics
                  │  one event per (key, step, value, wall_time)
                  ▼
browser: uPlot ring buffer ↔ reactive Svelte store
```

Image-sample logs (the periodic input | GT | prediction panels TB already writes) ride the same channel. Payload shape: `{kind:"image", tag, step, image_url}`; `image_url` is `/api/runs/{id}/images/{step}/{tag}` and the server decodes the TB-stored PNG on demand.

### Log streaming

Same shape, different source: `aiofiles` tails the run's `training_log_*.txt`, fans out new lines to all SSE subscribers on `/sse/runs/{id}/log`. The Jobs page subscribes to the spawning subprocess's combined `stdout/stderr` via `/sse/jobs/{id}/log`.

### Filesystem discovery

`watchfiles` watches the three configured root dirs. On every event, we debounce 500 ms, re-scan the affected subtree, and upsert into `run`/`dataset`/`prediction_set`. The browser subscribes to `/sse/system/events` to learn of new runs/datasets without polling.

## UI Pages

All pages share the **persistent header** (workspace dataset switcher · job count badge · GPU memory) and **sidebar** (Dashboard · Datasets · Train · Monitor · Compare · Predict · Models · Jobs · Settings).

### Dashboard

Landing page. 2×2 grid:
- **Active jobs** — names + per-job mini progress bars (epoch counter for training, case counter for inference).
- **Recent runs** — last 6 by `last_seen_at`, with final or best dice + age + status icon.
- **Datasets** — raw/preprocessed counts and most-recently-touched datasets.
- **System** — GPU memory bar, free disk on results/preprocessed, recent server-side errors banner.

### Datasets

Left list of all `nnUNet_raw/Dataset*` with status icons (`✓` preprocessed / `◯` raw only). Right pane shows the selected dataset's stats, action buttons (Train · Predict · Validate), and a tabbed detail panel:

- **Cases** — clickable list; the selected case opens NiiVue with the input + label overlay, slice scrubber, axis switch (axial/coronal/sagittal), overlay opacity slider, LUT picker.
- **Plans** — read-only JSON tree of `plans.json` with configuration tabs (2d / 3d_fullres / 3d_lowres / 3d_cascade_fullres) and computed values (patch size, batch size, network depth, pooling).
- **Fingerprint** — `dataset_fingerprint.json` rendered as readable tables (spacings, foreground intensity stats per modality).
- **Validation** — runs `verify_dataset_integrity`, surfaces errors with file-by-file detail.
- **Convert** — picker for source format (MSD / generic Old-nnUNet-v1) → form for target ID + name → executes the corresponding `nnUNetv2_convert_*` entry point.

### Train

Left pane: structured form. Fields, defaulted from the workspace dataset:

- Dataset · Configuration (chips, single-select) · Plans dropdown · Trainer dropdown (populated via reflection over `nnunetv2.training.nnUNetTrainer.variants`) · Folds (chips, multi-select → enqueues runs sequentially) · GPUs (numeric; DDP if >1) · Pretrained weights (path) · Flags (`--npz`, `--c`, `--val`, `--val_best`, `--disable_checkpointing`) · Device.

Beneath the form:

- A **GPU contention warning** appears when projected memory > free.
- "Preview CLI command" expands the equivalent `nnUNetv2_train …` line.
- "Launch" `POST`s to `/api/jobs/train`.

Right rail: queue & recent launches (live, via `/sse/jobs/events`), with the CLI equivalent of the topmost queued run displayed for copy-paste.

### Monitor

Top: run identity bar (dataset · plans · trainer · configuration · fold) plus status pill, epoch counter, ETA (from the last N epoch durations), age, fold-switcher dropdown, "Open in TensorBoard" (spawns `tensorboard --logdir …` on a sub-port and links), Stop button.

Tabs:
- **Curves** — grid of small uPlot charts: train_loss, val_loss, mean_fg_dice + ema, per-class dice, learning_rate, epoch_duration. Each chart streams via SSE. Pause/resume toggle.
- **Image samples** — strip of the most recent input | GT | prediction triplets emitted by the existing TB image-sample logger; click expands to full NiiVue.
- **Log** — live-tailing terminal-style view of `training_log_*.txt`.
- **Config & CLI** — read-only dump of trainer config + plans diff against defaults + the original CLI invocation.
- **Checkpoints** — list of `checkpoint_*.pth` files with sizes/timestamps; download links; "Validate from this checkpoint" action.

### Compare

Top: filter chips (datasets · configurations · trainers · plans · status), metric selector, x-axis selector (epoch vs wall-time), smoothing slider, export-CSV button.

Below: an overlay line chart and a sortable, filterable table of runs. Row-click toggles a run in the chart; double-click navigates to that run's Monitor page. Selected runs persist across navigation via the workspace store.

### Predict

Left pane: launch form (input folder · output folder · dataset · configuration · folds chips with `all` = ensemble · checkpoint final/best · step size · `--disable_tta` · `--save_probabilities` · `--c` · device). A sub-flow "+ Ensemble configs…" lets the user pick multiple configs to ensemble across (calls `nnUNetv2_ensemble` after individual predictions).

Right pane: per-case browser of an existing output folder. The viewer shows a 3-pane split (input | GT if present | prediction), with an overlay viewer below (opacity slider, contour toggle, LUT picker). Per-case metrics (Dice, HD95, volume) appear inline when GT is present.

### Postprocessing & Models

A combined Models page hosting:

- **Trained models** grouped dataset → config → trainer. Per-model actions: Export to zip (with weights-only mode), Share (copies a CLI command), Delete (staged via `.trash/`).
- **`find_best_configuration`** — pick configs → see recommended ensemble + postprocessing → "Generate inference_instructions.txt" + "Predict on a test folder →" deep-links to Predict pre-filled.
- **Ensemble** — pick prediction folders → launch `nnUNetv2_ensemble`.
- **Apply postprocessing** — pick predictions + a `postprocessing.pkl` → launch `nnUNetv2_apply_postprocessing`.
- **Import** — paste a URL or pick a zip → calls `nnUNetv2_download_pretrained_model_by_url` or `nnUNetv2_install_pretrained_model_from_zip`.

### Jobs

A table of every process the server has touched (running + recent). Columns: PID · kind · args-summary · status · started · CPU% · GPU MB · log lines · age. Row-click expands a panel with the full stdout/stderr live tail, full CLI args, Stop / Restart / Open-log-file actions. Filter chips by kind/status. The data backs the header job badge.

### Settings

- Env vars (`nnUNet_raw`, `nnUNet_preprocessed`, `nnUNet_results`, `nnUNet_tb_logdir`, `nnUNet_wandb_enabled`, `nnUNet_tb_image_every_n_epochs`, …) — edit + "restart server" prompt.
- Default device, theme (light/dark/system).
- GPU enumeration table.
- About: nnUNet version, GUI version, CUDA, torch version, **warning if PyTorch == 2.9.x** (per CLAUDE.md).
- "Open diag" → downloads `/api/system/diag` as JSON for bug reports.

## Dependencies, Packaging, Deploy

### Python (new optional extra `gui` in `pyproject.toml`)

```
fastapi >= 0.111
uvicorn[standard]
sse-starlette
watchfiles
aiofiles
psutil
pynvml                   # optional GPU mem/util; degrades gracefully when absent
tbparse                  # read TF event files without pulling tensorflow
sqlalchemy >= 2.0
pillow                   # decode TB-embedded PNG samples
nibabel                  # NIfTI header / spacing inspection server-side
```

`tensorboard` is already pulled by the existing TB logging feature. `SimpleITK` is already a transitive nnUNet dep, reused for 2D thumbnail rendering.

### Frontend (`frontend/package.json`, dev-only)

```
svelte ^5
vite ^5
typescript ^5
@niivue/niivue
uplot
bits-ui                      # headless primitives (button/dialog/table) for Svelte 5
lucide-svelte                # icons
zod                          # runtime schema validation on API responses
openapi-typescript           # codegen TS types from /openapi.json
```

### Build pipeline

`cd frontend && npm run build` writes static assets to `nnunetv2/gui/web/`. This directory is committed and shipped in the wheel, so end users do not need Node. A `make gui` target (or `hatch run gui:build`) wires both halves for contributors.

### Packaging additions

- `[project.optional-dependencies] gui = [...]`
- `[project.scripts] nnUNetv2_gui = "nnunetv2.gui.cli:main"`
- `[tool.setuptools.package-data]` includes `nnunetv2/gui/web/**`

### Dev workflow

- **Backend:** `uvicorn nnunetv2.gui.server:app --reload --port 8765` with `NNUNET_GUI_DEV=1` (enables CORS for `http://localhost:5173`).
- **Frontend:** `cd frontend && npm run dev` — Vite dev server proxies `/api/*` and `/sse/*` to the backend at 8765.
- **One-shot launch:** `nnUNetv2_gui --open` after `npm run build` opens the browser to `http://127.0.0.1:8765`.

### OS support

macOS + Linux are first-class. Windows is "best-effort": process-group semantics route through `CREATE_NEW_PROCESS_GROUP` instead of `setsid`, and the system-notification helper is no-op. Documented in `documentation/gui.md`.

## Error Handling, Security, Observability

### Error-handling philosophy

The training run is the asset; the GUI is disposable scaffolding. No GUI-side failure may corrupt or kill a training job.

1. **Server-side handlers are best-effort.** Every router catches `Exception`, logs with traceback, returns a typed error `{kind, message, retryable, details}`. The frontend renders a non-blocking toast; failed widgets show "couldn't load" with a Retry button.
2. **Tailers self-disable on repeat failure.** TB tailer, log tailer, fs watcher each run as supervised async tasks: on parse failure they log once, sleep 2 s, retry. After 5 consecutive failures they stop and surface a banner with a manual "restart tailer" action. Same pattern as the existing TensorBoard logger.
3. **Subprocesses inherit no GUI state.** A job is `Popen`'d with the exact CLI equivalent and a clean env (plus the required nnUNet vars). The job's contract is to write to disk; the GUI's contract is to read disk.

### Validation

- All form submissions go through Pydantic models server-side; the same shapes are codegen'd to TypeScript via `openapi-typescript`, so the form can pre-validate.
- Path inputs are normalized and bounded to live under `nnUNet_raw`/`nnUNet_preprocessed`/`nnUNet_results` or paths explicitly allowed via `--allow-path` at server start. Escape attempts return 400.
- Trainer-name dropdown is populated by reflection over `nnunetv2.training.nnUNetTrainer.variants` so users can't typo into a 30-minute crash.

### Security

- Default bind `127.0.0.1`, no auth.
- Server refuses to bind a non-loopback host unless `--token <hex>` is also passed; bearer-token middleware then enforces it on every HTTP request (REST and SSE).
- CORS off by default; `NNUNET_GUI_DEV=1` opens it to `http://localhost:5173` only.
- Settings → Edit env var is restricted to a whitelist matching documented nnUNet variables.
- "Delete this run" is staged via `<results>/.trash/` first; real deletion is a separate confirm action.

### Observability

- Structured logs (one JSON line per event) to `<results>/.nnunet_gui/server.log`, rotated daily. `--debug` flips to text format.
- `GET /api/system/healthz` and `GET /api/system/diag` (the latter dumps versions, env vars, GPU, disk, recent errors).
- Job stderr captured to the on-disk training log file *and* a separate `<job>.stderr` for the server's own subprocess wrapping. Both visible in the Jobs page.
- Frontend uncaught errors and Svelte error boundary catches → `POST /api/system/clienterror` → server log.

### No telemetry

Nothing leaves the machine. Stated explicitly in docs and About panel.

## Testing Strategy

Five tiers; nnUNet's "integration-first" tradition is preserved.

1. **Pure unit (Python) — `nnunetv2/tests/gui/unit/`.** SQLite migrations, TB event parser (hand-built fixtures), job state machine, path allowlist, env-var whitelist, CLI renderer. `pytest -m unit`. <1 s total.
2. **API contract — `nnunetv2/tests/gui/api/`.** FastAPI `TestClient` against the in-process app. Every router gets happy-path + one validation-failure case. Ephemeral SQLite (`:memory:`), `tmp_path`-rooted fake `nnUNet_results` with pre-made fold folders + event files committed as fixtures.
3. **Frontend unit — `frontend/src/**/*.test.ts`.** Vitest. Stores, API client retry/backoff, form-to-CLI renderer, chart ring buffer. Component tests only where there's logic. No DOM-snapshot tests.
4. **E2E smoke — `nnunetv2/tests/gui/e2e/`.** Playwright on Linux CI. One scripted user journey: boot server with fixture results dir → land on Dashboard → navigate Datasets/Compare/Monitor → assert live metric stream updates within 2 s for a fixture-backed "running" run → assert state transitions to completed. ~30 s.
5. **Live integration (extends `run_integration_test.sh`).** A new `--gui` flag launches the server in background, asserts via `curl` that a real Hippocampus training run appears in `/api/runs`, that the metric SSE stream emits, and the job page reports `completed` at the end. Opt-in (`workflow_dispatch`); needs GPU.

**Not tested.** Pixel-perfect UI snapshots; mock-heavy controller tests; NiiVue WebGL output; performance benchmarks (separate exercise).

**CI.** `.github/workflows/gui.yml` runs tiers 1–4 on every push (Python 3.10/3.11 × Linux). Tier 5 is opt-in. The existing `nnUNetv2` workflow is untouched.

## Phased Delivery

Each phase ends with a demoable artifact; you could stop after any phase and the GUI is still useful.

- **Phase 0 — Foundation.** Scaffold `nnunetv2/gui/` + `frontend/`. FastAPI `/system/healthz`, Svelte dev/build, SQLite schema, `nnUNetv2_gui` CLI, CI workflow with tiers 1–3. *Demo:* empty app, nav skeleton, placeholders.
- **Phase 1 — Read-only browse.** Filesystem discovery, Dataset list, Run list, Plans/Fingerprint viewer, Dashboard backed by historical data. *Demo:* navigate everything you've ever trained.
- **Phase 2 — Image viewer.** NiiVue, server-side slice streaming, dataset case browser, prediction-review viewer for runs already on disk. *Demo:* previewing any case in any dataset.
- **Phase 3 — Live monitoring (passive).** TB tailer → SSE, Monitor page, log tailing, Jobs page read-only, toast on job completion. *Demo:* launch trainings in the terminal and watch them live in the browser.
- **Phase 4 — Job launching.** Subprocess launcher with process groups, reaper, Preprocess/Train/Predict launchers, multi-fold queue, GPU warning, Stop/Restart. *Demo:* pure-GUI workflow end-to-end.
- **Phase 5 — Compare.** Multi-run aggregation, overlay chart with metric/x-axis/smoothing, sortable filterable table, CSV export.
- **Phase 6 — Inference polish + Models.** 3-pane prediction viewer + overlay, per-case metrics, `find_best_configuration`, ensembling, postprocessing, model export/import.
- **Phase 7 — Polish & system.** Settings, env-var management, theme, tags/notes, system notifications, e2e Playwright journey, Hippocampus integration with `--gui`, `documentation/gui.md`.

Sizing: Phases 0–2 small. Phase 3 medium (tailer infra is reused everywhere). Phase 4 largest (touches every CLI subcommand). Phases 5–6 medium. Phase 7 small but easy to under-scope.

No phase requires changes to nnUNet core training code. The only nnUNet-side change in v1 is a documentation page added in Phase 7.

## Open Questions / Future Work (out of v1 scope)

- Plans editor (write, not just read).
- Multi-machine job queue / remote agents.
- Authentication beyond bearer token (OAuth/OIDC) for multi-user deployments.
- Plugin API for third-party panels.
- Mobile/tablet responsive layout.
- DICOM as a first-class input format end-to-end.
- Cost/time prediction model trained on historical run data.
