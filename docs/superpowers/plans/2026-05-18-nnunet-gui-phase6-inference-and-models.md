# nnU-Net GUI — Phase 6 (Inference Polish + Models) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the inference story. The Predict route gets a 3-pane viewer (input | ground-truth | prediction with toggleable overlay) and a per-case metric table. A new **Models** page lists every trained run grouped by `dataset / plans__trainer__config`, with actions for `find_best_configuration`, ensemble across configs, apply postprocessing, model export to tarball, and import from tarball. All long-running operations re-use the **Phase 4 job lifecycle** — every "go" button enqueues a subprocess via `JobQueue.enqueue` exactly like train/predict already do.

**Architecture:**
- **Predict polish.** A new `PredictPaneViewer.svelte` composes three `NiiVueViewer.svelte` instances side-by-side (input · GT if present · prediction), plus an overlay strip below that toggles "prediction over input." A new `PerCaseMetricsTable.svelte` reads each run's `validation/summary.json` (already produced by training) and per-prediction metrics if a `summary.json` is written alongside an inference output folder.
- **Models discovery.** `state/models.py` groups runs by `(dataset, plans, trainer, configuration)` into a `Model` aggregate; per-Model fold enumeration + checkpoint listing is computed from disk.
- **find_best_configuration / ensemble / apply_postprocessing.** Each gets a POST endpoint in a dedicated router (`models.py` / `postproc.py`) that renders the equivalent CLI via new `cli_renderer` helpers, then calls `app.state.job_queue.enqueue(...)`. The same Phase 4 reaper/log-tailer powers them; the Jobs page surfaces them automatically (Phase 4 already lists all rows).
- **Model export/import.** Export creates a job that runs `nnUNetv2_export_model_to_zip` (already in `pyproject.toml`). Import accepts a zip path, runs `nnUNetv2_install_pretrained_model_from_zip` as a job. Both are subprocess jobs that observe the Phase 4 stop/restart contract.

The router additions are purely additive — no Phase 0-4 endpoint is modified. We extend `services/cli_renderer.py` with four new render functions and four new Pydantic request models, keeping the "single source of truth for argv" invariant.

**Tech Stack:** No new Python or npm dependencies. Re-uses `nibabel` (Phase 2) for prediction NIfTI reads, `pillow` for slice → PNG, and the existing `JobQueue` machinery.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "UI Pages" → "Predict" and "Postprocessing & Models". Architectural decisions (locked-in): ensembling, find_best_configuration, postprocessing, export, and import are **job-backed via the Phase 4 launcher** — they go through the same `JobQueue` and Stop/Cancel/Restart contract as train/predict.

**TDD discipline:** Every behavioral change starts with a failing test. One commit per task. CLI renderers are pure functions tested in isolation; routers tested via `TestClient` with `dry_run=true` so the test process never spawns a real `nnUNetv2_*` binary unless it owns a `sleep_helper` stub.

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/state/models.py` | `Model` aggregate Pydantic model + `list_models(cfg)`, `get_model(cfg, dataset_id, plans_name, trainer_name, configuration)`, `list_checkpoints(fold_dir)` |
| `nnunetv2/gui/services/cli_renderer.py` (mod) | Add `FindBestConfigRequest`, `EnsembleRequest`, `PostprocRequest`, `ExportModelRequest`, `ImportModelRequest` + matching `render_*` functions |
| `nnunetv2/gui/routers/models.py` | `GET /api/models`, `GET /api/models/{model_id:path}`, `POST /api/models/export`, `POST /api/models/import`, `POST /api/models/find_best`, `POST /api/models/ensemble` |
| `nnunetv2/gui/routers/postproc.py` | `POST /api/postproc/apply` — enqueue `nnUNetv2_apply_postprocessing` job |
| `nnunetv2/gui/routers/predict.py` (mod) | Add `GET /api/predict/per_case_metrics?prediction_folder=...` that reads a `summary.json` next to predictions (when present) |
| `nnunetv2/gui/server.py` (mod) | Include the three new routers |
| `nnunetv2/tests/gui/unit/test_models_state.py` | Discovery: group folds into Models, enumerate checkpoints |
| `nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py` | Pure-function tests for the four new renderers |
| `nnunetv2/tests/gui/api/test_models_api.py` | `/api/models` list + detail + export + import + find_best + ensemble (all dry-run + enqueue paths) |
| `nnunetv2/tests/gui/api/test_postproc_api.py` | `/api/postproc/apply` dry-run + enqueue |
| `nnunetv2/tests/gui/api/test_predict_metrics_api.py` | Per-case metrics endpoint contract |
| `nnunetv2/tests/gui/fixtures/builders.py` (mod) | Add `build_checkpoint(fold_dir, name)` + `build_inference_summary(out_dir, per_case=...)` helpers |
| `frontend/src/lib/types.ts` (mod) | `Model`, `ModelFold`, `Checkpoint`, `PerCaseMetric`, `FindBestConfigRequest`, `EnsembleRequest`, `PostprocRequest`, `ExportModelRequest`, `ImportModelRequest` |
| `frontend/src/lib/api.ts` (mod) | `getModels`, `getModel`, `getPerCaseMetrics`, `postExportModel`, `postImportModel`, `postFindBest`, `postEnsemble`, `postPostproc` |
| `frontend/src/lib/stores/models.ts` | Async store for `Model[]` |
| `frontend/src/components/ModelsList.svelte` | Grouped tree dataset → config → trainer with per-Model actions |
| `frontend/src/components/ModelExportDialog.svelte` | Output path + folds-chips + checkpoint picker, submit → enqueue |
| `frontend/src/components/ModelImportDialog.svelte` | Path-to-zip input, submit → enqueue |
| `frontend/src/components/FindBestConfigForm.svelte` | Dataset + configurations multi-select + plans + trainer + folds + `--disable_ensembling` |
| `frontend/src/components/EnsembleForm.svelte` | Multi-input-folder picker + output folder + `--save_npz` |
| `frontend/src/components/PostprocForm.svelte` | Input folder + output folder + `pp_pkl_file` path + plans/dataset JSON paths |
| `frontend/src/components/PredictPaneViewer.svelte` | 3-pane composition: input · GT · prediction, with toggleable overlay strip |
| `frontend/src/components/PerCaseMetricsTable.svelte` | Sortable per-case metrics (Dice / HD95 / volume) for a prediction folder |
| `frontend/src/routes/Models.svelte` (mod) | Replace stub with ModelsList + dialog overlays + FindBest/Ensemble/Postproc forms |
| `frontend/src/routes/Predict.svelte` (mod) | Add PredictPaneViewer + PerCaseMetricsTable to the existing Phase 4 PredictForm layout |
| `documentation/gui.md` (mod) | Refresh roadmap + "what you can do today" |

---

## Task 1: `state/models.py` — discover trained models on disk (TDD)

**Files:**
- Create: `nnunetv2/gui/state/models.py`
- Create: `nnunetv2/tests/gui/unit/test_models_state.py`
- Modify: `nnunetv2/tests/gui/fixtures/builders.py`

- [ ] **Step 1: Add `build_checkpoint` to builders**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_checkpoint(fold_dir: Path, name: str = "checkpoint_final.pth") -> Path:
    """Touch a checkpoint file with non-zero size so size reads work."""
    fold_dir.mkdir(parents=True, exist_ok=True)
    p = fold_dir / name
    p.write_bytes(b"\0" * 128)
    return p


def build_inference_summary(
    out_dir: Path,
    *,
    per_case: dict[str, float] | None = None,
    foreground_mean_dice: float | None = None,
) -> Path:
    """Write a summary.json alongside prediction outputs (mirrors validation/summary.json shape)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if foreground_mean_dice is not None:
        payload["foreground_mean"] = {"Dice": foreground_mean_dice}
    if per_case:
        payload["metric_per_case"] = [
            {"reference_file": cid, "metrics": {"1": {"Dice": d}}}
            for cid, d in per_case.items()
        ]
    p = out_dir / "summary.json"
    p.write_text(json.dumps(payload))
    return p
```

