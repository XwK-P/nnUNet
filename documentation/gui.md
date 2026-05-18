# nnU-Net GUI Manager

A browser-based experiment & dataset manager that wraps every `nnUNetv2_*` CLI command.
Status: **Phase 0** — scaffolding only. Subsequent phases add features.

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

## Security

The server binds to `127.0.0.1` and requires no authentication by default. Binding to a non-loopback host requires `--token <hex>`, which becomes the bearer token required on every request.

The GUI never sends data off your machine.

## Roadmap

The full design lives at [docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md](../docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md). v1 ships in 7 phases:

0. **Foundation** ✓ (this page) — scaffold, CLI, healthz.
1. **Read-only browse** — dataset/run lists, plans inspector.
2. **Image viewer** — NiiVue, case browser, prediction review.
3. **Live monitoring (passive)** — Monitor page, jobs read-only.
4. **Job launching** — preprocess/train/predict.
5. **Compare** — multi-run overlay + table.
6. **Inference polish + Models** — find_best_configuration, ensembling, export/import.
7. **Polish & system** — settings, notifications, e2e, integration test.
