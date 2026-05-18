# nnU-Net GUI — Phase 1 (Read-only Browse) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the read-only browse layer of the GUI — filesystem discovery, REST endpoints for datasets / runs / dashboard, and the Svelte UI to surface them — so a user can navigate everything they've ever trained without launching anything.

**Architecture:** A new `nnunetv2.gui.state` package (`datasets`, `runs`, `discovery`) extends the SQLite schema with `dataset` and `run` tables, scans `nnUNet_{raw,preprocessed,results}` at startup, and upserts canonical records. Three new FastAPI routers (`datasets`, `runs`, `dashboard`) expose them. The Svelte SPA replaces its Phase 0 placeholders on `/`, `/datasets`, and `/monitor` with real data, plus a workspace dropdown populated from `/api/datasets`.

**Tech Stack:** Same as Phase 0. No new dependencies — uses `nibabel`, `sqlalchemy`, `fastapi` (already in `[gui]` extra) and the existing Svelte/Tailwind/uPlot frontend.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md`. The "Data Model & Flows" → "SQLite schema" and "Run identity" sections, and the "UI Pages" → "Dashboard" / "Datasets" sections govern this phase.

**TDD discipline:** Every behavioral change starts with a failing test. Continues the Phase 0 pattern of one commit per task, with follow-up commits if the review surfaces issues.

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/db.py` (mod) | Add `dataset` + `run` SQLAlchemy `Table`s to the shared `_metadata` so `init_db` creates them. |
| `nnunetv2/gui/state/__init__.py` | Package marker |
| `nnunetv2/gui/state/datasets.py` | `Dataset` Pydantic model + repository functions (`list_all`, `get`, `upsert`, `mark_preprocessed`) |
| `nnunetv2/gui/state/runs.py` | `Run` Pydantic model + repository (`list`, `get`, `upsert`, status inference from on-disk files) + canonical-key helper |
| `nnunetv2/gui/state/discovery.py` | Filesystem scanners: `scan_raw_datasets`, `scan_preprocessed`, `scan_results_runs`, `reconcile(cfg)` orchestrator |
| `nnunetv2/gui/routers/datasets.py` | `GET /api/datasets`, `/api/datasets/{id}`, `/api/datasets/{id}/plans`, `/api/datasets/{id}/fingerprint` |
| `nnunetv2/gui/routers/runs.py` | `GET /api/runs` (with `dataset_id`, `configuration`, `trainer`, `fold`, `status` filters); `GET /api/runs/{id}` |
| `nnunetv2/gui/routers/dashboard.py` | `GET /api/dashboard` — aggregated stats for the 2×2 dashboard grid |
| `nnunetv2/gui/server.py` (mod) | Include new routers; call `reconcile(cfg)` once during `create_app` |
| `nnunetv2/tests/gui/fixtures/__init__.py` | Package marker |
| `nnunetv2/tests/gui/fixtures/builders.py` | `build_minimal_raw(root)`, `build_minimal_results(root)`, etc. — assemble fake nnUNet trees for tests |
| `nnunetv2/tests/gui/conftest.py` (mod) | Add `populated_paths` fixture that calls the builders on top of `gui_paths` |
| `nnunetv2/tests/gui/unit/test_discovery.py` | Scanner tests against fixture trees |
| `nnunetv2/tests/gui/unit/test_datasets_repo.py` | Dataset repo CRUD round-trips |
| `nnunetv2/tests/gui/unit/test_runs_repo.py` | Run repo CRUD + filter tests |
| `nnunetv2/tests/gui/api/test_datasets_api.py` | Dataset router contract tests |
| `nnunetv2/tests/gui/api/test_runs_api.py` | Runs router contract tests |
| `nnunetv2/tests/gui/api/test_dashboard_api.py` | Dashboard router contract tests |
| `frontend/src/lib/types.ts` | TypeScript types mirroring the Pydantic response models |
| `frontend/src/lib/api.ts` (mod) | Add typed endpoints `getDatasets`, `getDataset`, `getDatasetPlans`, `getDatasetFingerprint`, `getRuns`, `getRun`, `getDashboard` |
| `frontend/src/lib/stores/datasets.ts` | Async store of `Dataset[]` with `load()` |
| `frontend/src/lib/stores/runs.ts` | Async store of `Run[]` with `load(filters)` |
| `frontend/src/lib/stores/dashboard.ts` | Async store of `DashboardData` with `load()` |
| `frontend/src/components/WorkspaceSwitcher.svelte` | Header dropdown listing datasets, syncing with workspace store |
| `frontend/src/components/WorkspaceHeader.svelte` (mod) | Replace placeholder pill with real `<WorkspaceSwitcher/>` |
| `frontend/src/components/DashboardCards.svelte` | 2×2 grid: active jobs (placeholder), recent runs, datasets, system |
| `frontend/src/components/DatasetList.svelte` | Left rail listing datasets with status icons |
| `frontend/src/components/PlansViewer.svelte` | Read-only collapsible JSON tree for `plans.json` |
| `frontend/src/components/FingerprintViewer.svelte` | Readable tables of spacings + intensity stats from `fingerprint.json` |
| `frontend/src/components/DatasetDetail.svelte` | Right pane: stats + action buttons + tabbed detail (Cases / Plans / Fingerprint / Validation) — only Plans + Fingerprint tabs are wired in Phase 1; Cases + Validation are explicit "Phase 2"/"Phase 1+" placeholders |
| `frontend/src/components/RunsTable.svelte` | Sortable table of runs (no live updates) |
| `frontend/src/routes/Dashboard.svelte` (mod) | Replace stub with `<DashboardCards/>` |
| `frontend/src/routes/Datasets.svelte` (mod) | Replace stub with `<DatasetList/>` + `<DatasetDetail/>` split layout |
| `frontend/src/routes/Monitor.svelte` (mod) | Replace stub with `<RunsTable/>` + Phase-3 banner |
| `frontend/src/lib/api.test.ts` (mod) | Add 3 tests covering the new endpoints' success + 5xx handling |
| `frontend/src/lib/stores/datasets.test.ts` | Async store test |
| `frontend/src/lib/stores/runs.test.ts` | Async store test |

---

## Task 1: Extend SQLite schema with `dataset` and `run` tables (TDD)

**Files:**
- Modify: `nnunetv2/gui/db.py`
- Create: `nnunetv2/tests/gui/unit/test_schema_phase1.py`

- [ ] **Step 1: Write failing tests**

```python
# nnunetv2/tests/gui/unit/test_schema_phase1.py
from __future__ import annotations

import sqlite3

from nnunetv2.gui.db import init_db


def test_init_db_creates_dataset_table(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    cols = {r[1] for r in raw.execute("PRAGMA table_info('dataset')")}
    raw.close()
    assert {"id", "dataset_id_int", "name", "raw_path", "preprocessed_path",
            "last_scanned_at", "fingerprint_json", "case_count", "modality_count"} <= cols


def test_init_db_creates_run_table(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    cols = {r[1] for r in raw.execute("PRAGMA table_info('run')")}
    raw.close()
    assert {"id", "dataset_id", "plans_name", "trainer_name", "configuration",
            "fold", "output_folder", "status", "source", "created_at",
            "last_seen_at", "tags_json", "notes"} <= cols


def test_run_table_indexed_on_dataset_id(gui_config):
    init_db(gui_config)
    raw = sqlite3.connect(gui_config.state_db)
    indexes = {r[1] for r in raw.execute("PRAGMA index_list('run')")}
    raw.close()
    assert any("dataset_id" in i for i in indexes)
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_schema_phase1.py -v`
Expected: 3 failures — tables don't exist.

- [ ] **Step 3: Add tables to `nnunetv2/gui/db.py`**

Add these new imports if missing: `from sqlalchemy import Integer, DateTime, Index`. After the existing `settings_table` definition, add:

```python
dataset_table = Table(
    "dataset",
    _metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id_int", Integer, nullable=True),
    Column("name", String, nullable=True),
    Column("raw_path", String, nullable=True),
    Column("preprocessed_path", String, nullable=True),
    Column("last_scanned_at", DateTime, nullable=True),
    Column("fingerprint_json", String, nullable=True),
    Column("case_count", Integer, nullable=True),
    Column("modality_count", Integer, nullable=True),
)


run_table = Table(
    "run",
    _metadata,
    Column("id", String, primary_key=True),
    Column("dataset_id", String, nullable=False),
    Column("plans_name", String, nullable=False),
    Column("trainer_name", String, nullable=False),
    Column("configuration", String, nullable=False),
    Column("fold", String, nullable=False),
    Column("output_folder", String, nullable=False),
    Column("status", String, nullable=False),
    Column("source", String, nullable=False),
    Column("created_at", DateTime, nullable=True),
    Column("last_seen_at", DateTime, nullable=True),
    Column("tags_json", String, nullable=True),
    Column("notes", String, nullable=True),
    Index("ix_run_dataset_id", "dataset_id"),
)
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_schema_phase1.py -v`
Expected: 3 passes.