- [ ] **Step 2: Write failing tests**

`nnunetv2/tests/gui/unit/test_models_state.py`:
```python
from __future__ import annotations

from pathlib import Path

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.gui.state.models import (
    Model, ModelFold, Checkpoint, list_models, get_model, list_checkpoints,
)


def _cfg(populated_paths, monkeypatch) -> GuiConfig:
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)
    return cfg


def test_list_models_groups_runs_by_dataset_config(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    models = list_models(cfg)
    # populated_paths fixture builds 3d_fullres and 2d, both on Dataset027_ACDC
    ids = sorted(m.id for m in models)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres",
    ]


def test_model_enumerates_folds(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    build_run(populated_paths["results"], dataset_folder="Dataset027_ACDC",
              configuration="3d_fullres", fold="1", completed=True)
    build_run(populated_paths["results"], dataset_folder="Dataset027_ACDC",
              configuration="3d_fullres", fold="2", completed=False)

    cfg = _cfg(populated_paths, monkeypatch)
    m = get_model(cfg, "Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres")
    assert m is not None
    folds = {f.fold: f.status for f in m.folds}
    assert folds == {"0": "completed", "1": "completed", "2": "abandoned"}


def test_get_unknown_model_returns_none(populated_paths, monkeypatch):
    cfg = _cfg(populated_paths, monkeypatch)
    assert get_model(cfg, "Dataset999_X", "p", "t", "c") is None


def test_list_checkpoints_returns_sorted_with_size(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_checkpoint
    cfg = _cfg(populated_paths, monkeypatch)
    fold_dir = (
        Path(cfg.results) / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0"
    )
    # populated_paths already builds checkpoint_final.pth
    build_checkpoint(fold_dir, "checkpoint_best.pth")
    build_checkpoint(fold_dir, "checkpoint_latest.pth")

    out = list_checkpoints(fold_dir)
    names = [c.name for c in out]
    assert set(names) == {"checkpoint_final.pth", "checkpoint_best.pth", "checkpoint_latest.pth"}
    for c in out:
        assert c.size_bytes > 0


def test_list_checkpoints_missing_fold_returns_empty(tmp_path):
    assert list_checkpoints(tmp_path / "nope") == []
```

