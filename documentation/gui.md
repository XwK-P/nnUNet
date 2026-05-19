# nnU-Net GUI Manager

A browser-based experiment & dataset manager that wraps every `nnUNetv2_*` CLI command.
Status: **Phase 5** — pure-GUI workflow end-to-end (browse, image viewer, live monitoring, job launching), plus multi-run **Compare** (overlay chart + sortable summary table + CSV export).

## Install

```bash
pip install "nnunetv2[gui]"
```

For development:

```bash
pip install -e ".[gui]"
cd frontend
npm install
npm run build
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

## What you can do today (after Phase 5)

- Browse every dataset in `$nnUNet_raw` from the **Datasets** page.
- Inspect any dataset's `plans.json` and `dataset_fingerprint.json`.
- **Preprocess** any dataset from a collapsible panel on the Datasets page; the panel previews the equivalent `nnUNetv2_plan_and_preprocess …` command before launch.
- Browse every training run in `$nnUNet_results` from the **Monitor** page.
- Use the **Workspace** switcher in the header to scope downstream pages to a single dataset.
- See aggregate stats and recent runs on the **Dashboard**.
- Watch a run live: SSE-streamed metric curves (uPlot), tailed training log, and TB image-sample panel. Closed/completed runs replay their full history; running ones append in near real time.
- **Launch trainings** from the **Train** tab — choose configuration, fold(s), trainer/plans, num_gpus, npz; multi-fold expands into N queued jobs that run serially.
- **Launch predictions** from the **Predict** tab — input/output folders, configuration, fold(s) including `all` for ensemble, checkpoint, step size, TTA / save-probabilities flags, device.
- Open the **Jobs** page for a list of all tracked jobs with per-row **stop / cancel / restart** actions. Stop sends SIGTERM (5 s grace) then SIGKILL to the detached process group. The header badge shows a live count of active jobs and links to the page.
- Restart-safe: killing the GUI server does not kill in-flight subprocesses. On the next launch, `attach_on_boot` rediscovers them by PID and resumes tailing.
- Pick any N runs from **Compare**, overlay their training curves with metric/x-axis/smoothing controls.
- Sort & filter the run-summary table; export to CSV for downstream analysis.

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

## Security

The server binds to `127.0.0.1` and requires no authentication by default. Binding to a non-loopback host requires `--token <hex>`, which becomes the bearer token required on every request.

The GUI never sends data off your machine.

## Roadmap

The full design lives at [docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md](../docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md). v1 ships in 7 phases:

0. **Foundation** ✓ — scaffold, CLI, healthz.
1. **Read-only browse** ✓ — filesystem discovery, dataset/run lists, plans/fingerprint inspector, dashboard cards backed by historical data.
2. **Image viewer** ✓ — NiiVue + PNG slice preview, case browser per dataset, prediction review per run.
3. **Live monitoring (passive)** ✓ — SSE multiplexed stream, live curves (uPlot), log tail, image samples panel, read-only Jobs page, header active-job badge.
4. **Job launching** ✓ — preprocess / train (multi-fold queue) / predict launched from the GUI; stop/cancel/restart actions in the Jobs page; GPU contention warning + CLI preview; restart-safe re-attach via PID probes on server boot.
5. **Compare** ✓ — multi-run overlay chart (uPlot, with metric/x-axis/smoothing controls) + sortable RunSummary table with CSV export.
6. **Inference polish + Models** — find_best_configuration, ensembling, export/import.
7. **Polish & system** — settings, notifications, e2e, integration test.
