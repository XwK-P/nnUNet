# nnU-Net GUI Manager

A browser-based experiment & dataset manager that wraps every `nnUNetv2_*` CLI command. Local-first, single-user, no auth by default. The GUI never replaces the CLI — it spawns CLI subprocesses, monitors them, and reflects everything on disk.

Status: **v1 complete** (Phases 0-7).

## Install

```bash
pip install "nnunetv2[gui]"
```

For contributors:

```bash
pip install -e ".[gui,gui-e2e]"
cd frontend && npm install && npm run build
```

To run the Playwright end-to-end test locally, also:

```bash
playwright install --with-deps chromium
```

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

- **Dashboard** — counts (datasets, preprocessed datasets, runs, completed runs), recent runs, disk usage per root, GPU memory.
- **Datasets** — every `Dataset*` under `$nnUNet_raw`. Per-dataset tabs: Cases (NiiVue viewer with per-axis slice / per-channel / window controls), Plans (`plans.json` inspector), Fingerprint (`dataset_fingerprint.json` inspector), Validation, Convert. A collapsible **Preprocess** panel previews the equivalent `nnUNetv2_plan_and_preprocess …` command before launch.
- **Train** — multi-fold queue with a GPU contention warning. The "Preview CLI" toggle expands the equivalent `nnUNetv2_train …` command. Folds are dispatched to N jobs and run serially under the launcher's slot manager.
- **Monitor** — live curves (`uPlot`), log tail, image samples (TB scalars + `add_image`), checkpoint list. SSE-multiplexed on `/sse/runs/{run_id}/events`. Closed/completed runs replay their full history; running ones append in near real time. The TB tailer self-disables after 5 consecutive failures and surfaces a Retry banner.
- **Compare** — pick N runs, overlay training curves with metric / x-axis / smoothing controls; sort and filter the run-summary table; export to CSV.
- **Predict** — launch form + 3-pane viewer (input · GT · prediction) with overlay opacity + sortable per-case Dice table.
- **Models** — per-Model fold/checkpoint list, **export to zip**, **import zip**, `find_best_configuration`, `nnUNetv2_ensemble` across configurations, `nnUNetv2_apply_postprocessing`.
- **Jobs** — every spawned process with per-row **Stop / Cancel / Restart**. Stop sends SIGTERM (5 s grace) then SIGKILL to the detached process group; cancel removes a queued job before launch; restart re-queues with the same args.
- **Settings** — environment-variable inspector (read-only allowlist), server log-level toggle, theme switcher (light / dark / system), Run **tags & notes** editor.

## Workflow