- [ ] **Step 3: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_models_state.py -v
```

- [ ] **Step 4: Implement `nnunetv2/gui/state/models.py`**

```python
"""Models = runs grouped by (dataset, plans, trainer, configuration)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.runs import RunFilter, list_runs


class Checkpoint(BaseModel):
    name: str
    path: str
    size_bytes: int


class ModelFold(BaseModel):
    fold: str
    output_folder: str
    status: str  # completed | abandoned | training | unknown
    checkpoints: list[Checkpoint]


class Model(BaseModel):
    id: str  # <dataset>/<plans>__<trainer>__<config>
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    folds: list[ModelFold]


def _model_id(dataset_id: str, plans_name: str, trainer_name: str, configuration: str) -> str:
    return f"{dataset_id}/{plans_name}__{trainer_name}__{configuration}"


def list_models(cfg: GuiConfig) -> list[Model]:
    """Group every discovered run by (dataset, plans, trainer, configuration)."""
    runs = list_runs(cfg, RunFilter())
    by_key: dict[str, list] = {}
    for r in runs:
        key = _model_id(r.dataset_id, r.plans_name, r.trainer_name, r.configuration)
        by_key.setdefault(key, []).append(r)
    out: list[Model] = []
    for key, group in sorted(by_key.items()):
        first = group[0]
        folds = [
            ModelFold(
                fold=r.fold,
                output_folder=r.output_folder,
                status=r.status,
                checkpoints=list_checkpoints(Path(r.output_folder)),
            )
            for r in sorted(group, key=lambda x: x.fold)
        ]
        out.append(Model(
            id=key,
            dataset_id=first.dataset_id,
            plans_name=first.plans_name,
            trainer_name=first.trainer_name,
            configuration=first.configuration,
            folds=folds,
        ))
    return out


def get_model(
    cfg: GuiConfig, dataset_id: str, plans_name: str, trainer_name: str, configuration: str,
) -> Optional[Model]:
    target = _model_id(dataset_id, plans_name, trainer_name, configuration)
    for m in list_models(cfg):
        if m.id == target:
            return m
    return None


def list_checkpoints(fold_dir: Path) -> list[Checkpoint]:
    if not fold_dir.is_dir():
        return []
    out: list[Checkpoint] = []
    for p in sorted(fold_dir.glob("checkpoint_*.pth")):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out.append(Checkpoint(name=p.name, path=str(p), size_bytes=size))
    return out
```

- [ ] **Step 5: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_models_state.py -v
git add nnunetv2/gui/state/models.py nnunetv2/tests/gui/unit/test_models_state.py \
        nnunetv2/tests/gui/fixtures/builders.py
git commit -m "gui(state): Model/ModelFold/Checkpoint aggregation grouped by dataset/config"
```

---

## Task 2: Extend `cli_renderer.py` with four new render functions (TDD)

**Files:**
- Modify: `nnunetv2/gui/services/cli_renderer.py`
- Create: `nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py`

- [ ] **Step 1: Failing tests**

`nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py`:
```python
from __future__ import annotations

from nnunetv2.gui.services.cli_renderer import (
    FindBestConfigRequest, EnsembleRequest, PostprocRequest,
    ExportModelRequest, ImportModelRequest,
    render_find_best, render_ensemble, render_postproc,
    render_export_model, render_import_model,
)


def test_find_best_minimal():
    req = FindBestConfigRequest(dataset_id=27)
    argv = render_find_best(req)
    assert argv[0] == "nnUNetv2_find_best_configuration"
    assert "27" in argv


def test_find_best_with_configs_and_disable_ensembling():
    req = FindBestConfigRequest(
        dataset_id=27, configurations=["2d", "3d_fullres"],
        plans=["nnUNetPlans"], trainers=["nnUNetTrainer"],
        folds=["0", "1", "2", "3", "4"], disable_ensembling=True,
    )
    argv = render_find_best(req)
    assert "-c" in argv and "2d" in argv and "3d_fullres" in argv
    assert "-p" in argv and "nnUNetPlans" in argv
    assert "-tr" in argv and "nnUNetTrainer" in argv
    assert "-f" in argv and argv.count("0") >= 1
    assert "--disable_ensembling" in argv


def test_ensemble_minimal():
    req = EnsembleRequest(input_folders=["/a", "/b"], output_folder="/out")
    argv = render_ensemble(req)
    assert argv[0] == "nnUNetv2_ensemble"
    i_idx = argv.index("-i")
    assert argv[i_idx + 1 : i_idx + 3] == ["/a", "/b"]
    assert "-o" in argv and "/out" in argv


def test_ensemble_save_npz():
    req = EnsembleRequest(input_folders=["/a"], output_folder="/out", save_npz=True)
    argv = render_ensemble(req)
    assert "--save_npz" in argv


def test_postproc_minimal():
    req = PostprocRequest(
        input_folder="/in", output_folder="/out",
        pp_pkl_file="/pp.pkl", plans_json="/plans.json", dataset_json="/dataset.json",
    )
    argv = render_postproc(req)
    assert argv[0] == "nnUNetv2_apply_postprocessing"
    assert argv[argv.index("-i") + 1] == "/in"
    assert argv[argv.index("-o") + 1] == "/out"
    assert argv[argv.index("-pp_pkl_file") + 1] == "/pp.pkl"
    assert argv[argv.index("-plans_json") + 1] == "/plans.json"
    assert argv[argv.index("-dataset_json") + 1] == "/dataset.json"


def test_export_model_minimal():
    req = ExportModelRequest(dataset_id=27, output_zip="/out.zip")
    argv = render_export_model(req)
    assert argv[0] == "nnUNetv2_export_model_to_zip"
    assert argv[argv.index("-d") + 1] == "27"
    assert argv[argv.index("-o") + 1] == "/out.zip"


def test_export_model_with_folds_configs_checkpoints():
    req = ExportModelRequest(
        dataset_id=27, output_zip="/out.zip",
        configurations=["3d_fullres", "2d"], folds=["0", "1"],
        trainer="nnUNetTrainer", plans="nnUNetPlans",
        checkpoints=["checkpoint_final.pth", "checkpoint_best.pth"],
    )
    argv = render_export_model(req)
    assert "-c" in argv and "3d_fullres" in argv and "2d" in argv
    assert "-tr" in argv and "nnUNetTrainer" in argv
    assert "-p" in argv and "nnUNetPlans" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1 : f_idx + 3] == ["0", "1"]
    chk_idx = argv.index("-chk")
    assert argv[chk_idx + 1 : chk_idx + 3] == ["checkpoint_final.pth", "checkpoint_best.pth"]


def test_import_model_minimal():
    req = ImportModelRequest(zip_path="/path/model.zip")
    argv = render_import_model(req)
    assert argv == ["nnUNetv2_install_pretrained_model_from_zip", "/path/model.zip"]
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py -v
```

- [ ] **Step 3: Append models + renderers to `cli_renderer.py`**

Append these after the Phase 4 functions:

```python
class FindBestConfigRequest(BaseModel):
    dataset_id: int
    plans: Optional[list[str]] = None
    configurations: Optional[list[str]] = None
    trainers: Optional[list[str]] = None
    folds: Optional[list[str]] = None
    disable_ensembling: bool = False
    no_overwrite: bool = False
    num_processes: Optional[int] = None


class EnsembleRequest(BaseModel):
    input_folders: list[str]
    output_folder: str
    save_npz: bool = False
    num_processes: Optional[int] = None


class PostprocRequest(BaseModel):
    input_folder: str
    output_folder: str
    pp_pkl_file: str
    plans_json: Optional[str] = None
    dataset_json: Optional[str] = None
    num_processes: Optional[int] = None


class ExportModelRequest(BaseModel):
    dataset_id: int
    output_zip: str
    configurations: Optional[list[str]] = None
    folds: Optional[list[str]] = None
    trainer: Optional[str] = None
    plans: Optional[str] = None
    checkpoints: Optional[list[str]] = None
    export_cv_preds: bool = False


class ImportModelRequest(BaseModel):
    zip_path: str


def render_find_best(req: FindBestConfigRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_find_best_configuration", str(req.dataset_id)]
    if req.plans:
        argv += ["-p", *req.plans]
    if req.configurations:
        argv += ["-c", *req.configurations]
    if req.trainers:
        argv += ["-tr", *req.trainers]
    if req.folds:
        argv += ["-f", *req.folds]
    if req.num_processes is not None:
        argv += ["-np", str(req.num_processes)]
    if req.disable_ensembling:
        argv.append("--disable_ensembling")
    if req.no_overwrite:
        argv.append("--no_overwrite")
    return argv


def render_ensemble(req: EnsembleRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_ensemble", "-i", *req.input_folders, "-o", req.output_folder]
    if req.num_processes is not None:
        argv += ["-np", str(req.num_processes)]
    if req.save_npz:
        argv.append("--save_npz")
    return argv


def render_postproc(req: PostprocRequest) -> list[str]:
    argv: list[str] = [
        "nnUNetv2_apply_postprocessing",
        "-i", req.input_folder,
        "-o", req.output_folder,
        "-pp_pkl_file", req.pp_pkl_file,
    ]
    if req.plans_json:
        argv += ["-plans_json", req.plans_json]
    if req.dataset_json:
        argv += ["-dataset_json", req.dataset_json]
    if req.num_processes is not None:
        argv += ["-np", str(req.num_processes)]
    return argv


def render_export_model(req: ExportModelRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_export_model_to_zip", "-d", str(req.dataset_id), "-o", req.output_zip]
    if req.configurations:
        argv += ["-c", *req.configurations]
    if req.trainer:
        argv += ["-tr", req.trainer]
    if req.plans:
        argv += ["-p", req.plans]
    if req.folds:
        argv += ["-f", *req.folds]
    if req.checkpoints:
        argv += ["-chk", *req.checkpoints]
    if req.export_cv_preds:
        argv.append("--exp_cv_preds")
    return argv


def render_import_model(req: ImportModelRequest) -> list[str]:
    return ["nnUNetv2_install_pretrained_model_from_zip", req.zip_path]
```

- [ ] **Step 4: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py -v
git add nnunetv2/gui/services/cli_renderer.py nnunetv2/tests/gui/unit/test_cli_renderer_phase6.py
git commit -m "gui(services): cli_renderer entries for find_best/ensemble/postproc/export/import"
```

---

## Task 3: `routers/models.py` — list + detail (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/models.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/api/test_models_api.py`

- [ ] **Step 1: Write failing tests (list + detail subset)**

`nnunetv2/tests/gui/api/test_models_api.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture
def models_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_models_groups_runs(models_client):
    r = models_client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    ids = sorted(m["id"] for m in body)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres",
    ]


def test_get_model_returns_folds(models_client):
    r = models_client.get(
        "/api/models/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dataset_id"] == "Dataset027_ACDC"
    assert body["configuration"] == "3d_fullres"
    assert len(body["folds"]) == 1
    assert body["folds"][0]["fold"] == "0"


def test_get_model_not_found(models_client):
    r = models_client.get("/api/models/Dataset999_X/p__t__c")
    assert r.status_code == 404
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
```

- [ ] **Step 3: Implement `nnunetv2/gui/routers/models.py` (list + detail only — actions land in later tasks)**

```python
"""Models router — list trained models + per-model actions."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.models import Model, list_models, get_model


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/models", tags=["models"])

    @router.get("", response_model=list[Model])
    def list_all(request: Request) -> list[Model]:
        return list_models(request.app.state.gui_config)

    @router.get("/{model_id:path}", response_model=Model)
    def get_one(model_id: str, request: Request) -> Model:
        cfg = request.app.state.gui_config
        # model_id format: <dataset>/<plans>__<trainer>__<config>
        try:
            dataset_id, rest = model_id.split("/", 1)
            plans, trainer, configuration = rest.split("__")
        except ValueError:
            raise HTTPException(status_code=400, detail="malformed model id")
        m = get_model(cfg, dataset_id, plans, trainer, configuration)
        if m is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
        return m

    return router