Also run all gui tests to confirm no regression: `pytest nnunetv2/tests/gui/ -v` → all green (was 26, now 29).

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/db.py nnunetv2/tests/gui/unit/test_schema_phase1.py
git commit -m "gui(db): add dataset + run tables for Phase 1 read-only browse"
```

---

## Task 2: Test-fixture builders for fake nnUNet trees

**Files:**
- Create: `nnunetv2/tests/gui/fixtures/__init__.py` (empty)
- Create: `nnunetv2/tests/gui/fixtures/builders.py`
- Modify: `nnunetv2/tests/gui/conftest.py`

- [ ] **Step 1: Create the builder module**

`nnunetv2/tests/gui/fixtures/__init__.py`:
```python
```

`nnunetv2/tests/gui/fixtures/builders.py`:
```python
"""Build minimal fake nnUNet directory trees for tests.

Each builder writes a small but valid-shape tree under the given root and
returns the canonical ids it created, so tests can assert against them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def build_dataset_raw(
    raw_root: Path,
    *,
    dataset_id: int,
    name: str,
    case_ids: Iterable[str] = ("case_001", "case_002", "case_003"),
    channels: dict[str, str] | None = None,
    file_ending: str = ".nii.gz",
) -> str:
    """Create a Dataset<XXX>_<Name> directory under raw_root.

    Returns the dataset folder name (e.g. 'Dataset027_ACDC').
    """
    channels = channels or {"0": "CT"}
    folder = f"Dataset{dataset_id:03d}_{name}"
    base = raw_root / folder
    (base / "imagesTr").mkdir(parents=True)
    (base / "labelsTr").mkdir()
    for cid in case_ids:
        for chan_idx in sorted(int(c) for c in channels):
            (base / "imagesTr" / f"{cid}_{chan_idx:04d}{file_ending}").touch()
        (base / "labelsTr" / f"{cid}{file_ending}").touch()
    dataset_json = {
        "channel_names": channels,
        "labels": {"background": 0, "foreground": 1},
        "numTraining": len(list(case_ids)) if not hasattr(case_ids, "__len__") else len(case_ids),
        "file_ending": file_ending,
    }
    (base / "dataset.json").write_text(json.dumps(dataset_json))
    return folder


def build_dataset_preprocessed(
    preprocessed_root: Path,
    *,
    dataset_folder: str,
    fingerprint: dict | None = None,
) -> Path:
    """Mark a dataset as preprocessed by creating its directory + fingerprint."""
    base = preprocessed_root / dataset_folder
    base.mkdir(parents=True, exist_ok=True)
    fp = fingerprint or {
        "spacings": [[1.0, 1.0, 1.0]],
        "foreground_intensity_properties_per_channel": {"0": {"mean": 100.0, "std": 50.0}},
    }
    (base / "dataset_fingerprint.json").write_text(json.dumps(fp))
    return base


def build_run(
    results_root: Path,
    *,
    dataset_folder: str,
    plans_name: str = "nnUNetPlans",
    trainer_name: str = "nnUNetTrainer",
    configuration: str = "3d_fullres",
    fold: str = "0",
    completed: bool = True,
    plans: dict | None = None,
    dataset_json: dict | None = None,
) -> tuple[Path, str]:
    """Create a fold directory with the standard nnUNet output files.

    Returns (fold_path, canonical_run_id).
    """
    base = results_root / dataset_folder / f"{plans_name}__{trainer_name}__{configuration}"
    fold_dir = base / f"fold_{fold}"
    fold_dir.mkdir(parents=True, exist_ok=True)
    (base / "plans.json").write_text(json.dumps(plans or {"plans_name": plans_name, "configurations": {configuration: {}}}))
    (base / "dataset.json").write_text(json.dumps(dataset_json or {"channel_names": {"0": "CT"}, "labels": {"background": 0, "foreground": 1}}))
    if completed:
        (fold_dir / "checkpoint_final.pth").write_bytes(b"")
        (fold_dir / "validation").mkdir(exist_ok=True)
        (fold_dir / "validation" / "summary.json").write_text(json.dumps({"foreground_mean": {"Dice": 0.9}}))
    canonical_id = f"{dataset_folder}/{plans_name}__{trainer_name}__{configuration}/fold_{fold}"
    return fold_dir, canonical_id
```

- [ ] **Step 2: Add `populated_paths` fixture to conftest**

Append to `nnunetv2/tests/gui/conftest.py`:

```python


@pytest.fixture
def populated_paths(gui_paths):
    """Like gui_paths, but with a small fixture tree pre-built.

    Contents: one raw dataset (Dataset027_ACDC, 3 cases, single CT channel) that
    is preprocessed and has two completed runs (3d_fullres fold_0 and 2d fold_0).
    """
    from nnunetv2.tests.gui.fixtures.builders import (
        build_dataset_raw,
        build_dataset_preprocessed,
        build_run,
    )

    folder = build_dataset_raw(gui_paths["raw"], dataset_id=27, name="ACDC")
    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder=folder)
    build_run(gui_paths["results"], dataset_folder=folder, configuration="3d_fullres", fold="0")
    build_run(gui_paths["results"], dataset_folder=folder, configuration="2d", fold="0")
    return gui_paths
```

- [ ] **Step 3: Verify fixtures import + pytest collection still works**

Run: `pytest nnunetv2/tests/gui/ -q --collect-only 2>&1 | tail -3`
Expected: collection succeeds, no errors.

- [ ] **Step 4: Commit**

```bash
git add nnunetv2/tests/gui/fixtures/ nnunetv2/tests/gui/conftest.py
git commit -m "gui(tests): fixture builders for fake nnUNet trees + populated_paths"
```

---

## Task 3: Discovery — raw dataset scanner (TDD)

**Files:**
- Create: `nnunetv2/gui/state/__init__.py` (empty)
- Create: `nnunetv2/gui/state/discovery.py` (partial — raw scanner only; later tasks extend it)
- Create: `nnunetv2/tests/gui/unit/test_discovery.py`

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/unit/test_discovery.py`:
```python
from __future__ import annotations

from nnunetv2.gui.state.discovery import scan_raw_datasets


def test_scan_raw_empty_returns_empty(gui_paths):
    found = scan_raw_datasets(gui_paths["raw"])
    assert found == []


def test_scan_raw_finds_dataset(populated_paths):
    found = scan_raw_datasets(populated_paths["raw"])
    assert len(found) == 1
    d = found[0]
    assert d.id == "Dataset027_ACDC"
    assert d.dataset_id_int == 27
    assert d.name == "ACDC"
    assert d.case_count == 3
    assert d.modality_count == 1
    assert d.raw_path == str(populated_paths["raw"] / "Dataset027_ACDC")


def test_scan_raw_skips_non_dataset_dirs(populated_paths, tmp_path):
    # Create a noise directory that shouldn't be picked up
    (populated_paths["raw"] / "not_a_dataset").mkdir()
    (populated_paths["raw"] / "README.md").write_text("ignore me")

    found = scan_raw_datasets(populated_paths["raw"])
    ids = [d.id for d in found]
    assert ids == ["Dataset027_ACDC"]


def test_scan_raw_handles_multi_modality(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    build_dataset_raw(
        gui_paths["raw"],
        dataset_id=42,
        name="BraTS",
        case_ids=["c1", "c2"],
        channels={"0": "T1", "1": "T1ce", "2": "T2", "3": "FLAIR"},
    )
    found = scan_raw_datasets(gui_paths["raw"])
    assert len(found) == 1
    assert found[0].modality_count == 4
    assert found[0].case_count == 2
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v`
Expected: import error or function-not-found errors.

- [ ] **Step 3: Implement the raw scanner**

`nnunetv2/gui/state/__init__.py`:
```python
```

`nnunetv2/gui/state/discovery.py`:
```python
"""Filesystem scanners that turn nnU-Net on-disk artifacts into model records."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DATASET_DIR_RE = re.compile(r"^Dataset(\d{3})_(.+)$")


@dataclass(frozen=True)
class DiscoveredDataset:
    id: str
    dataset_id_int: Optional[int]
    name: Optional[str]
    raw_path: str
    case_count: int
    modality_count: int


def scan_raw_datasets(raw_root: Path) -> list[DiscoveredDataset]:
    """Walk `raw_root` and return one DiscoveredDataset per Dataset<XXX>_<Name> dir."""
    if not raw_root.is_dir():
        return []
    out: list[DiscoveredDataset] = []
    for entry in sorted(raw_root.iterdir()):
        if not entry.is_dir():
            continue
        m = DATASET_DIR_RE.match(entry.name)
        if not m:
            continue
        ds = _read_one_raw(entry, m)
        out.append(ds)
    return out


def _read_one_raw(folder: Path, name_match: re.Match[str]) -> DiscoveredDataset:
    dataset_id_int = int(name_match.group(1))
    name = name_match.group(2)
    cases, modalities = _count_cases_and_modalities(folder)
    return DiscoveredDataset(
        id=folder.name,
        dataset_id_int=dataset_id_int,
        name=name,
        raw_path=str(folder),
        case_count=cases,
        modality_count=modalities,
    )


def _count_cases_and_modalities(folder: Path) -> tuple[int, int]:
    # Prefer dataset.json if present (authoritative for channels)
    modality_count = 0
    ds_json = folder / "dataset.json"
    if ds_json.is_file():
        try:
            data = json.loads(ds_json.read_text())
            channels = data.get("channel_names") or {}
            modality_count = len(channels)
        except (json.JSONDecodeError, OSError):
            modality_count = 0

    images_tr = folder / "imagesTr"
    if not images_tr.is_dir():
        return 0, modality_count
    case_ids: set[str] = set()
    for f in images_tr.iterdir():
        # Pattern: <case>_<NNNN>.<ext-or-extensions>
        stem = f.name.split(".")[0]  # strip multi-suffix .nii.gz
        # last "_NNNN" is the modality index
        m = re.match(r"^(.+)_(\d{4})$", stem)
        if not m:
            continue
        case_ids.add(m.group(1))
    return len(case_ids), modality_count
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v`
Expected: 4 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/__init__.py nnunetv2/gui/state/discovery.py nnunetv2/tests/gui/unit/test_discovery.py
git commit -m "gui(state): raw-dataset scanner with case + modality counts"
```

---

## Task 4: Discovery — preprocessed marker + fingerprint reader (TDD)

**Files:**
- Modify: `nnunetv2/gui/state/discovery.py`
- Modify: `nnunetv2/tests/gui/unit/test_discovery.py`

- [ ] **Step 1: Append the failing tests**

Append to `nnunetv2/tests/gui/unit/test_discovery.py`:

```python


def test_scan_preprocessed_marks_dataset(populated_paths):
    from nnunetv2.gui.state.discovery import scan_preprocessed
    pre = scan_preprocessed(populated_paths["preprocessed"])
    assert pre == {"Dataset027_ACDC": str(populated_paths["preprocessed"] / "Dataset027_ACDC")}


def test_scan_preprocessed_empty(gui_paths):
    from nnunetv2.gui.state.discovery import scan_preprocessed
    assert scan_preprocessed(gui_paths["preprocessed"]) == {}


def test_read_fingerprint_returns_dict(populated_paths):
    from nnunetv2.gui.state.discovery import read_fingerprint
    fp = read_fingerprint(populated_paths["preprocessed"] / "Dataset027_ACDC")
    assert "spacings" in fp


def test_read_fingerprint_missing_returns_none(tmp_path):
    from nnunetv2.gui.state.discovery import read_fingerprint
    (tmp_path / "no_fp").mkdir()
    assert read_fingerprint(tmp_path / "no_fp") is None
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v -k "preprocessed or fingerprint"`
Expected: 4 failures.