1. Set environment variables (`nnUNet_raw`, `nnUNet_preprocessed`, `nnUNet_results`).
2. Drop a dataset into `$nnUNet_raw` (or convert via the GUI's Convert tab).
3. Pick **Preprocess** on the dataset detail page.
4. Train: choose folds, configuration, trainer; click Launch.
5. Monitor: switch to Monitor and watch the curves stream.
6. Compare: tick the runs you care about; export CSV.
7. Predict: point at an input folder and an output folder; review the 3-pane viewer per case.
8. Post-process / find_best / ensemble: pick prediction folders, queue the job from the Models page.
9. Export: turn a Model into a zip; share or archive.

## Notifications

When a job reaches a terminal state (`completed` / `failed` / `killed` / `cancelled`), the browser fires a desktop notification. Permission is requested on first job completion. Notifications dedupe by job id, so refreshing a tab won't re-fire historical jobs. Disable in the browser's notification permission UI.

## Run tags & notes

In **Settings → Run tags & notes**, pick a run on the left and edit its `tags` (comma-separated list) and `notes` (free text) on the right. Both are persisted to the GUI SQLite database alongside the run row; they survive restarts and appear via `GET /api/runs/{id}`.

## Restart safety

Killing the GUI server never kills in-flight subprocesses. On the next launch, the launcher rediscovers each job by PID and resumes tailing logs / TB events. The Jobs page row stays on `running` across a server restart, and Monitor curves keep advancing once the SSE pipe reconnects.

## Security

The server binds to `127.0.0.1` and requires no authentication by default. Binding to a non-loopback host requires `--token <hex>`, which becomes the bearer token required on every `/api/*` and `/sse/*` request. `/api/system/healthz` stays open so external monitoring still works.

The browser presents the token in two ways:

- **fetch requests** carry `Authorization: Bearer <token>` (preferred).
- **`<img>` previews and SSE EventSource** can't attach custom headers, so the same token is accepted as `?token=<token>`. Treat HTTPS as a prerequisite for non-loopback deployments — query-string tokens appear in uvicorn / nginx access logs.

To hand the token to the SPA on first load, append it to the page URL:

```
https://your-host/?token=<your-token>
```

The SPA captures the value, stores it in `sessionStorage`, strips it from the URL bar so it doesn't linger in browser history, and injects it on every subsequent request for the tab. Closing the tab clears the token.

The GUI never sends data off your machine. No telemetry. No outgoing network requests.

## OS support

macOS and Linux are first-class. Windows is best-effort:
- Process-group semantics use `CREATE_NEW_PROCESS_GROUP` instead of `setsid`; SIGTERM/SIGKILL are mapped to `terminate()` / `kill()`.
- The system-notification helper is a no-op on browsers that block desktop notifications.

## Manual verification (Phase 4)

Before declaring Phase 4 fully done on a fresh box, run through the checklist below against a real `nnUNet_raw/Dataset004_Hippocampus` (or similar):

1. Datasets → Dataset004 → click **Preprocess** with default planner; confirm Jobs page shows a `running` row that transitions to `completed`.
2. After preprocess completes: Train tab → 3d_fullres + folds `[0, 1]` → **Launch 2 folds**; fold_0 runs while fold_1 sits `queued`, then fold_1 starts after fold_0 finishes.
3. On fold_1, hit **stop**; row turns `killed` within 6 s.
4. After fold_0 completes: Predict tab → fill input/output folders → **Launch**; prediction completes and the Predict route shows the per-case viewer.
5. Header active-job badge updates throughout.
6. `pkill -f uvicorn` while a training is running and re-launch `nnUNetv2_gui`:
   - the training subprocess is still alive in `ps`;
   - the Jobs page shows it as `running` after re-boot;
   - the Monitor curves resume tailing.

## Hippocampus integration

`bash nnunetv2/tests/integration_tests/run_integration_test.sh 4 --gui` runs the full Hippocampus pipeline with the GUI booted alongside it. The script:

1. Boots `nnUNetv2_gui --host 127.0.0.1 --port 8765` in the background and waits for `/api/system/healthz`.
2. Runs the normal training + best-config + inference pipeline.
3. Snapshots `/api/dashboard` to `/tmp/nnunet_gui_dashboard.json`, then kills the GUI process.

This is intended for ad-hoc verification on a machine with a GPU. No CI workflow runs it.

## Troubleshooting

- **Browser shows "Loading dashboard…" forever.** Check that the three env vars point at writable directories. Open `/api/system/diag` in a tab and inspect `paths`.
- **No runs show up.** Confirm `$nnUNet_results` contains `DatasetXXX_*/<plans>__<trainer>__<config>/fold_*` directories with at least one file.
- **Live monitor flickers.** The TB tailer self-disables after 5 consecutive failures and surfaces a banner with a Retry button.
- **A subprocess survived a server restart.** That's by design — the GUI re-attaches by PID on boot. Check the Jobs page; the row should flip from `unknown` to a terminal state once the subprocess exits.
- **`--gui` integration smoke complains the GUI never came up.** Check `/tmp/nnunet_gui.log`. Most often: env vars are unset, or port 8765 is already bound.

## Testing

The test pyramid lives at `nnunetv2/tests/gui/`:

| Tier | Path | What it covers |
|---|---|---|
| unit | `unit/` | State machines, repos, services, helpers — no FastAPI |
| api | `api/` | TestClient against the FastAPI app with synthetic fixtures |
| smoke | (`test_pure_gui_smoke.py`, `test_monitor_smoke.py`) | Real uvicorn in a thread for streams |
| e2e | `e2e/` | Playwright (Chromium) drives the built GUI against a synthetic dataset; only runs when `pytest-playwright` is installed |
| frontend | `frontend/` (vitest) | TS unit tests + a smoke render test |

The CI workflow at `.github/workflows/gui.yml` runs all four tiers on every push touching `nnunetv2/gui/**`, `nnunetv2/tests/gui/**`, `frontend/**`, or `pyproject.toml`.

## Roadmap

The full design lives at [docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md](../docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md). v1 ships in 8 phases:

0. **Foundation** ✓ — scaffold, CLI, healthz.
1. **Read-only browse** ✓ — filesystem discovery, dataset/run lists, plans/fingerprint inspector, dashboard cards.
2. **Image viewer** ✓ — NiiVue, case browser, prediction review.
3. **Live monitoring** ✓ — TB tailer, Monitor page, Jobs read-only.
4. **Job launching** ✓ — preprocess / train / predict + multi-fold queue + stop / cancel / restart.
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