```

- [ ] **Step 4: Include router in `create_app`**

Add to `nnunetv2/gui/server.py`:

```python
from nnunetv2.gui.routers import models as models_router
# ...
    app.include_router(models_router.make_router())
```

- [ ] **Step 5: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
git add nnunetv2/gui/routers/models.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_models_api.py
git commit -m "gui(api): GET /api/models list + detail with fold/checkpoint enumeration"
```

---

## Task 4: Model export action — `POST /api/models/export` (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/models.py`
- Modify: `nnunetv2/tests/gui/api/test_models_api.py`

- [ ] **Step 1: Append failing tests**

```python
def test_export_dry_run(models_client):
    r = models_client.post("/api/models/export?dry_run=true",
                            json={"dataset_id": 27, "output_zip": "/tmp/model.zip",
                                  "configurations": ["3d_fullres"]})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_export_model_to_zip"
    assert body["argv"][argv_index(body['argv'], '-d') + 1] == "27"
    assert "job_id" not in body


def test_export_enqueues_job(models_client):
    r = models_client.post("/api/models/export",
                            json={"dataset_id": 27, "output_zip": "/tmp/model.zip"})
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_export_validation_error(models_client):
    r = models_client.post("/api/models/export", json={})
    assert r.status_code == 422
```

Add helper at the top of the test file:
```python
def argv_index(argv, needle):
    return argv.index(needle)
```

- [ ] **Step 2: Run; confirm fail**

- [ ] **Step 3: Append the export route to `models.py`**

```python
import os
from pathlib import Path

from fastapi import status

from nnunetv2.gui.services.cli_renderer import (
    ExportModelRequest, render_export_model, argv_to_cli_string,
)


    @router.post("/export", status_code=status.HTTP_201_CREATED)
    async def export(req: ExportModelRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_export_model(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs"
                       / f"export_d{req.dataset_id}.log")
        j = await q.enqueue(kind="export", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}
```

- [ ] **Step 4: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
git add nnunetv2/gui/routers/models.py nnunetv2/tests/gui/api/test_models_api.py
git commit -m "gui(api): POST /api/models/export — dry-run + enqueue (uses Phase 4 launcher)"
```

---

## Task 5: Model import action — `POST /api/models/import` (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/models.py`
- Modify: `nnunetv2/tests/gui/api/test_models_api.py`

- [ ] **Step 1: Append failing tests**

```python
def test_import_dry_run(models_client):
    r = models_client.post("/api/models/import?dry_run=true",
                            json={"zip_path": "/tmp/some_model.zip"})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"] == ["nnUNetv2_install_pretrained_model_from_zip", "/tmp/some_model.zip"]


def test_import_enqueue(models_client):
    r = models_client.post("/api/models/import",
                            json={"zip_path": "/tmp/some_model.zip"})
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_import_validation_error(models_client):
    r = models_client.post("/api/models/import", json={})
    assert r.status_code == 422
```

- [ ] **Step 2: Run; confirm fail**

- [ ] **Step 3: Append the import route**

```python
from nnunetv2.gui.services.cli_renderer import (
    ImportModelRequest, render_import_model,
)


    @router.post("/import", status_code=status.HTTP_201_CREATED)
    async def import_model(req: ImportModelRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_import_model(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / "import_model.log")
        j = await q.enqueue(kind="import", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}
```

- [ ] **Step 4: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
git add nnunetv2/gui/routers/models.py nnunetv2/tests/gui/api/test_models_api.py
git commit -m "gui(api): POST /api/models/import enqueue install-from-zip"
```

---

## Task 6: `routers/postproc.py` — `POST /api/postproc/apply` (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/postproc.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/api/test_postproc_api.py`

- [ ] **Step 1: Failing tests**

