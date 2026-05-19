# nnU-Net GUI Manager

A browser-based experiment & dataset manager that wraps every `nnUNetv2_*` CLI command.
Status: **Phase 4** — pure-GUI workflow end-to-end. Browse, image viewer, live monitoring, and job launching (preprocess / train (multi-fold queue) / predict) with stop/cancel/restart actions and a GPU contention warning.

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

## What you can do today (after Phase 4)

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
5. **Compare** — multi-run overlay + table.
6. **Inference polish + Models** — find_best_configuration, ensembling, export/import.
7. **Polish & system** — settings, notifications, e2e, integration test.