- [ ] **Step 3: Add to `nnunetv2/gui/state/discovery.py`**

Append these functions at the end of the module:

```python
def scan_preprocessed(preprocessed_root: Path) -> dict[str, str]:
    """Return {dataset_folder_name: absolute_path} for every preprocessed dataset."""
    if not preprocessed_root.is_dir():
        return {}
    out: dict[str, str] = {}
    for entry in sorted(preprocessed_root.iterdir()):
        if not entry.is_dir():
            continue
        if not DATASET_DIR_RE.match(entry.name):
            continue
        out[entry.name] = str(entry)
    return out


def read_fingerprint(dataset_preprocessed_dir: Path) -> Optional[dict]:
    """Read dataset_fingerprint.json if present; return None otherwise."""
    fp = dataset_preprocessed_dir / "dataset_fingerprint.json"
    if not fp.is_file():
        return None
    try:
        return json.loads(fp.read_text())
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v`
Expected: 8 passes (4 from Task 3 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/discovery.py nnunetv2/tests/gui/unit/test_discovery.py
git commit -m "gui(state): scan_preprocessed + read_fingerprint helpers"
```

---

## Task 5: Discovery — results runs scanner (TDD)

**Files:**
- Modify: `nnunetv2/gui/state/discovery.py`
- Modify: `nnunetv2/tests/gui/unit/test_discovery.py`

- [ ] **Step 1: Append the failing tests**

Append to `nnunetv2/tests/gui/unit/test_discovery.py`:

```python


def test_scan_results_finds_runs(populated_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs
    runs = scan_results_runs(populated_paths["results"])
    assert len(runs) == 2
    ids = sorted(r.id for r in runs)
    assert ids == [
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__2d/fold_0",
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0",
    ]
    for r in runs:
        assert r.dataset_id == "Dataset027_ACDC"
        assert r.plans_name == "nnUNetPlans"
        assert r.trainer_name == "nnUNetTrainer"
        assert r.fold == "0"
        assert r.status == "completed"  # checkpoint_final.pth exists


def test_scan_results_marks_abandoned_when_no_final_checkpoint(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    from nnunetv2.gui.state.discovery import scan_results_runs

    build_run(gui_paths["results"], dataset_folder="Dataset099_X",
              configuration="3d_fullres", fold="2", completed=False)
    runs = scan_results_runs(gui_paths["results"])
    assert len(runs) == 1
    assert runs[0].status == "abandoned"


def test_scan_results_handles_fold_all(gui_paths):
    from nnunetv2.tests.gui.fixtures.builders import build_run
    from nnunetv2.gui.state.discovery import scan_results_runs

    build_run(gui_paths["results"], dataset_folder="Dataset100_Y",
              configuration="3d_fullres", fold="all")
    runs = scan_results_runs(gui_paths["results"])
    assert len(runs) == 1
    assert runs[0].fold == "all"


def test_scan_results_skips_garbage_dirs(populated_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs

    (populated_paths["results"] / "Dataset027_ACDC" / "junk_not_a_run_dir").mkdir()
    (populated_paths["results"] / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "validation_only_no_fold.txt").touch()
    runs = scan_results_runs(populated_paths["results"])
    # Should still be the 2 runs from populated_paths
    assert len(runs) == 2


def test_scan_results_empty(gui_paths):
    from nnunetv2.gui.state.discovery import scan_results_runs
    assert scan_results_runs(gui_paths["results"]) == []
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v -k "results"`
Expected: 5 failures.

- [ ] **Step 3: Append to `nnunetv2/gui/state/discovery.py`**

Add at the top:
```python
RUN_DIR_RE = re.compile(r"^(.+)__(.+)__(.+)$")
FOLD_DIR_RE = re.compile(r"^fold_(.+)$")
```

Add a new dataclass after `DiscoveredDataset`:

```python
@dataclass(frozen=True)
class DiscoveredRun:
    id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    output_folder: str
    status: str  # 'completed' | 'abandoned'
```

Add the scanner at the end of the file:

```python
def scan_results_runs(results_root: Path) -> list[DiscoveredRun]:
    """Walk `results_root`, yielding one DiscoveredRun per fold_* directory."""
    if not results_root.is_dir():
        return []
    out: list[DiscoveredRun] = []
    for dataset_dir in sorted(results_root.iterdir()):
        if not dataset_dir.is_dir() or not DATASET_DIR_RE.match(dataset_dir.name):
            continue
        for plans_trainer_config_dir in sorted(dataset_dir.iterdir()):
            if not plans_trainer_config_dir.is_dir():
                continue
            m = RUN_DIR_RE.match(plans_trainer_config_dir.name)
            if not m:
                continue
            plans_name, trainer_name, configuration = m.group(1), m.group(2), m.group(3)
            for fold_dir in sorted(plans_trainer_config_dir.iterdir()):
                if not fold_dir.is_dir():
                    continue
                fm = FOLD_DIR_RE.match(fold_dir.name)
                if not fm:
                    continue
                fold = fm.group(1)
                status = "completed" if (fold_dir / "checkpoint_final.pth").is_file() else "abandoned"
                canonical_id = f"{dataset_dir.name}/{plans_trainer_config_dir.name}/{fold_dir.name}"
                out.append(DiscoveredRun(
                    id=canonical_id,
                    dataset_id=dataset_dir.name,
                    plans_name=plans_name,
                    trainer_name=trainer_name,
                    configuration=configuration,
                    fold=fold,
                    output_folder=str(fold_dir),
                    status=status,
                ))
    return out
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_discovery.py -v`
Expected: 13 passes (8 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/discovery.py nnunetv2/tests/gui/unit/test_discovery.py
git commit -m "gui(state): scan_results_runs with canonical-key identity + status inference"
```

---

## Task 6: Dataset repository (TDD)

**Files:**
- Create: `nnunetv2/gui/state/datasets.py`
- Create: `nnunetv2/tests/gui/unit/test_datasets_repo.py`

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/unit/test_datasets_repo.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.datasets import Dataset, list_datasets, get_dataset, upsert_dataset


def _make(id="Dataset027_ACDC", **overrides) -> Dataset:
    d = Dataset(
        id=id, dataset_id_int=27, name="ACDC",
        raw_path="/raw/Dataset027_ACDC",
        preprocessed_path=None,
        last_scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprint_json=None,
        case_count=3, modality_count=1,
    )
    return d.model_copy(update=overrides)


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_datasets(gui_config) == []


def test_upsert_and_get(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make())
    fetched = get_dataset(gui_config, "Dataset027_ACDC")
    assert fetched is not None
    assert fetched.id == "Dataset027_ACDC"
    assert fetched.case_count == 3


def test_upsert_updates_existing(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make())
    upsert_dataset(gui_config, _make(case_count=5))
    fetched = get_dataset(gui_config, "Dataset027_ACDC")
    assert fetched.case_count == 5
    assert len(list_datasets(gui_config)) == 1


def test_list_sorted_by_dataset_id_int(gui_config):
    init_db(gui_config)
    upsert_dataset(gui_config, _make(id="Dataset100_X", dataset_id_int=100))
    upsert_dataset(gui_config, _make(id="Dataset027_ACDC", dataset_id_int=27))
    ids = [d.id for d in list_datasets(gui_config)]
    assert ids == ["Dataset027_ACDC", "Dataset100_X"]


def test_get_missing_returns_none(gui_config):
    init_db(gui_config)
    assert get_dataset(gui_config, "Dataset999_Nope") is None
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_datasets_repo.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `nnunetv2/gui/state/datasets.py`**

```python
"""Dataset record and repository functions."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import dataset_table, session_scope


class Dataset(BaseModel):
    id: str
    dataset_id_int: Optional[int]
    name: Optional[str]
    raw_path: Optional[str]
    preprocessed_path: Optional[str]
    last_scanned_at: Optional[datetime]
    fingerprint_json: Optional[str]
    case_count: Optional[int]
    modality_count: Optional[int]


def _row_to_model(row) -> Dataset:
    return Dataset(
        id=row.id,
        dataset_id_int=row.dataset_id_int,
        name=row.name,
        raw_path=row.raw_path,
        preprocessed_path=row.preprocessed_path,
        last_scanned_at=row.last_scanned_at,
        fingerprint_json=row.fingerprint_json,
        case_count=row.case_count,
        modality_count=row.modality_count,
    )


def list_datasets(cfg: GuiConfig) -> list[Dataset]:
    with session_scope(cfg) as s:
        rows = s.execute(
            select(dataset_table).order_by(dataset_table.c.dataset_id_int.asc().nulls_last())
        ).all()
    return [_row_to_model(r) for r in rows]


def get_dataset(cfg: GuiConfig, dataset_id: str) -> Optional[Dataset]:
    with session_scope(cfg) as s:
        row = s.execute(
            select(dataset_table).where(dataset_table.c.id == dataset_id)
        ).first()
    return _row_to_model(row) if row else None


def upsert_dataset(cfg: GuiConfig, dataset: Dataset) -> None:
    values = dataset.model_dump()
    with session_scope(cfg) as s:
        existing = s.execute(
            select(dataset_table.c.id).where(dataset_table.c.id == dataset.id)
        ).first()
        if existing:
            s.execute(
                dataset_table.update()
                .where(dataset_table.c.id == dataset.id)
                .values(**values)
            )
        else:
            s.execute(dataset_table.insert().values(**values))


def fingerprint_dict(dataset: Dataset) -> Optional[dict]:
    if not dataset.fingerprint_json:
        return None
    try:
        return json.loads(dataset.fingerprint_json)
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_datasets_repo.py -v`
Expected: 5 passes.

Also confirm `pydantic` is available: it isn't in `[gui]` extra directly but is a hard dep of `fastapi`. Verify with `python -c "import pydantic; print(pydantic.VERSION)"`. (Pydantic 2.x is expected.)

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/datasets.py nnunetv2/tests/gui/unit/test_datasets_repo.py
git commit -m "gui(state): Dataset model + repository (list/get/upsert)"
```

---

## Task 7: Run repository with filters (TDD)

**Files:**
- Create: `nnunetv2/gui/state/runs.py`
- Create: `nnunetv2/tests/gui/unit/test_runs_repo.py`

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/unit/test_runs_repo.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.runs import (
    Run, RunFilter, canonical_run_id, list_runs, get_run, upsert_run,
)


def _make(**overrides) -> Run:
    base = Run(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0"),
        dataset_id="Dataset027_ACDC",
        plans_name="nnUNetPlans",
        trainer_name="nnUNetTrainer",
        configuration="3d_fullres",
        fold="0",
        output_folder="/results/.../fold_0",
        status="completed",
        source="cli",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        tags_json=None,
        notes=None,
    )
    return base.model_copy(update=overrides)


def test_canonical_run_id_shape():
    assert canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0") == \
        "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"


def test_list_empty(gui_config):
    init_db(gui_config)
    assert list_runs(gui_config, RunFilter()) == []


def test_upsert_and_get(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    fetched = get_run(gui_config, _make().id)
    assert fetched is not None
    assert fetched.configuration == "3d_fullres"


def test_filter_by_dataset_id(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset042_BraTS", "nnUNetPlans", "nnUNetTrainer", "3d_fullres", "0"),
        dataset_id="Dataset042_BraTS",
    ))
    runs = list_runs(gui_config, RunFilter(dataset_id="Dataset027_ACDC"))
    assert len(runs) == 1
    assert runs[0].dataset_id == "Dataset027_ACDC"


def test_filter_by_status(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "2d", "0"),
        configuration="2d", status="abandoned",
    ))
    completed = list_runs(gui_config, RunFilter(status="completed"))
    abandoned = list_runs(gui_config, RunFilter(status="abandoned"))
    assert len(completed) == 1
    assert len(abandoned) == 1


def test_filter_by_multiple_fields(gui_config):
    init_db(gui_config)
    upsert_run(gui_config, _make())
    upsert_run(gui_config, _make(
        id=canonical_run_id("Dataset027_ACDC", "nnUNetPlans", "nnUNetTrainer", "2d", "1"),
        configuration="2d", fold="1",
    ))
    runs = list_runs(gui_config, RunFilter(configuration="3d_fullres", fold="0"))
    assert len(runs) == 1
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_runs_repo.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `nnunetv2/gui/state/runs.py`**

```python
"""Run record and repository functions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import run_table, session_scope


class Run(BaseModel):
    id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    output_folder: str
    status: str
    source: str
    created_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    tags_json: Optional[str]
    notes: Optional[str]


class RunFilter(BaseModel):
    dataset_id: Optional[str] = None
    plans_name: Optional[str] = None
    trainer_name: Optional[str] = None
    configuration: Optional[str] = None
    fold: Optional[str] = None
    status: Optional[str] = None


def canonical_run_id(
    dataset_id: str,
    plans_name: str,
    trainer_name: str,
    configuration: str,
    fold: str,
) -> str:
    return f"{dataset_id}/{plans_name}__{trainer_name}__{configuration}/fold_{fold}"


def _row_to_model(row) -> Run:
    return Run(
        id=row.id,
        dataset_id=row.dataset_id,
        plans_name=row.plans_name,
        trainer_name=row.trainer_name,
        configuration=row.configuration,
        fold=row.fold,
        output_folder=row.output_folder,
        status=row.status,
        source=row.source,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        tags_json=row.tags_json,
        notes=row.notes,
    )


def list_runs(cfg: GuiConfig, flt: RunFilter) -> list[Run]:
    stmt = select(run_table)
    if flt.dataset_id:
        stmt = stmt.where(run_table.c.dataset_id == flt.dataset_id)
    if flt.plans_name:
        stmt = stmt.where(run_table.c.plans_name == flt.plans_name)
    if flt.trainer_name:
        stmt = stmt.where(run_table.c.trainer_name == flt.trainer_name)
    if flt.configuration:
        stmt = stmt.where(run_table.c.configuration == flt.configuration)
    if flt.fold:
        stmt = stmt.where(run_table.c.fold == flt.fold)
    if flt.status:
        stmt = stmt.where(run_table.c.status == flt.status)
    stmt = stmt.order_by(run_table.c.last_seen_at.desc().nulls_last())
    with session_scope(cfg) as s:
        rows = s.execute(stmt).all()
    return [_row_to_model(r) for r in rows]


def get_run(cfg: GuiConfig, run_id: str) -> Optional[Run]:
    with session_scope(cfg) as s:
        row = s.execute(
            select(run_table).where(run_table.c.id == run_id)
        ).first()
    return _row_to_model(row) if row else None


def upsert_run(cfg: GuiConfig, run: Run) -> None:
    values = run.model_dump()
    with session_scope(cfg) as s:
        existing = s.execute(
            select(run_table.c.id).where(run_table.c.id == run.id)
        ).first()
        if existing:
            s.execute(
                run_table.update().where(run_table.c.id == run.id).values(**values)
            )
        else:
            s.execute(run_table.insert().values(**values))
```

- [ ] **Step 4: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_runs_repo.py -v`
Expected: 6 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/runs.py nnunetv2/tests/gui/unit/test_runs_repo.py
git commit -m "gui(state): Run model + repository with composable filters"
```

---

## Task 8: Reconcile orchestrator + startup hook (TDD)

**Files:**
- Modify: `nnunetv2/gui/state/discovery.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/unit/test_reconcile.py`

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/unit/test_reconcile.py`:
```python
from __future__ import annotations

from nnunetv2.gui.db import init_db
from nnunetv2.gui.state.discovery import reconcile
from nnunetv2.gui.state.datasets import list_datasets, get_dataset
from nnunetv2.gui.state.runs import list_runs, RunFilter


def test_reconcile_empty(gui_config):
    init_db(gui_config)
    reconcile(gui_config)
    assert list_datasets(gui_config) == []
    assert list_runs(gui_config, RunFilter()) == []


def test_reconcile_populates(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)
    reconcile(cfg)

    datasets = list_datasets(cfg)
    assert len(datasets) == 1
    assert datasets[0].id == "Dataset027_ACDC"
    assert datasets[0].preprocessed_path is not None
    assert datasets[0].fingerprint_json is not None

    runs = list_runs(cfg, RunFilter())
    assert len(runs) == 2


def test_reconcile_is_idempotent(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)

    reconcile(cfg)
    reconcile(cfg)

    assert len(list_datasets(cfg)) == 1
    assert len(list_runs(cfg, RunFilter())) == 2


def test_reconcile_updates_dataset_preprocessed_path(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw, build_dataset_preprocessed
    build_dataset_raw(gui_paths["raw"], dataset_id=99, name="X")
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    init_db(cfg)

    reconcile(cfg)
    ds = get_dataset(cfg, "Dataset099_X")
    assert ds.preprocessed_path is None

    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder="Dataset099_X")
    reconcile(cfg)
    ds = get_dataset(cfg, "Dataset099_X")
    assert ds.preprocessed_path is not None
    assert ds.fingerprint_json is not None
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/unit/test_reconcile.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `reconcile` in `discovery.py`**

Append to `nnunetv2/gui/state/discovery.py`:

```python
def reconcile(cfg) -> None:
    """One-shot scan of raw + preprocessed + results, upserting all records.

    Imports the repositories lazily to keep `discovery` decoupled from `state.{datasets,runs}`.
    """
    from datetime import datetime, timezone
    import json

    from nnunetv2.gui.state.datasets import Dataset, upsert_dataset, get_dataset
    from nnunetv2.gui.state.runs import Run, upsert_run

    now = datetime.now(timezone.utc)
    preprocessed_map = scan_preprocessed(cfg.preprocessed)

    for d in scan_raw_datasets(cfg.raw):
        preprocessed_path = preprocessed_map.get(d.id)
        fingerprint_json = None
        if preprocessed_path:
            fp = read_fingerprint(Path(preprocessed_path))
            if fp is not None:
                fingerprint_json = json.dumps(fp)
        ds = Dataset(
            id=d.id,
            dataset_id_int=d.dataset_id_int,
            name=d.name,
            raw_path=d.raw_path,
            preprocessed_path=preprocessed_path,
            last_scanned_at=now,
            fingerprint_json=fingerprint_json,
            case_count=d.case_count,
            modality_count=d.modality_count,
        )
        upsert_dataset(cfg, ds)

    for r in scan_results_runs(cfg.results):
        # Preserve created_at if the row already exists; otherwise set now.
        # For Phase 1 we treat last_seen_at = now for any rediscovered run.
        from nnunetv2.gui.state.runs import get_run
        existing = get_run(cfg, r.id)
        created = existing.created_at if existing else now
        run = Run(
            id=r.id,
            dataset_id=r.dataset_id,
            plans_name=r.plans_name,
            trainer_name=r.trainer_name,
            configuration=r.configuration,
            fold=r.fold,
            output_folder=r.output_folder,
            status=r.status,
            source=existing.source if existing else "unknown",
            created_at=created,
            last_seen_at=now,
            tags_json=existing.tags_json if existing else None,
            notes=existing.notes if existing else None,
        )
        upsert_run(cfg, run)
```

- [ ] **Step 4: Wire `reconcile` into `create_app`**

Modify `/Users/puyangwang/nnUNet/nnunetv2/gui/server.py`. Add an import at the top of the imports block:

```python
from nnunetv2.gui.state.discovery import reconcile
```

Inside `create_app`, after `init_db(cfg)` and before `app = FastAPI(...)`, add:

```python
    reconcile(cfg)
```

- [ ] **Step 5: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/unit/test_reconcile.py -v`
Expected: 4 passes.

Also run full gui tests: `pytest nnunetv2/tests/gui/ -v`. All previous tests must still pass.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/state/discovery.py nnunetv2/gui/server.py nnunetv2/tests/gui/unit/test_reconcile.py
git commit -m "gui(state): reconcile orchestrator + startup hook"
```

---

## Task 9: `/api/datasets` router (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/datasets.py`
- Create: `nnunetv2/tests/gui/api/test_datasets_api.py`
- Modify: `nnunetv2/gui/server.py` (include router)

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/api/test_datasets_api.py`:
```python
from __future__ import annotations


def test_list_datasets_empty(client):
    r = client.get("/api/datasets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_datasets_populated(populated_paths, monkeypatch):
    # Rebuild app pointed at populated_paths
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    app = create_app(cfg)
    c = TestClient(app)

    r = c.get("/api/datasets")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "Dataset027_ACDC"
    assert body[0]["case_count"] == 3


def test_get_dataset_detail(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "Dataset027_ACDC"
    assert body["modality_count"] == 1


def test_get_dataset_not_found(client):
    r = client.get("/api/datasets/Dataset999_NoSuch")
    assert r.status_code == 404


def test_get_dataset_plans(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC/plans")
    assert r.status_code == 200
    body = r.json()
    # populated_paths created runs with default plans.json containing "plans_name"
    assert "plans_name" in body or "configurations" in body


def test_get_dataset_plans_not_found_for_unpreprocessed(client):
    r = client.get("/api/datasets/Dataset027_ACDC/plans")
    assert r.status_code == 404


def test_get_dataset_fingerprint(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset027_ACDC/fingerprint")
    assert r.status_code == 200
    body = r.json()
    assert "spacings" in body
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/api/test_datasets_api.py -v`
Expected: 7 failures (404s on routes that don't exist).

- [ ] **Step 3: Implement `nnunetv2/gui/routers/datasets.py`**

```python
"""Datasets router."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.datasets import (
    Dataset, list_datasets, get_dataset, fingerprint_dict,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/datasets", tags=["datasets"])

    @router.get("", response_model=list[Dataset])
    def list_all(request: Request) -> list[Dataset]:
        return list_datasets(request.app.state.gui_config)

    @router.get("/{dataset_id}", response_model=Dataset)
    def get_one(dataset_id: str, request: Request) -> Dataset:
        d = get_dataset(request.app.state.gui_config, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        return d

    @router.get("/{dataset_id}/plans")
    def get_plans(dataset_id: str, request: Request) -> dict:
        cfg = request.app.state.gui_config
        d = get_dataset(cfg, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        # Look for plans.json under any results subfolder for this dataset (any run).
        results_dataset_dir = Path(cfg.results) / dataset_id
        if results_dataset_dir.is_dir():
            for run_dir in results_dataset_dir.iterdir():
                plans_path = run_dir / "plans.json"
                if plans_path.is_file():
                    try:
                        return json.loads(plans_path.read_text())
                    except json.JSONDecodeError:
                        continue
        raise HTTPException(status_code=404, detail="No plans.json found for this dataset")

    @router.get("/{dataset_id}/fingerprint")
    def get_fingerprint(dataset_id: str, request: Request) -> dict:
        cfg = request.app.state.gui_config
        d = get_dataset(cfg, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        fp = fingerprint_dict(d)
        if fp is None:
            raise HTTPException(status_code=404, detail="No fingerprint available")
        return fp

    return router
```

- [ ] **Step 4: Include the router in `create_app`**

Modify `/Users/puyangwang/nnUNet/nnunetv2/gui/server.py`. Add an import at the top:

```python
from nnunetv2.gui.routers import datasets as datasets_router
```

Inside `create_app`, after `app.include_router(system_router.make_router())`, add:

```python
    app.include_router(datasets_router.make_router())
```

- [ ] **Step 5: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/api/test_datasets_api.py -v`
Expected: 7 passes.

Also run full gui tests.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/datasets.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_datasets_api.py
git commit -m "gui(api): /api/datasets list, detail, plans, fingerprint endpoints"
```

---

## Task 10: `/api/runs` router (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/runs.py`
- Create: `nnunetv2/tests/gui/api/test_runs_api.py`
- Modify: `nnunetv2/gui/server.py` (include router)

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/api/test_runs_api.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_runs_empty(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_populated(populated_client):
    r = populated_client.get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(run["dataset_id"] == "Dataset027_ACDC" for run in body)


def test_list_runs_filter_by_dataset_id(populated_client):
    r = populated_client.get("/api/runs?dataset_id=Dataset027_ACDC")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = populated_client.get("/api/runs?dataset_id=Dataset999_None")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_filter_by_configuration(populated_client):
    r = populated_client.get("/api/runs?configuration=3d_fullres")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["configuration"] == "3d_fullres"


def test_list_runs_filter_by_status(populated_client):
    r = populated_client.get("/api/runs?status=completed")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_run_detail(populated_client):
    r = populated_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["configuration"] == "3d_fullres"
    assert body["fold"] == "0"


def test_get_run_not_found(client):
    r = client.get("/api/runs/Dataset999_None/x__y__z/fold_0")
    assert r.status_code == 404
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/api/test_runs_api.py -v`
Expected: failures from missing route.

- [ ] **Step 3: Implement `nnunetv2/gui/routers/runs.py`**

```python
"""Runs router."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.runs import Run, RunFilter, list_runs, get_run


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["runs"])

    @router.get("", response_model=list[Run])
    def list_all(
        request: Request,
        dataset_id: Optional[str] = None,
        plans_name: Optional[str] = None,
        trainer_name: Optional[str] = None,
        configuration: Optional[str] = None,
        fold: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[Run]:
        flt = RunFilter(
            dataset_id=dataset_id,
            plans_name=plans_name,
            trainer_name=trainer_name,
            configuration=configuration,
            fold=fold,
            status=status,
        )
        return list_runs(request.app.state.gui_config, flt)

    # Run IDs contain slashes — use path: converter to capture the full string.
    @router.get("/{run_id:path}", response_model=Run)
    def get_one(run_id: str, request: Request) -> Run:
        r = get_run(request.app.state.gui_config, run_id)
        if r is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        return r

    return router
```

- [ ] **Step 4: Include router in `create_app`**

Add an import at the top of `nnunetv2/gui/server.py`:

```python
from nnunetv2.gui.routers import runs as runs_router
```

After `app.include_router(datasets_router.make_router())`:

```python
    app.include_router(runs_router.make_router())
```

- [ ] **Step 5: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/api/test_runs_api.py -v`
Expected: 7 passes.

Full suite still green.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/runs.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_runs_api.py
git commit -m "gui(api): /api/runs list (with filters) + detail endpoints"
```

---

## Task 11: `/api/dashboard` router (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/dashboard.py`
- Create: `nnunetv2/tests/gui/api/test_dashboard_api.py`
- Modify: `nnunetv2/gui/server.py`

- [ ] **Step 1: Write the failing tests**

`nnunetv2/tests/gui/api/test_dashboard_api.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture
def populated_client(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_dashboard_empty(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["datasets"] == 0
    assert body["counts"]["preprocessed_datasets"] == 0
    assert body["counts"]["runs"] == 0
    assert body["counts"]["completed_runs"] == 0
    assert body["recent_runs"] == []
    # active_jobs is always present, always empty in Phase 1
    assert body["active_jobs"] == []


def test_dashboard_populated(populated_client):
    r = populated_client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["datasets"] == 1
    assert body["counts"]["preprocessed_datasets"] == 1
    assert body["counts"]["runs"] == 2
    assert body["counts"]["completed_runs"] == 2
    assert len(body["recent_runs"]) == 2
    assert "system" in body
    assert "disk" in body["system"]


def test_dashboard_recent_runs_sorted_newest_first(populated_client):
    r = populated_client.get("/api/dashboard")
    body = r.json()
    seen = [run["last_seen_at"] for run in body["recent_runs"] if run["last_seen_at"]]
    assert seen == sorted(seen, reverse=True)
```

- [ ] **Step 2: Run; confirm fail**

Run: `pytest nnunetv2/tests/gui/api/test_dashboard_api.py -v`
Expected: 3 failures.

- [ ] **Step 3: Implement `nnunetv2/gui/routers/dashboard.py`**

```python
"""Dashboard router — aggregate stats for the landing page."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Request

from nnunetv2.gui.state.datasets import list_datasets
from nnunetv2.gui.state.runs import RunFilter, list_runs


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

    @router.get("")
    def get_dashboard(request: Request) -> dict:
        cfg = request.app.state.gui_config
        datasets = list_datasets(cfg)
        runs = list_runs(cfg, RunFilter())
        completed = [r for r in runs if r.status == "completed"]
        preprocessed = [d for d in datasets if d.preprocessed_path]

        recent = sorted(
            runs,
            key=lambda r: r.last_seen_at or r.created_at or 0,
            reverse=True,
        )[:6]

        def _disk(path: str) -> dict:
            try:
                usage = shutil.disk_usage(path)
                return {"path": path, "total": usage.total, "free": usage.free}
            except OSError:
                return {"path": path, "total": None, "free": None}

        return {
            "counts": {
                "datasets": len(datasets),
                "preprocessed_datasets": len(preprocessed),
                "runs": len(runs),
                "completed_runs": len(completed),
            },
            "recent_runs": [r.model_dump(mode="json") for r in recent],
            "active_jobs": [],  # Phase 3 fills this
            "system": {
                "disk": {
                    "raw": _disk(str(cfg.raw)),
                    "preprocessed": _disk(str(cfg.preprocessed)),
                    "results": _disk(str(cfg.results)),
                },
                # GPU stats land in Phase 7.
            },
        }

    return router
```

- [ ] **Step 4: Include router in `create_app`**

Add import:
```python
from nnunetv2.gui.routers import dashboard as dashboard_router
```

After `app.include_router(runs_router.make_router())`:
```python
    app.include_router(dashboard_router.make_router())
```

- [ ] **Step 5: Run; confirm pass**

Run: `pytest nnunetv2/tests/gui/api/test_dashboard_api.py -v`
Expected: 3 passes.

Full suite green: `pytest nnunetv2/tests/gui/ -v`. Run with clean env too.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/dashboard.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_dashboard_api.py
git commit -m "gui(api): /api/dashboard aggregate stats endpoint"
```

---

## Task 12: Frontend types + typed API endpoints

**Files:**
- Create: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Create `frontend/src/lib/types.ts`**

```ts
export interface Dataset {
  id: string;
  dataset_id_int: number | null;
  name: string | null;
  raw_path: string | null;
  preprocessed_path: string | null;
  last_scanned_at: string | null;
  fingerprint_json: string | null;
  case_count: number | null;
  modality_count: number | null;
}

export interface Run {
  id: string;
  dataset_id: string;
  plans_name: string;
  trainer_name: string;
  configuration: string;
  fold: string;
  output_folder: string;
  status: string;
  source: string;
  created_at: string | null;
  last_seen_at: string | null;
  tags_json: string | null;
  notes: string | null;
}

export interface RunFilter {
  dataset_id?: string;
  plans_name?: string;
  trainer_name?: string;
  configuration?: string;
  fold?: string;
  status?: string;
}

export interface DiskUsage {
  path: string;
  total: number | null;
  free: number | null;
}

export interface DashboardData {
  counts: {
    datasets: number;
    preprocessed_datasets: number;
    runs: number;
    completed_runs: number;
  };
  recent_runs: Run[];
  active_jobs: unknown[];
  system: {
    disk: {
      raw: DiskUsage;
      preprocessed: DiskUsage;
      results: DiskUsage;
    };
  };
}
```

- [ ] **Step 2: Extend `frontend/src/lib/api.ts`**

After the existing `api` export, add typed-endpoint helpers. The final file looks like this:

```ts
export class ApiError extends Error {
  readonly kind: string;
  readonly retryable: boolean;
  readonly details: unknown;
  readonly status: number;

  constructor(opts: {
    kind: string;
    message: string;
    retryable: boolean;
    details: unknown;
    status: number;
  }) {
    super(opts.message);
    this.name = 'ApiError';
    this.kind = opts.kind;
    this.retryable = opts.retryable;
    this.details = opts.details;
    this.status = opts.status;
  }
}

async function envelope(res: Response): Promise<never> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiError({
      kind: 'http_error',
      message: `HTTP ${res.status} ${res.statusText}`,
      retryable: res.status >= 500,
      details: null,
      status: res.status,
    });
  }
  const env = body as {
    kind?: string;
    message?: string;
    retryable?: boolean;
    details?: unknown;
  };
  throw new ApiError({
    kind: env.kind ?? 'http_error',
    message: env.message ?? `HTTP ${res.status}`,
    retryable: env.retryable ?? res.status >= 500,
    details: env.details ?? null,
    status: res.status,
  });
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    await envelope(res);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get<T>(url: string): Promise<T> {
    return request<T>(url);
  },
  post<T>(url: string, body: unknown): Promise<T> {
    return request<T>(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
};

import type { Dataset, Run, RunFilter, DashboardData } from './types';

function qs(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, v);
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export const endpoints = {
  getDatasets: () => api.get<Dataset[]>('/api/datasets'),
  getDataset: (id: string) => api.get<Dataset>(`/api/datasets/${encodeURIComponent(id)}`),
  getDatasetPlans: (id: string) =>
    api.get<Record<string, unknown>>(`/api/datasets/${encodeURIComponent(id)}/plans`),
  getDatasetFingerprint: (id: string) =>
    api.get<Record<string, unknown>>(`/api/datasets/${encodeURIComponent(id)}/fingerprint`),
  getRuns: (filter: RunFilter = {}) => api.get<Run[]>(`/api/runs${qs(filter)}`),
  getRun: (id: string) => api.get<Run>(`/api/runs/${id}`),
  getDashboard: () => api.get<DashboardData>('/api/dashboard'),
};
```

- [ ] **Step 3: Confirm svelte-check passes**

Run: `cd frontend && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "gui(frontend): types + typed endpoint helpers for datasets/runs/dashboard"
```

---

## Task 13: Async stores for datasets / runs / dashboard (TDD)

**Files:**
- Create: `frontend/src/lib/stores/datasets.ts`
- Create: `frontend/src/lib/stores/runs.ts`
- Create: `frontend/src/lib/stores/dashboard.ts`
- Create: `frontend/src/lib/stores/datasets.test.ts`
- Create: `frontend/src/lib/stores/runs.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/lib/stores/datasets.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createDatasetsStore } from './datasets';

describe('datasets store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('starts in idle state', () => {
    const store = createDatasetsStore();
    expect(store.get()).toEqual({ kind: 'idle' });
  });

  it('transitions to loading then loaded on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify([
        { id: 'Dataset001_X', dataset_id_int: 1, name: 'X', raw_path: '/r',
          preprocessed_path: null, last_scanned_at: null,
          fingerprint_json: null, case_count: 5, modality_count: 1 },
      ]), { status: 200 })),
    );

    const store = createDatasetsStore();
    const states: string[] = [];
    store.subscribe((s) => states.push(s.kind));

    await store.load();

    expect(states).toEqual(['idle', 'loading', 'loaded']);
    const final = store.get();
    expect(final.kind).toBe('loaded');
    if (final.kind === 'loaded') {
      expect(final.data).toHaveLength(1);
      expect(final.data[0].id).toBe('Dataset001_X');
    }
  });

  it('transitions to error on 5xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(
        JSON.stringify({ kind: 'internal_error', message: 'boom', retryable: false, details: null }),
        { status: 500 },
      )),
    );

    const store = createDatasetsStore();
    await store.load();

    const final = store.get();
    expect(final.kind).toBe('error');
    if (final.kind === 'error') {
      expect(final.error.message).toContain('boom');
    }
  });
});
```

`frontend/src/lib/stores/runs.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRunsStore } from './runs';

describe('runs store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('passes filter as query string', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createRunsStore();
    await store.load({ dataset_id: 'Dataset027_ACDC', status: 'completed' });

    expect(mock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/runs\?.*dataset_id=Dataset027_ACDC.*status=completed/),
      undefined,
    );
  });

  it('omits empty filter values from query string', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createRunsStore();
    await store.load({});

    expect(mock).toHaveBeenCalledWith('/api/runs', undefined);
  });
});
```

- [ ] **Step 2: Run; confirm fail**

Run: `cd frontend && npm test -- datasets runs`

- [ ] **Step 3: Implement the three stores**

`frontend/src/lib/stores/datasets.ts`:
```ts
import { endpoints } from '../api';
import { ApiError } from '../api';
import type { Dataset } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Dataset[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createDatasetsStore() {
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
    async load(): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getDatasets();
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
```

`frontend/src/lib/stores/runs.ts`:
```ts
import { endpoints, ApiError } from '../api';
import type { Run, RunFilter } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Run[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createRunsStore() {
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
    async load(filter: RunFilter = {}): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getRuns(filter);
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
```

`frontend/src/lib/stores/dashboard.ts`:
```ts
import { endpoints, ApiError } from '../api';
import type { DashboardData } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: DashboardData }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createDashboardStore() {
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
    async load(): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getDashboard();
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

Run: `cd frontend && npm test`
Expected: 15 (Phase 0) + 5 new = 20 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stores/datasets.ts frontend/src/lib/stores/runs.ts frontend/src/lib/stores/dashboard.ts \
        frontend/src/lib/stores/datasets.test.ts frontend/src/lib/stores/runs.test.ts
git commit -m "gui(frontend): async stores for datasets, runs, dashboard with idle/loading/loaded/error states"
```

---

## Task 14: WorkspaceSwitcher component + WorkspaceHeader integration

**Files:**
- Create: `frontend/src/components/WorkspaceSwitcher.svelte`
- Modify: `frontend/src/components/WorkspaceHeader.svelte`

- [ ] **Step 1: Create `WorkspaceSwitcher.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Dataset } from '../lib/types';

  const datasets = createDatasetsStore();
  const workspace = createWorkspaceStore();

  let state = $state(datasets.get());
  let current = $state<string | null>(workspace.get());
  let open = $state(false);

  onMount(() => {
    const unsubDatasets = datasets.subscribe((s) => (state = s));
    const unsubWorkspace = workspace.subscribe((v) => (current = v));
    datasets.load();
    return () => {
      unsubDatasets();
      unsubWorkspace();
    };
  });

  function select(d: Dataset): void {
    workspace.set(d.id);
    open = false;
  }

  function clear(): void {
    workspace.clear();
    open = false;
  }

  function options(): Dataset[] {
    if (state.kind === 'loaded') return state.data;
    return [];
  }
</script>

<div class="relative inline-block">
  <button
    class="bg-bg-soft px-2 py-0.5 rounded text-slate-400 hover:bg-bg-panel"
    onclick={() => (open = !open)}
  >
    Workspace: {current ?? '(none — pick a dataset)'} ▾
  </button>

  {#if open}
    <div class="absolute z-10 mt-1 min-w-[220px] bg-bg-panel border border-border-soft rounded shadow-lg text-xs">
      {#if state.kind === 'loading'}
        <div class="px-3 py-2 text-slate-500">Loading…</div>
      {:else if state.kind === 'error'}
        <div class="px-3 py-2 text-err">Failed to load datasets</div>
      {:else if options().length === 0}
        <div class="px-3 py-2 text-slate-500">No datasets found</div>
      {:else}
        {#each options() as d}
          <button
            class="block w-full text-left px-3 py-1.5 hover:bg-bg-soft"
            class:text-accent={current === d.id}
            onclick={() => select(d)}
          >
            {d.id}
            {#if d.preprocessed_path}<span class="text-ok ml-1">✓</span>{/if}
          </button>
        {/each}
      {/if}
      {#if current}
        <button class="block w-full text-left px-3 py-1.5 border-t border-border-soft text-slate-500 hover:bg-bg-soft" onclick={clear}>
          Clear workspace
        </button>
      {/if}
    </div>
  {/if}
</div>
```

- [ ] **Step 2: Replace the placeholder pill in `WorkspaceHeader.svelte`**

The current file (from Phase 0) has a placeholder span. Replace it with `<WorkspaceSwitcher/>`. Final content:

```svelte
<script lang="ts">
  import WorkspaceSwitcher from './WorkspaceSwitcher.svelte';
</script>

<header
  class="flex items-center gap-3 bg-bg-panel border-b border-border px-4 py-2 text-xs"
>
  <strong class="text-slate-100">nnU-Net Manager</strong>

  <WorkspaceSwitcher />

  <span class="bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded-full text-[10px]">
    ● 0 jobs running
  </span>

  <span class="text-amber-400 text-[10px]">GPU: pending</span>

  <span class="flex-1"></span>

  <a href="#/settings" class="text-slate-400 hover:text-slate-200">⚙ Settings</a>
</header>
```

- [ ] **Step 3: Run svelte-check + build**

Run: `cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 errors, build succeeds.

- [ ] **Step 4: Commit (include rebuilt bundle)**

```bash
git add frontend/src/components/WorkspaceSwitcher.svelte frontend/src/components/WorkspaceHeader.svelte
git add nnunetv2/gui/web/
git commit -m "gui(frontend): WorkspaceSwitcher dropdown wired to /api/datasets"
```

---

## Task 15: DashboardCards component + Dashboard route

**Files:**
- Create: `frontend/src/components/DashboardCards.svelte`
- Modify: `frontend/src/routes/Dashboard.svelte`

- [ ] **Step 1: Create `DashboardCards.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createDashboardStore } from '../lib/stores/dashboard';

  const dash = createDashboardStore();
  let state = $state(dash.get());

  onMount(() => {
    const unsub = dash.subscribe((s) => (state = s));
    dash.load();
    return unsub;
  });

  function gb(n: number | null): string {
    if (n === null) return '—';
    return (n / 1024 / 1024 / 1024).toFixed(1) + ' GB';
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading dashboard…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">Failed to load dashboard: {state.error.message}</p>
{:else}
  <div class="grid grid-cols-2 gap-3">
    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Active jobs</h3>
      <p class="text-sm text-slate-400">{state.data.active_jobs.length === 0 ? 'No jobs running. Live tracking lands in Phase 3.' : ''}</p>
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Recent runs</h3>
      {#if state.data.recent_runs.length === 0}
        <p class="text-sm text-slate-400">No runs yet.</p>
      {:else}
        <ul class="space-y-1">
          {#each state.data.recent_runs as run}
            <li class="text-xs">
              <span class="text-slate-200">{run.dataset_id}</span>
              <span class="text-slate-500">·</span>
              <span class="text-slate-400">{run.configuration} · fold_{run.fold}</span>
              <span class="text-slate-500">·</span>
              <span class:text-ok={run.status === 'completed'} class:text-slate-500={run.status !== 'completed'}>{run.status}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Datasets</h3>
      <p class="text-sm text-slate-200">{state.data.counts.datasets} raw · {state.data.counts.preprocessed_datasets} preprocessed</p>
      <p class="text-xs text-slate-500 mt-1">{state.data.counts.runs} runs total, {state.data.counts.completed_runs} completed</p>
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">System</h3>
      <ul class="text-xs space-y-1">
        <li>Raw: <span class="text-slate-400">{gb(state.data.system.disk.raw.free)} free of {gb(state.data.system.disk.raw.total)}</span></li>
        <li>Preprocessed: <span class="text-slate-400">{gb(state.data.system.disk.preprocessed.free)} free of {gb(state.data.system.disk.preprocessed.total)}</span></li>
        <li>Results: <span class="text-slate-400">{gb(state.data.system.disk.results.free)} free of {gb(state.data.system.disk.results.total)}</span></li>
      </ul>
      <p class="text-[10px] text-slate-600 mt-2">GPU stats land in Phase 7.</p>
    </section>
  </div>
{/if}
```

- [ ] **Step 2: Replace `frontend/src/routes/Dashboard.svelte`**

```svelte
<script lang="ts">
  import DashboardCards from '../components/DashboardCards.svelte';
</script>

<h2 class="text-lg font-semibold text-slate-100">Dashboard</h2>
<div class="mt-4">
  <DashboardCards />
</div>
```

- [ ] **Step 3: svelte-check + build**

Run: `cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DashboardCards.svelte frontend/src/routes/Dashboard.svelte
git add nnunetv2/gui/web/
git commit -m "gui(frontend): Dashboard cards backed by /api/dashboard"
```

---

## Task 16: PlansViewer + FingerprintViewer components

**Files:**
- Create: `frontend/src/components/PlansViewer.svelte`
- Create: `frontend/src/components/FingerprintViewer.svelte`

- [ ] **Step 1: Create `PlansViewer.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints, ApiError } from '../lib/api';

  let { datasetId }: { datasetId: string } = $props();

  let state = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: Record<string, unknown> }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  onMount(() => {
    state = { kind: 'loading' };
    endpoints
      .getDatasetPlans(datasetId)
      .then((data) => (state = { kind: 'loaded', data }))
      .catch((e) => (state = { kind: 'error', error: e }));
  });
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading plans…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">
    {state.error instanceof ApiError && state.error.status === 404
      ? 'No plans.json found — run plan_and_preprocess first.'
      : `Failed to load plans: ${state.error.message}`}
  </p>
{:else}
  <pre class="text-[11px] text-slate-300 bg-bg-soft border border-border-soft rounded p-3 overflow-auto max-h-96">{JSON.stringify(state.data, null, 2)}</pre>
{/if}
```

- [ ] **Step 2: Create `FingerprintViewer.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints, ApiError } from '../lib/api';

  let { datasetId }: { datasetId: string } = $props();

  let state = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: Record<string, unknown> }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  onMount(() => {
    state = { kind: 'loading' };
    endpoints
      .getDatasetFingerprint(datasetId)
      .then((data) => (state = { kind: 'loaded', data }))
      .catch((e) => (state = { kind: 'error', error: e }));
  });

  function spacings(d: Record<string, unknown>): number[][] {
    const s = d['spacings'];
    if (Array.isArray(s)) return s as number[][];
    return [];
  }

  function intensityProps(d: Record<string, unknown>): Record<string, Record<string, number>> {
    const obj = d['foreground_intensity_properties_per_channel'];
    if (obj && typeof obj === 'object') return obj as Record<string, Record<string, number>>;
    return {};
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading fingerprint…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">
    {state.error instanceof ApiError && state.error.status === 404
      ? 'No fingerprint.json — dataset has not been preprocessed yet.'
      : `Failed to load fingerprint: ${state.error.message}`}
  </p>
{:else}
  <div class="space-y-4">
    <section>
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Spacings (first {Math.min(5, spacings(state.data).length)} of {spacings(state.data).length})</h4>
      <ul class="text-xs space-y-0.5">
        {#each spacings(state.data).slice(0, 5) as s}
          <li class="text-slate-300 font-mono">[{s.map((v) => v.toFixed(3)).join(', ')}]</li>
        {/each}
      </ul>
    </section>

    <section>
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Intensity per channel</h4>
      <table class="text-xs w-full">
        <thead>
          <tr class="text-slate-500 border-b border-border-soft">
            <th class="text-left py-1">Channel</th>
            <th class="text-right py-1">Mean</th>
            <th class="text-right py-1">Std</th>
          </tr>
        </thead>
        <tbody>
          {#each Object.entries(intensityProps(state.data)) as [ch, props]}
            <tr>
              <td class="py-1 text-slate-300">{ch}</td>
              <td class="py-1 text-right text-slate-400">{(props.mean ?? NaN).toFixed(2)}</td>
              <td class="py-1 text-right text-slate-400">{(props.std ?? NaN).toFixed(2)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  </div>
{/if}
```

- [ ] **Step 3: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PlansViewer.svelte frontend/src/components/FingerprintViewer.svelte
git add nnunetv2/gui/web/
git commit -m "gui(frontend): PlansViewer + FingerprintViewer components"
```

---

## Task 17: DatasetList + DatasetDetail components

**Files:**
- Create: `frontend/src/components/DatasetList.svelte`
- Create: `frontend/src/components/DatasetDetail.svelte`

- [ ] **Step 1: Create `DatasetList.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import type { Dataset } from '../lib/types';

  let { selectedId, onSelect }: { selectedId: string | null; onSelect: (d: Dataset) => void } = $props();

  const datasets = createDatasetsStore();
  let state = $state(datasets.get());

  onMount(() => {
    const unsub = datasets.subscribe((s) => (state = s));
    datasets.load();
    return unsub;
  });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2">
  <h3 class="text-xs uppercase tracking-wider text-slate-500 px-2 py-1">All datasets</h3>
  {#if state.kind === 'loading' || state.kind === 'idle'}
    <p class="px-2 py-1 text-xs text-slate-500">Loading…</p>
  {:else if state.kind === 'error'}
    <p class="px-2 py-1 text-xs text-err">{state.error.message}</p>
  {:else if state.data.length === 0}
    <p class="px-2 py-1 text-xs text-slate-500">No datasets in nnUNet_raw</p>
  {:else}
    <ul class="text-xs">
      {#each state.data as d}
        <li>
          <button
            class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
            class:text-accent={d.id === selectedId}
            class:text-slate-300={d.id !== selectedId}
            onclick={() => onSelect(d)}
          >
            {d.id}
            {#if d.preprocessed_path}
              <span class="text-ok ml-1" title="preprocessed">✓</span>
            {:else}
              <span class="text-slate-600 ml-1" title="raw only">◯</span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
```

- [ ] **Step 2: Create `DatasetDetail.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints, ApiError } from '../lib/api';
  import type { Dataset } from '../lib/types';
  import PlansViewer from './PlansViewer.svelte';
  import FingerprintViewer from './FingerprintViewer.svelte';

  let { datasetId }: { datasetId: string } = $props();

  type Tab = 'cases' | 'plans' | 'fingerprint' | 'validation';
  let tab = $state<Tab>('cases');

  let state = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: Dataset }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  $effect(() => {
    state = { kind: 'loading' };
    endpoints
      .getDataset(datasetId)
      .then((data) => (state = { kind: 'loaded', data }))
      .catch((e) => (state = { kind: 'error', error: e }));
  });

  const TABS: { id: Tab; label: string }[] = [
    { id: 'cases', label: 'Cases' },
    { id: 'plans', label: 'Plans' },
    { id: 'fingerprint', label: 'Fingerprint' },
    { id: 'validation', label: 'Validation' },
  ];
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading dataset…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">{state.error.message}</p>
{:else}
  <div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
    <div class="flex items-center gap-2">
      <strong class="text-sm text-slate-100">{state.data.id}</strong>
      <span class="text-xs bg-bg-panel px-2 py-0.5 rounded text-slate-400">{state.data.case_count ?? '?'} cases</span>
      <span class="text-xs bg-bg-panel px-2 py-0.5 rounded text-slate-400">{state.data.modality_count ?? '?'} modality(s)</span>
      {#if state.data.preprocessed_path}
        <span class="text-xs bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded">✓ preprocessed</span>
      {:else}
        <span class="text-xs bg-bg-panel text-slate-500 px-2 py-0.5 rounded">raw only</span>
      {/if}
    </div>
  </div>

  <div class="bg-bg-soft border border-border-soft rounded p-3">
    <div class="flex gap-1 border-b border-border-soft pb-2 mb-3">
      {#each TABS as t}
        <button
          class="px-3 py-1 text-xs rounded"
          class:bg-bg-panel={tab === t.id}
          class:text-slate-100={tab === t.id}
          class:text-slate-500={tab !== t.id}
          onclick={() => (tab = t.id)}
        >
          {t.label}
        </button>
      {/each}
    </div>

    {#if tab === 'cases'}
      <p class="text-sm text-slate-400">Case browser + NiiVue viewer land in Phase 2.</p>
    {:else if tab === 'plans'}
      <PlansViewer datasetId={state.data.id} />
    {:else if tab === 'fingerprint'}
      <FingerprintViewer datasetId={state.data.id} />
    {:else if tab === 'validation'}
      <p class="text-sm text-slate-400">Dataset-integrity check lands later in Phase 1+.</p>
    {/if}
  </div>
{/if}
```

- [ ] **Step 3: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DatasetList.svelte frontend/src/components/DatasetDetail.svelte
git add nnunetv2/gui/web/
git commit -m "gui(frontend): DatasetList + DatasetDetail with tabs"
```

---

## Task 18: Datasets route wiring

**Files:**
- Modify: `frontend/src/routes/Datasets.svelte`

- [ ] **Step 1: Replace `Datasets.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import DatasetList from '../components/DatasetList.svelte';
  import DatasetDetail from '../components/DatasetDetail.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Dataset } from '../lib/types';

  const ws = createWorkspaceStore();
  let selectedId = $state<string | null>(ws.get());

  onMount(() => ws.subscribe((v) => (selectedId = v)));

  function onSelect(d: Dataset): void {
    ws.set(d.id);
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Datasets</h2>
<div class="mt-4 flex gap-3">
  <div class="w-56 flex-shrink-0">
    <DatasetList {selectedId} {onSelect} />
  </div>
  <div class="flex-1 min-w-0">
    {#if selectedId}
      <DatasetDetail datasetId={selectedId} />
    {:else}
      <p class="text-sm text-slate-400">Pick a dataset on the left, or pick one from the Workspace switcher in the header.</p>
    {/if}
  </div>
</div>
```

- [ ] **Step 2: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/Datasets.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Datasets route uses real list + detail components"
```

---

## Task 19: RunsTable component + Monitor route

**Files:**
- Create: `frontend/src/components/RunsTable.svelte`
- Modify: `frontend/src/routes/Monitor.svelte`

- [ ] **Step 1: Create `RunsTable.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createRunsStore } from '../lib/stores/runs';
  import type { Run, RunFilter } from '../lib/types';

  let { filter = {} as RunFilter }: { filter?: RunFilter } = $props();

  const runs = createRunsStore();
  let state = $state(runs.get());

  type SortKey = 'dataset_id' | 'configuration' | 'fold' | 'status' | 'last_seen_at';
  let sortBy = $state<SortKey>('last_seen_at');
  let sortDir = $state<'asc' | 'desc'>('desc');

  onMount(() => {
    const unsub = runs.subscribe((s) => (state = s));
    runs.load(filter);
    return unsub;
  });

  function sorted(data: Run[]): Run[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...data].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortBy] ?? '';
      const bv = (b as unknown as Record<string, unknown>)[sortBy] ?? '';
      if (av < bv) return -1 * mult;
      if (av > bv) return 1 * mult;
      return 0;
    });
  }

  function setSort(k: SortKey): void {
    if (sortBy === k) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else {
      sortBy = k;
      sortDir = 'desc';
    }
  }

  function arrow(k: SortKey): string {
    if (sortBy !== k) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading runs…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">{state.error.message}</p>
{:else if state.data.length === 0}
  <p class="text-sm text-slate-400">No runs found.</p>
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
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('last_seen_at')}>Last seen{arrow('last_seen_at')}</th>
      </tr>
    </thead>
    <tbody>
      {#each sorted(state.data) as r}
        <tr class="border-b border-border-soft">
          <td class="py-1 px-2 text-slate-300">{r.dataset_id}</td>
          <td class="py-1 px-2 text-slate-300">{r.configuration}</td>
          <td class="py-1 px-2 text-slate-400">{r.trainer_name}</td>
          <td class="py-1 px-2 text-slate-400">{r.plans_name}</td>
          <td class="py-1 px-2 text-slate-300">{r.fold}</td>
          <td class="py-1 px-2">
            <span class:text-ok={r.status === 'completed'} class:text-slate-500={r.status !== 'completed'}>{r.status}</span>
          </td>
          <td class="py-1 px-2 text-slate-500">{r.last_seen_at ?? '—'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
```

- [ ] **Step 2: Replace `Monitor.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import RunsTable from '../components/RunsTable.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { RunFilter } from '../lib/types';

  const ws = createWorkspaceStore();
  let workspaceId = $state<string | null>(ws.get());

  onMount(() => ws.subscribe((v) => (workspaceId = v)));

  let filter = $derived<RunFilter>(workspaceId ? { dataset_id: workspaceId } : {});
</script>

<h2 class="text-lg font-semibold text-slate-100">Monitor</h2>
<p class="text-xs text-amber-400 mt-1">Live curves + image samples + log tail land in Phase 3. Phase 1 shows the historical run list.</p>

<div class="mt-4">
  <RunsTable {filter} />
</div>
```

- [ ] **Step 3: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/RunsTable.svelte frontend/src/routes/Monitor.svelte
git add nnunetv2/gui/web/
git commit -m "gui(frontend): RunsTable component + Monitor route shows historical runs"
```

---

## Task 20: End-to-end smoke + docs refresh

**Files:**
- Modify: `documentation/gui.md`

- [ ] **Step 1: Run the full test pyramid**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && cd ..
```
Expected: all green. Phase 0's 26 backend tests grew to ~52 (depends on exact counts), and 15 frontend tests grew to ~20.

- [ ] **Step 2: Boot the server with a real-ish fixture**

```bash
NNUNET_RAW=$(mktemp -d) NNUNET_PRE=$(mktemp -d) NNUNET_RES=$(mktemp -d)
python -c "
from pathlib import Path
from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw, build_dataset_preprocessed, build_run
import os
raw = Path(os.environ['NNUNET_RAW']); pre = Path(os.environ['NNUNET_PRE']); res = Path(os.environ['NNUNET_RES'])
build_dataset_raw(raw, dataset_id=27, name='ACDC')
build_dataset_preprocessed(pre, dataset_folder='Dataset027_ACDC')
build_run(res, dataset_folder='Dataset027_ACDC', configuration='3d_fullres', fold='0')
build_run(res, dataset_folder='Dataset027_ACDC', configuration='2d', fold='0')
print('ok')
"
nnUNet_raw=$NNUNET_RAW \
nnUNet_preprocessed=$NNUNET_PRE \
nnUNet_results=$NNUNET_RES \
  nnUNetv2_gui --port 8765 &
PID=$!
sleep 2
curl -s http://127.0.0.1:8765/api/datasets | head -c 200; echo
curl -s http://127.0.0.1:8765/api/runs | head -c 200; echo
curl -s http://127.0.0.1:8765/api/dashboard | head -c 400; echo
kill $PID
```

Expected: dataset list shows `Dataset027_ACDC` with `case_count: 3`, runs list has 2 entries, dashboard shows counts `{datasets: 1, preprocessed_datasets: 1, runs: 2, completed_runs: 2}`.

- [ ] **Step 3: Open in a real browser and confirm by eye**

Restart the server, open `http://127.0.0.1:8765` in a browser, navigate Dashboard / Datasets / Monitor. Confirm:
- Dashboard cards populated.
- Datasets page lists `Dataset027_ACDC` with the green ✓; clicking it shows the detail pane with Plans + Fingerprint tabs.
- Monitor shows the 2 runs in a sortable table.
- Workspace dropdown in the header lists the dataset; selecting it persists across navigation.

- [ ] **Step 4: Update `documentation/gui.md`**

Replace the "Roadmap" section's Phase 0 entry and Phase 1 entry with:

```markdown
0. **Foundation** ✓ — scaffold, CLI, healthz.
1. **Read-only browse** ✓ — filesystem discovery, dataset/run lists, plans/fingerprint inspector, dashboard cards backed by historical data.
2. **Image viewer** — NiiVue, case browser, prediction review.
```

(Leave Phases 2–7 untouched.)

Also add a new "What you can do today" section between "Launch" and "Security":

```markdown
## What you can do today (after Phase 1)

- Browse every dataset in `$nnUNet_raw` from the **Datasets** page.
- Inspect any dataset's `plans.json` and `dataset_fingerprint.json`.
- Browse every training run in `$nnUNet_results` from the **Monitor** page.
- Use the **Workspace** switcher in the header to scope downstream pages to a single dataset.
- See aggregate stats and recent runs on the **Dashboard**.

Phase 1 is read-only — launching trainings, live monitoring, predictions, and exports arrive in Phases 3–6.
```

- [ ] **Step 5: Commit**

```bash
git add documentation/gui.md
git commit -m "gui(docs): refresh Phase 1 entry + 'what you can do today' section"
```

---

## Done condition

Phase 1 is complete when:

- [ ] All gui pytest tests pass on host + clean env.
- [ ] All frontend vitest tests pass.
- [ ] svelte-check is 0 errors.
- [ ] `nnUNetv2_gui` boots; `/api/{datasets,runs,dashboard}` return real data from filesystem.
- [ ] Browser: Dashboard, Datasets, Monitor all show real data; Workspace switcher works.
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 1 completion.

Then return to writing-plans for Phase 2 (Image viewer — NiiVue, case browser, prediction review).