`nnunetv2/tests/gui/api/test_postproc_api.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture
def postproc_client(populated_paths, monkeypatch):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_postproc_dry_run(postproc_client):
    r = postproc_client.post("/api/postproc/apply?dry_run=true", json={
        "input_folder": "/preds",
        "output_folder": "/preds_pp",
        "pp_pkl_file": "/pp.pkl",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_apply_postprocessing"
    assert body["argv"][body["argv"].index("-i") + 1] == "/preds"
    assert body["argv"][body["argv"].index("-o") + 1] == "/preds_pp"


def test_postproc_enqueue(postproc_client):
    r = postproc_client.post("/api/postproc/apply", json={
        "input_folder": "/preds",
        "output_folder": "/preds_pp",
        "pp_pkl_file": "/pp.pkl",
    })
    assert r.status_code == 201
    assert "job_id" in r.json()


def test_postproc_validation_error(postproc_client):
    r = postproc_client.post("/api/postproc/apply", json={"input_folder": "/x"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run; confirm fail**

- [ ] **Step 3: Implement `nnunetv2/gui/routers/postproc.py`**

```python
"""POST /api/postproc/apply — enqueue nnUNetv2_apply_postprocessing."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nnunetv2.gui.services.cli_renderer import (
    PostprocRequest, render_postproc, argv_to_cli_string,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/postproc", tags=["postproc"])

    @router.post("/apply", status_code=status.HTTP_201_CREATED)
    async def apply(req: PostprocRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_postproc(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / "postproc.log")
        j = await q.enqueue(kind="postproc", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}

    return router
```

- [ ] **Step 4: Wire + pass + commit**

```python
# server.py
from nnunetv2.gui.routers import postproc as postproc_router
# ...
    app.include_router(postproc_router.make_router())
```

```bash
pytest nnunetv2/tests/gui/api/test_postproc_api.py -v
git add nnunetv2/gui/routers/postproc.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_postproc_api.py
git commit -m "gui(api): POST /api/postproc/apply enqueue nnUNetv2_apply_postprocessing"
```

---

## Task 7: `find_best_configuration` endpoint — `POST /api/models/find_best` (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/models.py`
- Modify: `nnunetv2/tests/gui/api/test_models_api.py`

- [ ] **Step 1: Append failing tests**

```python
def test_find_best_dry_run(models_client):
    r = models_client.post("/api/models/find_best?dry_run=true",
                            json={"dataset_id": 27, "configurations": ["3d_fullres", "2d"]})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_find_best_configuration"
    assert "27" in body["argv"]


def test_find_best_enqueue(models_client):
    r = models_client.post("/api/models/find_best",
                            json={"dataset_id": 27})
    assert r.status_code == 201
    assert "job_id" in r.json()
```

- [ ] **Step 2: Append the route**

```python
from nnunetv2.gui.services.cli_renderer import (
    FindBestConfigRequest, render_find_best,
)


    @router.post("/find_best", status_code=status.HTTP_201_CREATED)
    async def find_best(req: FindBestConfigRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_find_best(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs"
                       / f"find_best_d{req.dataset_id}.log")
        j = await q.enqueue(kind="find_best", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
git add nnunetv2/gui/routers/models.py nnunetv2/tests/gui/api/test_models_api.py
git commit -m "gui(api): POST /api/models/find_best enqueue nnUNetv2_find_best_configuration"
```

---

## Task 8: Ensembling endpoint — `POST /api/models/ensemble` (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/models.py`
- Modify: `nnunetv2/tests/gui/api/test_models_api.py`

- [ ] **Step 1: Append failing tests**

```python
def test_ensemble_dry_run(models_client):
    r = models_client.post("/api/models/ensemble?dry_run=true",
                            json={"input_folders": ["/a", "/b"], "output_folder": "/out"})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_ensemble"
    i_idx = body["argv"].index("-i")
    assert body["argv"][i_idx + 1 : i_idx + 3] == ["/a", "/b"]


def test_ensemble_enqueue(models_client):
    r = models_client.post("/api/models/ensemble",
                            json={"input_folders": ["/a", "/b"], "output_folder": "/out"})
    assert r.status_code == 201
    assert "job_id" in r.json()
```

- [ ] **Step 2: Append the route**

```python
from nnunetv2.gui.services.cli_renderer import (
    EnsembleRequest, render_ensemble,
)


    @router.post("/ensemble", status_code=status.HTTP_201_CREATED)
    async def ensemble(req: EnsembleRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_ensemble(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content={"argv": argv, "cli": cli})
        cfg = request.app.state.gui_config
        q = request.app.state.job_queue
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / "ensemble.log")
        j = await q.enqueue(kind="ensemble", argv=argv, env=os.environ.copy(),
                            log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_models_api.py -v
git add nnunetv2/gui/routers/models.py nnunetv2/tests/gui/api/test_models_api.py
git commit -m "gui(api): POST /api/models/ensemble enqueue nnUNetv2_ensemble"
```

---

## Task 9: Per-case metrics endpoint + Predict route polish (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/predict.py`
- Create: `nnunetv2/tests/gui/api/test_predict_metrics_api.py`

- [ ] **Step 1: Failing tests**

`nnunetv2/tests/gui/api/test_predict_metrics_api.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def metrics_client(populated_paths, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    from nnunetv2.tests.gui.fixtures.builders import build_inference_summary

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))

    pred_folder = tmp_path / "preds"
    pred_folder.mkdir()
    build_inference_summary(pred_folder,
                            per_case={"case_001": 0.92, "case_002": 0.83},
                            foreground_mean_dice=0.875)

    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None))), pred_folder


def test_per_case_metrics_returns_rows(metrics_client):
    client, pred_folder = metrics_client
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={pred_folder}")
    assert r.status_code == 200
    body = r.json()
    assert body["foreground_mean_dice"] == 0.875
    cases = {c["case_id"]: c["dice"] for c in body["cases"]}
    assert cases == {"case_001": 0.92, "case_002": 0.83}


def test_per_case_metrics_missing_summary(client, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = client.get(f"/api/predict/per_case_metrics?prediction_folder={empty}")
    assert r.status_code == 404


def test_per_case_metrics_path_must_exist(client):
    r = client.get("/api/predict/per_case_metrics?prediction_folder=/nope/nope")
    assert r.status_code == 404
```

- [ ] **Step 2: Run; confirm fail**

- [ ] **Step 3: Append the endpoint to `nnunetv2/gui/routers/predict.py`**

```python
import json

from fastapi import HTTPException


    @router.get("/per_case_metrics")
    def per_case_metrics(prediction_folder: str) -> dict:
        fp = Path(prediction_folder) / "summary.json"
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="no summary.json next to predictions")
        try:
            data = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=500, detail=f"failed to parse summary.json: {e}")
        fg = (data.get("foreground_mean") or {}).get("Dice")
        cases = []
        for entry in data.get("metric_per_case") or []:
            cid = entry.get("reference_file") or entry.get("case_id") or ""
            metrics = entry.get("metrics") or {}
            # Take the first non-background label's Dice
            dice = None
            for label, m in metrics.items():
                if label == "0":
                    continue
                if isinstance(m, dict) and "Dice" in m:
                    dice = float(m["Dice"]); break
            cases.append({"case_id": Path(cid).name, "dice": dice})
        return {"foreground_mean_dice": fg, "cases": cases}
```

- [ ] **Step 4: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_predict_metrics_api.py -v
git add nnunetv2/gui/routers/predict.py nnunetv2/tests/gui/api/test_predict_metrics_api.py \
        nnunetv2/tests/gui/fixtures/builders.py
git commit -m "gui(api): GET /api/predict/per_case_metrics reads inference summary.json"
```

---

## Task 10: Frontend types + API helpers

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/lib/types.ts`:

```ts
export interface Checkpoint {
  name: string;
  path: string;
  size_bytes: number;
}

export interface ModelFold {
  fold: string;
  output_folder: string;
  status: string;
  checkpoints: Checkpoint[];
}

export interface Model {
  id: string;
  dataset_id: string;
  plans_name: string;
  trainer_name: string;
  configuration: string;
  folds: ModelFold[];
}

export interface PerCaseMetric {
  case_id: string;
  dice: number | null;
}

export interface PerCaseMetricsResponse {
  foreground_mean_dice: number | null;
  cases: PerCaseMetric[];
}

export interface FindBestConfigRequest {
  dataset_id: number;
  plans?: string[];
  configurations?: string[];
  trainers?: string[];
  folds?: string[];
  disable_ensembling?: boolean;
  no_overwrite?: boolean;
  num_processes?: number;
}

export interface EnsembleRequest {
  input_folders: string[];
  output_folder: string;
  save_npz?: boolean;
  num_processes?: number;
}

export interface PostprocRequest {
  input_folder: string;
  output_folder: string;
  pp_pkl_file: string;
  plans_json?: string;
  dataset_json?: string;
  num_processes?: number;
}

export interface ExportModelRequest {
  dataset_id: number;
  output_zip: string;
  configurations?: string[];
  folds?: string[];
  trainer?: string;
  plans?: string;
  checkpoints?: string[];
  export_cv_preds?: boolean;
}

export interface ImportModelRequest {
  zip_path: string;
}
```

- [ ] **Step 2: Add endpoint helpers**

Append to the `endpoints` object in `frontend/src/lib/api.ts`:

```ts
import type {
  Model, PerCaseMetricsResponse,
  FindBestConfigRequest, EnsembleRequest, PostprocRequest,
  ExportModelRequest, ImportModelRequest,
} from './types';

  // inside endpoints:
  getModels: () => api.get<Model[]>('/api/models'),
  getModel: (id: string) => api.get<Model>(`/api/models/${id}`),
  getPerCaseMetrics: (predictionFolder: string) =>
    api.get<PerCaseMetricsResponse>(
      `/api/predict/per_case_metrics?prediction_folder=${encodeURIComponent(predictionFolder)}`),
  postExportModel: (req: ExportModelRequest) => api.post<{ job_id: number }>(
    '/api/models/export', req),
  postImportModel: (req: ImportModelRequest) => api.post<{ job_id: number }>(
    '/api/models/import', req),
  postFindBest: (req: FindBestConfigRequest) => api.post<{ job_id: number }>(
    '/api/models/find_best', req),
  postEnsemble: (req: EnsembleRequest) => api.post<{ job_id: number }>(
    '/api/models/ensemble', req),
  postPostproc: (req: PostprocRequest) => api.post<{ job_id: number }>(
    '/api/postproc/apply', req),
```

- [ ] **Step 3: svelte-check + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "gui(frontend): types + endpoint helpers for models/postproc/find_best/ensemble"
```

---

## Task 11: Frontend — `ModelsList.svelte` + dialogs + Models route

**Files:**
- Create: `frontend/src/lib/stores/models.ts`
- Create: `frontend/src/components/ModelsList.svelte`
- Create: `frontend/src/components/ModelExportDialog.svelte`
- Create: `frontend/src/components/ModelImportDialog.svelte`
- Create: `frontend/src/components/FindBestConfigForm.svelte`
- Create: `frontend/src/components/EnsembleForm.svelte`
- Create: `frontend/src/components/PostprocForm.svelte`
- Modify: `frontend/src/routes/Models.svelte`

- [ ] **Step 1: Models async store**

`frontend/src/lib/stores/models.ts`:
```ts
import { endpoints, ApiError } from '../api';
import type { Model } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Model[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createModelsStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();

  function emit() { for (const l of listeners) l(current); }

  return {
    get(): State { return current; },
    subscribe(l: Listener): () => void {
      listeners.add(l); l(current);
      return () => listeners.delete(l);
    },
    async load(): Promise<void> {
      current = { kind: 'loading' }; emit();
      try {
        const data = await endpoints.getModels();
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
```

- [ ] **Step 2: Implement `ModelsList.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createModelsStore } from '../lib/stores/models';
  import type { Model } from '../lib/types';

  let { onAction }: { onAction: (kind: string, model: Model) => void } = $props();

  const models = createModelsStore();
  let state = $state(models.get());

  onMount(() => {
    const unsub = models.subscribe((s) => (state = s));
    models.load();
    return unsub;
  });

  function mb(n: number): string {
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading models…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">{state.error.message}</p>
{:else if state.data.length === 0}
  <p class="text-sm text-slate-400">No trained models yet — train something first.</p>
{:else}
  <div class="space-y-3">
    {#each state.data as m}
      <div class="bg-bg-soft border border-border-soft rounded p-3">
        <div class="flex items-center gap-2 mb-2">
          <strong class="text-sm text-slate-100">{m.id}</strong>
          <span class="flex-1"></span>
          <button class="text-[11px] bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200 hover:bg-bg-soft"
                  onclick={() => onAction('export', m)}>Export</button>
        </div>
        <table class="text-xs w-full">
          <thead>
            <tr class="text-slate-500 border-b border-border-soft">
              <th class="text-left py-1">Fold</th>
              <th class="text-left py-1">Status</th>
              <th class="text-left py-1">Checkpoints</th>
            </tr>
          </thead>
          <tbody>
            {#each m.folds as f}
              <tr>
                <td class="py-1 text-slate-300">{f.fold}</td>
                <td class="py-1">
                  <span class:text-ok={f.status === 'completed'}
                        class:text-slate-500={f.status !== 'completed'}>{f.status}</span>
                </td>
                <td class="py-1 text-slate-400">
                  {#if f.checkpoints.length === 0}—{/if}
                  {#each f.checkpoints as c, i}
                    {i > 0}, {/each}{c.name} ({mb(c.size_bytes)})
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/each}
  </div>
{/if}
```

- [ ] **Step 3: Export & Import dialogs**

`frontend/src/components/ModelExportDialog.svelte`:
```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';
  import type { Model, ExportModelRequest } from '../lib/types';

  let { model, onClose }: { model: Model; onClose: () => void } = $props();

  let outputZip = $state('');
  let folds = $state<string[]>(model.folds.map((f) => f.fold));
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit() {
    if (!outputZip) { error = 'output zip required'; return; }
    busy = true; error = null;
    try {
      const req: ExportModelRequest = {
        dataset_id: Number(model.dataset_id.replace(/^Dataset/, '').split('_')[0]),
        output_zip: outputZip,
        configurations: [model.configuration],
        folds,
        trainer: model.trainer_name,
        plans: model.plans_name,
      };
      await endpoints.postExportModel(req);
      onClose();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="fixed inset-0 z-30 bg-black/60 flex items-center justify-center" onclick={onClose}>
  <div class="bg-bg-panel border border-border-soft rounded p-4 w-[480px]" onclick|stopPropagation>
    <h3 class="text-sm font-semibold text-slate-100 mb-3">Export {model.id}</h3>
    <label class="block text-xs text-slate-500 mb-1">Output zip path</label>
    <input class="w-full bg-bg-soft border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
           bind:value={outputZip} placeholder="/abs/path/model.zip" />
    <div class="mt-3">
      <span class="block text-xs text-slate-500 mb-1">Folds</span>
      <div class="flex gap-1 flex-wrap">
        {#each model.folds as f}
          <label class="text-[11px] flex items-center gap-1">
            <input type="checkbox" checked={folds.includes(f.fold)}
                   onchange={() => folds = folds.includes(f.fold) ? folds.filter((x) => x !== f.fold) : [...folds, f.fold]} />
            {f.fold}
          </label>
        {/each}
      </div>
    </div>
    {#if error}<p class="text-[11px] text-err mt-2">{error}</p>{/if}
    <div class="flex gap-2 mt-4 justify-end">
      <button class="text-xs text-slate-400 px-3 py-1" onclick={onClose}>Cancel</button>
      <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={submit}>
        {busy ? 'Queuing…' : 'Export'}
      </button>
    </div>
  </div>
</div>
```

`frontend/src/components/ModelImportDialog.svelte`:
```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';

  let { onClose }: { onClose: () => void } = $props();

  let zipPath = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit() {
    if (!zipPath) { error = 'zip path required'; return; }
    busy = true; error = null;
    try {
      await endpoints.postImportModel({ zip_path: zipPath });
      onClose();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="fixed inset-0 z-30 bg-black/60 flex items-center justify-center" onclick={onClose}>
  <div class="bg-bg-panel border border-border-soft rounded p-4 w-[480px]" onclick|stopPropagation>
    <h3 class="text-sm font-semibold text-slate-100 mb-3">Import model from zip</h3>
    <label class="block text-xs text-slate-500 mb-1">Local zip path</label>
    <input class="w-full bg-bg-soft border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
           bind:value={zipPath} placeholder="/abs/path/model.zip" />
    {#if error}<p class="text-[11px] text-err mt-2">{error}</p>{/if}
    <div class="flex gap-2 mt-4 justify-end">
      <button class="text-xs text-slate-400 px-3 py-1" onclick={onClose}>Cancel</button>
      <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={submit}>
        {busy ? 'Queuing…' : 'Import'}
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: FindBest / Ensemble / Postproc forms**

`frontend/src/components/FindBestConfigForm.svelte`:
```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';

  let datasetId = $state<number>(27);
  let configurations = $state<string>('2d 3d_fullres 3d_lowres');
  let disableEnsembling = $state(false);
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit() {
    busy = true; error = null; result = null;
    try {
      const res = await endpoints.postFindBest({
        dataset_id: datasetId,
        configurations: configurations.split(/\s+/).filter(Boolean),
        disable_ensembling: disableEnsembling,
      });
      result = `Job #${res.job_id} queued — see Jobs page`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">find_best_configuration</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center">Dataset ID</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
           type="number" bind:value={datasetId} />
    <label class="text-slate-500 self-center">Configurations</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
           bind:value={configurations} placeholder="2d 3d_fullres" />
    <span></span>
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={disableEnsembling} /> --disable_ensembling
    </label>
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={submit}>
      {busy ? 'Queuing…' : 'Run find_best_configuration'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
```

`frontend/src/components/EnsembleForm.svelte`:
```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';

  let inputs = $state<string>('');
  let output = $state<string>('');
  let saveNpz = $state(false);
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit() {
    busy = true; error = null; result = null;
    try {
      const res = await endpoints.postEnsemble({
        input_folders: inputs.split(/\s+/).filter(Boolean),
        output_folder: output,
        save_npz: saveNpz,
      });
      result = `Job #${res.job_id} queued`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally { busy = false; }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Ensemble prediction folders</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center">Input folders</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
           bind:value={inputs} placeholder="/preds_3d /preds_2d (space-separated)" />
    <label class="text-slate-500 self-center">Output folder</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
           bind:value={output} placeholder="/preds_ensemble" />
    <span></span>
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={saveNpz} /> --save_npz
    </label>
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={submit}>
      {busy ? 'Queuing…' : 'Run nnUNetv2_ensemble'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
```

`frontend/src/components/PostprocForm.svelte`:
```svelte
<script lang="ts">
  import { endpoints } from '../lib/api';

  let inputFolder = $state<string>('');
  let outputFolder = $state<string>('');
  let ppPkl = $state<string>('');
  let plansJson = $state<string>('');
  let datasetJson = $state<string>('');
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit() {
    busy = true; error = null; result = null;
    try {
      const res = await endpoints.postPostproc({
        input_folder: inputFolder,
        output_folder: outputFolder,
        pp_pkl_file: ppPkl,
        plans_json: plansJson || undefined,
        dataset_json: datasetJson || undefined,
      });
      result = `Job #${res.job_id} queued`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally { busy = false; }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Apply postprocessing</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center">Input folder</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200" bind:value={inputFolder} />
    <label class="text-slate-500 self-center">Output folder</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200" bind:value={outputFolder} />
    <label class="text-slate-500 self-center">pp.pkl</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200" bind:value={ppPkl} />
    <label class="text-slate-500 self-center">plans.json</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200" bind:value={plansJson} />
    <label class="text-slate-500 self-center">dataset.json</label>
    <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200" bind:value={datasetJson} />
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button class="text-xs bg-accent text-bg-base px-3 py-1 rounded" disabled={busy} onclick={submit}>
      {busy ? 'Queuing…' : 'Apply postprocessing'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
```

- [ ] **Step 5: Models route**

Replace `frontend/src/routes/Models.svelte`:

```svelte
<script lang="ts">
  import ModelsList from '../components/ModelsList.svelte';
  import ModelExportDialog from '../components/ModelExportDialog.svelte';
  import ModelImportDialog from '../components/ModelImportDialog.svelte';
  import FindBestConfigForm from '../components/FindBestConfigForm.svelte';
  import EnsembleForm from '../components/EnsembleForm.svelte';
  import PostprocForm from '../components/PostprocForm.svelte';
  import type { Model } from '../lib/types';

  let exportingModel = $state<Model | null>(null);
  let importing = $state(false);

  function handleAction(kind: string, m: Model) {
    if (kind === 'export') exportingModel = m;
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Models</h2>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4">
  <div class="min-w-0">
    <ModelsList onAction={handleAction} />
  </div>

  <div class="space-y-3">
    <div class="bg-bg-soft border border-border-soft rounded p-3">
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Tools</h4>
      <button class="text-[11px] bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200 hover:bg-bg-soft"
              onclick={() => importing = true}>Import zip…</button>
    </div>
    <FindBestConfigForm />
    <EnsembleForm />
    <PostprocForm />
  </div>
</div>

{#if exportingModel}
  <ModelExportDialog model={exportingModel} onClose={() => exportingModel = null} />
{/if}
{#if importing}
  <ModelImportDialog onClose={() => importing = false} />
{/if}
```

- [ ] **Step 6: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/lib/stores/models.ts frontend/src/components/ModelsList.svelte \
        frontend/src/components/ModelExportDialog.svelte frontend/src/components/ModelImportDialog.svelte \
        frontend/src/components/FindBestConfigForm.svelte frontend/src/components/EnsembleForm.svelte \
        frontend/src/components/PostprocForm.svelte frontend/src/routes/Models.svelte \
        nnunetv2/gui/web/
git commit -m "gui(frontend): Models page with grouped list + export/import dialogs + find_best/ensemble/postproc forms"
```

---

## Task 12: Predict route polish — 3-pane viewer + per-case table

**Files:**
- Create: `frontend/src/components/PredictPaneViewer.svelte`
- Create: `frontend/src/components/PerCaseMetricsTable.svelte`
- Modify: `frontend/src/routes/Predict.svelte`

- [ ] **Step 1: `PredictPaneViewer.svelte`**

```svelte
<script lang="ts">
  import NiiVueViewer from '../lib/viewer/NiiVueViewer.svelte';

  let { inputUrl, labelUrl, predictionUrl }:
    { inputUrl: string; labelUrl: string | null; predictionUrl: string | null } = $props();

  let overlay = $state(true);
  let opacity = $state(0.5);
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2 text-[11px]">
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={overlay} /> Overlay prediction
    </label>
    {#if overlay}
      <label class="text-slate-500">opacity</label>
      <input type="range" min="0" max="1" step="0.05" bind:value={opacity} />
      <span class="text-slate-400">{opacity.toFixed(2)}</span>
    {/if}
  </div>

  <div class="grid grid-cols-3 gap-2">
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Input</h5>
      <NiiVueViewer volumeUrl={inputUrl}
                    overlayUrl={overlay && predictionUrl ? predictionUrl : undefined}
                    overlayOpacity={opacity} />
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Ground truth</h5>
      {#if labelUrl}
        <NiiVueViewer volumeUrl={labelUrl} />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">no GT label for this case</p>
      {/if}
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Prediction</h5>
      {#if predictionUrl}
        <NiiVueViewer volumeUrl={predictionUrl} />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">no prediction available</p>
      {/if}
    </div>
  </div>
</div>
```

- [ ] **Step 2: `PerCaseMetricsTable.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints, ApiError } from '../lib/api';
  import type { PerCaseMetricsResponse, PerCaseMetric } from '../lib/types';

  let { predictionFolder }: { predictionFolder: string } = $props();

  let state = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: PerCaseMetricsResponse }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  $effect(() => {
    if (!predictionFolder) return;
    state = { kind: 'loading' };
    endpoints.getPerCaseMetrics(predictionFolder)
      .then((data) => state = { kind: 'loaded', data })
      .catch((e) => state = { kind: 'error', error: e });
  });

  type SortKey = 'case_id' | 'dice';
  let sortBy = $state<SortKey>('dice');
  let sortDir = $state<'asc' | 'desc'>('desc');

  function sorted(cases: PerCaseMetric[]): PerCaseMetric[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...cases].sort((a, b) => {
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
</script>

{#if state.kind === 'idle' || state.kind === 'loading'}
  <p class="text-xs text-slate-500">Loading per-case metrics…</p>
{:else if state.kind === 'error'}
  <p class="text-xs text-slate-500">
    {state.error instanceof ApiError && state.error.status === 404
      ? 'No summary.json next to predictions — likely no GT was available.'
      : `Failed to load: ${state.error.message}`}
  </p>
{:else}
  <div class="bg-bg-soft border border-border-soft rounded p-3">
    <div class="text-xs text-slate-300 mb-2">
      Mean Dice across cases:
      <span class="text-slate-100">{state.data.foreground_mean_dice?.toFixed(4) ?? '—'}</span>
    </div>
    <table class="w-full text-xs">
      <thead>
        <tr class="text-slate-500 border-b border-border-soft">
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('case_id')}>Case</th>
          <th class="text-right py-1 px-2 cursor-pointer" onclick={() => setSort('dice')}>Dice</th>
        </tr>
      </thead>
      <tbody>
        {#each sorted(state.data.cases) as c}
          <tr class="border-b border-border-soft">
            <td class="py-1 px-2 text-slate-300">{c.case_id}</td>
            <td class="py-1 px-2 text-right text-slate-200">{c.dice?.toFixed(4) ?? '—'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
```

- [ ] **Step 3: Wire into `Predict.svelte`**

Edit `frontend/src/routes/Predict.svelte`. After the Phase 4 PredictForm, append a "Review predictions" section:

```svelte
<script lang="ts">
  import PredictForm from '../lib/forms/PredictForm.svelte';
  import PredictPaneViewer from '../components/PredictPaneViewer.svelte';
  import PerCaseMetricsTable from '../components/PerCaseMetricsTable.svelte';

  let predictionFolder = $state<string>('');
  let inputUrl = $state<string>('');
  let labelUrl = $state<string | null>(null);
  let predictionUrl = $state<string | null>(null);
</script>

<h2 class="text-lg font-semibold text-slate-100">Predict</h2>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-4">
  <PredictForm />

  <div class="space-y-3">
    <div class="bg-bg-soft border border-border-soft rounded p-3">
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Review predictions</h4>
      <label class="block text-xs text-slate-500 mb-1">Prediction folder</label>
      <input class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
             bind:value={predictionFolder} placeholder="/abs/path/predictions" />
    </div>

    {#if inputUrl}
      <PredictPaneViewer {inputUrl} {labelUrl} {predictionUrl} />
    {/if}
    {#if predictionFolder}
      <PerCaseMetricsTable {predictionFolder} />
    {/if}
  </div>
</div>
```

(`inputUrl` / `labelUrl` / `predictionUrl` wiring to specific cases is a follow-up tweak — the form input here is the minimal hook that lets a user paste a folder and immediately see per-case metrics. Per-case selection that flips the three URLs sits on top of the Phase 2 `CasesList` for the same dataset.)

- [ ] **Step 4: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/components/PredictPaneViewer.svelte frontend/src/components/PerCaseMetricsTable.svelte \
        frontend/src/routes/Predict.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Predict 3-pane viewer + per-case metrics table"
```

---

## Task 13: End-to-end smoke + docs refresh

**Files:**
- Modify: `documentation/gui.md`

- [ ] **Step 1: Full test pyramid**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && cd ..
```
All green.

- [ ] **Step 2: Live smoke — dry-run each new endpoint**

```bash
NNUNET_RAW=$(mktemp -d) NNUNET_PRE=$(mktemp -d) NNUNET_RES=$(mktemp -d)
python -c "
from pathlib import Path
import os
from nnunetv2.tests.gui.fixtures.builders import (
    build_dataset_raw, build_dataset_preprocessed, build_run,
)
raw = Path(os.environ['NNUNET_RAW']); pre = Path(os.environ['NNUNET_PRE']); res = Path(os.environ['NNUNET_RES'])
build_dataset_raw(raw, dataset_id=27, name='ACDC')
build_dataset_preprocessed(pre, dataset_folder='Dataset027_ACDC')
build_run(res, dataset_folder='Dataset027_ACDC', configuration='3d_fullres', fold='0')
"
nnUNet_raw=$NNUNET_RAW nnUNet_preprocessed=$NNUNET_PRE nnUNet_results=$NNUNET_RES nnUNetv2_gui --port 8765 &
PID=$!; sleep 2
curl -s http://127.0.0.1:8765/api/models | head -c 400; echo
curl -s -X POST 'http://127.0.0.1:8765/api/models/find_best?dry_run=true' \
     -H 'content-type: application/json' \
     -d '{"dataset_id": 27, "configurations": ["3d_fullres"]}' | head -c 400; echo
curl -s -X POST 'http://127.0.0.1:8765/api/postproc/apply?dry_run=true' \
     -H 'content-type: application/json' \
     -d '{"input_folder":"/in","output_folder":"/out","pp_pkl_file":"/pp.pkl"}' | head -c 400; echo
kill $PID
```

Expected: models list shows the one trained run; dry-run responses include the right `argv` head.

- [ ] **Step 3: Update `documentation/gui.md`**

Replace the Phase 6 line with `6. **Inference polish + Models** ✓ — 3-pane viewer, per-case metrics, find_best, ensembling, postprocessing, export/import.` and extend "What you can do today":

```markdown
- Browse and act on **Models**: export per-fold to zip, import from zip, queue `find_best_configuration` / `nnUNetv2_ensemble` / `nnUNetv2_apply_postprocessing` jobs from the UI.
- Review predictions in a 3-pane viewer (input · GT · prediction) with overlay opacity, and inspect a sortable per-case Dice table.
```

- [ ] **Step 4: Commit**

```bash
git add documentation/gui.md
git commit -m "gui(docs): refresh Phase 6 entry + 'what you can do today'"
```

---

## Done condition

Phase 6 is complete when:

- [ ] `pytest nnunetv2/tests/gui/` is fully green.
- [ ] `npm test` + `svelte-check` are fully green.
- [ ] `/api/models` lists every trained model grouped by `(dataset, plans, trainer, configuration)`; per-model fold list includes checkpoint files with non-zero sizes.
- [ ] `/api/models/export`, `/api/models/import`, `/api/models/find_best`, `/api/models/ensemble`, `/api/postproc/apply` all support `dry_run=true` for argv preview and `dry_run=false` to enqueue a job via the Phase 4 `JobQueue`.
- [ ] `/api/predict/per_case_metrics?prediction_folder=...` returns per-case Dice when a `summary.json` exists.
- [ ] Browser: Models page shows the grouped list with Export dialog; Find best / Ensemble / Postproc forms queue jobs and show "Job #N queued" feedback. Predict route shows 3-pane viewer + per-case metrics table.
- [ ] All new long-running jobs appear in the Jobs page with working Stop/Cancel/Restart actions (Phase 4 behavior reused unchanged).
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 6 completion.
