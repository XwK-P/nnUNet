# nnU-Net GUI — Phase 2 (Image Viewer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every NIfTI case visible. Add a server-side image service (open NIfTI with nibabel, decode slices into PNG bytes, LRU-cache), three new REST endpoints (`/cases`, `/cases/{id}/preview`, `/cases/{id}/labels`), prediction listing per run, and a Svelte `NiiVueViewer` component that the Datasets → Cases tab and the run/prediction review pane both consume.

**Architecture:** A new `nnunetv2.gui.services.images` module owns NIfTI I/O, returning either decoded PNG bytes (server-side) or volume bytes for client-side NiiVue rendering. The existing `datasets` and `runs` routers gain new sub-paths. The Svelte UI uses **NiiVue** (WebGL2) for full 3-D volumes and falls back to PNG `<img>` tags for the small thumbnails. The Cases tab placeholder from Phase 1 is replaced with a real CasesList. Prediction review for completed runs lives on the Monitor route's existing run identity bar.

**Tech Stack:** Adds `nibabel` (Python) and `@niivue/niivue` (npm). Re-uses Pillow (already in `[gui]` extra) for slice → PNG encoding. No changes to nnUNet core training code.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "UI Pages" → "Datasets" (Cases tab) and "Predict" (3-pane viewer description — Phase 6 expands; Phase 2 covers the basics). Architectural decision from controller: in-memory LRU bounded by item count (default 256 slices), no disk cache.

**TDD discipline:** Every behavioral change starts with a failing test. One commit per task. PNG round-tripping is tested with a synthetic 3-D numpy array — no checked-in `.nii.gz` until the very last task.

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/services/__init__.py` | Package marker |
| `nnunetv2/gui/services/images.py` | `open_nifti(path)`, `slice_to_png(arr, axis, index, window)`, `slice_lru_cache` (functools), `list_cases(dataset_dir)`, `case_files(...)` |
| `nnunetv2/gui/state/cases.py` | `Case` Pydantic model (id, channels, label_path), `list_cases_for_dataset(cfg, dataset_id)` |
| `nnunetv2/gui/routers/datasets.py` (mod) | Add `/cases`, `/cases/{case_id}/preview`, `/cases/{case_id}/labels` endpoints. Preview takes `axis`, `slice`, `channel`, `window` query params; returns `image/png`. |
| `nnunetv2/gui/routers/runs.py` (mod) | Add `/predictions` (list prediction outputs for a run) and `/predictions/{case_id}` (PNG preview, mirrors dataset preview signature) |
| `nnunetv2/gui/services/cli_renderer.py` | Placeholder file with `__all__ = []` — Phase 4 fills it; created here so the `services` package import surface is set up. |
| `nnunetv2/tests/gui/fixtures/builders.py` (mod) | Add `build_case_nifti(folder, name, shape=(16,16,16))` helper that writes a tiny valid NIfTI with `nibabel`. |
| `nnunetv2/tests/gui/unit/test_images_service.py` | Slice/decode/cache tests against builder NIfTI volumes |
| `nnunetv2/tests/gui/unit/test_cases_state.py` | Case discovery from raw dataset trees |
| `nnunetv2/tests/gui/api/test_cases_api.py` | `/api/datasets/{id}/cases` + preview/labels endpoint contract |
| `nnunetv2/tests/gui/api/test_predictions_api.py` | `/api/runs/{id}/predictions` + per-case endpoint contract |
| `nnunetv2/tests/gui/fixtures/data/tiny.nii.gz` | One checked-in synthetic NIfTI (≈4 KB) so the e2e + viewer smoke tests have real bytes. Built in Task 11. |
| `frontend/src/lib/types.ts` (mod) | Add `Case`, `Prediction` types |
| `frontend/src/lib/api.ts` (mod) | Add `getCases`, `getCasePreviewUrl`, `getPredictions`, `getPredictionPreviewUrl` |
| `frontend/src/lib/stores/cases.ts` | Async store of `Case[]` |
| `frontend/src/lib/viewer/NiiVueViewer.svelte` | Wrapper around `@niivue/niivue`. Props: `volumeUrl`, `overlayUrl`, `overlayOpacity`, `axis`, `slice`, `lut`. |
| `frontend/src/lib/viewer/Canvas2DViewer.svelte` | Fallback PNG `<img>` viewer for when WebGL2 is unavailable |
| `frontend/src/components/CasesList.svelte` | List of cases inside a dataset; emits select |
| `frontend/src/components/CaseViewer.svelte` | Composes axis switch, slice scrubber, channel select, overlay opacity, LUT picker, and embeds `NiiVueViewer` |
| `frontend/src/components/PredictionList.svelte` | List of cases that have a prediction for a given run |
| `frontend/src/components/DatasetDetail.svelte` (mod) | Replace the Cases tab placeholder with `<CasesList/>` + `<CaseViewer/>` |
| `frontend/src/components/RunDetail.svelte` | New right pane for the Monitor route; contains run identity bar + "Predictions" sub-section (Phase 3 will add Curves/Log tabs) |
| `frontend/src/routes/Monitor.svelte` (mod) | Layout: left = `<RunsTable>`, right = `<RunDetail>` when a row is selected |
| `frontend/src/lib/viewer/NiiVueViewer.test.ts` | Lightweight test: mounts component with a fake URL, asserts NiiVue constructor is called. NiiVue itself is mocked. |
| `package.json` (mod) | Add `@niivue/niivue` dep |
| `pyproject.toml` (mod) | Add `nibabel` under `[project.optional-dependencies] gui = [...]` |

---

## Task 1: Declare new dependencies and bump fixture builders (TDD-light)

**Files:**
- Modify: `pyproject.toml`
- Modify: `frontend/package.json`
- Modify: `nnunetv2/tests/gui/fixtures/builders.py`

- [ ] **Step 1: Add `nibabel` to the `[gui]` extra**

In `pyproject.toml`, the `[project.optional-dependencies] gui = [...]` block has `nibabel` listed in the spec already. Verify it is present; add it if missing:

```toml
gui = [
    # ... existing deps ...
    "nibabel>=5.0",
]
```

- [ ] **Step 2: Add NiiVue to `frontend/package.json`**

```bash
cd frontend && npm install --save @niivue/niivue
```

This will pin the version. Commit the changed `package.json` + `package-lock.json`.

- [ ] **Step 3: Extend `builders.py` with NIfTI helper**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_case_nifti(folder: Path, name: str, shape: tuple[int, int, int] = (16, 16, 16)) -> Path:
    """Write a tiny synthetic NIfTI under `folder/name`. Returns the file path.

    Uses nibabel to produce a real, openable file with deterministic content
    (a per-voxel index gradient). Roughly 4 KB for shape (16,16,16) float32.
    """
    import numpy as np
    import nibabel as nib
    folder.mkdir(parents=True, exist_ok=True)
    arr = np.arange(int(np.prod(shape)), dtype=np.float32).reshape(shape)
    img = nib.Nifti1Image(arr, affine=np.eye(4))
    path = folder / name
    nib.save(img, str(path))
    return path
```

- [ ] **Step 4: Verify install + collection**

```bash
pip install -e ".[gui]"
python -c "import nibabel; print(nibabel.__version__)"
pytest nnunetv2/tests/gui/ -q --collect-only 2>&1 | tail -3
```

Expected: nibabel imports, collection clean.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml frontend/package.json frontend/package-lock.json nnunetv2/tests/gui/fixtures/builders.py
git commit -m "gui(deps): add nibabel (Python) + @niivue/niivue (frontend) for Phase 2 image viewer"
```

---

## Task 2: `services.images` — open + slice + LRU (TDD)

**Files:**
- Create: `nnunetv2/gui/services/__init__.py` (empty)
- Create: `nnunetv2/gui/services/images.py`
- Create: `nnunetv2/tests/gui/unit/test_images_service.py`

- [ ] **Step 1: Write failing tests**

`nnunetv2/tests/gui/unit/test_images_service.py`:

```python
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from nnunetv2.gui.services.images import (
    open_nifti, slice_to_png, get_slice_png_cached, clear_slice_cache,
)


@pytest.fixture
def nifti_file(tmp_path):
    from nnunetv2.tests.gui.fixtures.builders import build_case_nifti
    return build_case_nifti(tmp_path, "case_001_0000.nii.gz", shape=(8, 16, 32))


def test_open_nifti_returns_array_and_spacing(nifti_file):
    arr, spacing = open_nifti(nifti_file)
    assert arr.shape == (8, 16, 32)
    assert arr.dtype.kind == "f"
    assert len(spacing) == 3


def test_slice_to_png_axial(nifti_file):
    arr, _ = open_nifti(nifti_file)
    png_bytes = slice_to_png(arr, axis=0, index=4)
    img = Image.open(io.BytesIO(png_bytes))
    # Axis 0 with shape (8,16,32) -> 16x32 image
    assert img.size == (32, 16)


def test_slice_to_png_out_of_range_clamps(nifti_file):
    arr, _ = open_nifti(nifti_file)
    # Index past end should clamp to last valid slice, not crash
    png_bytes = slice_to_png(arr, axis=0, index=999)
    assert len(png_bytes) > 100


def test_slice_to_png_respects_window(nifti_file):
    arr, _ = open_nifti(nifti_file)
    # Same slice, different windows → different PNGs
    a = slice_to_png(arr, axis=0, index=0, window=(0, 100))
    b = slice_to_png(arr, axis=0, index=0, window=(0, 1000))
    assert a != b


def test_lru_cache_returns_same_bytes(nifti_file):
    clear_slice_cache()
    a = get_slice_png_cached(str(nifti_file), axis=0, index=0, window=None)
    b = get_slice_png_cached(str(nifti_file), axis=0, index=0, window=None)
    assert a is b  # cache returns the exact same bytes object


def test_lru_cache_bounded(nifti_file):
    clear_slice_cache()
    # Fill with > 256 entries; the first should evict.
    for i in range(260):
        get_slice_png_cached(str(nifti_file), axis=0, index=i % 8, window=(float(i), float(i + 1)))
    # Total cached entries should not exceed the bound (default 256)
    from nnunetv2.gui.services.images import slice_cache_size
    assert slice_cache_size() <= 256
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_images_service.py -v
```

Expected: import errors / not implemented.

- [ ] **Step 3: Implement `services/images.py`**

```python
"""On-demand NIfTI slice decoding for the GUI image viewer.

Returns PNG-encoded slices with an LRU cache bounded by item count.
No disk cache — the cache is per-process and survives only as long as the
server. Volumes themselves are not cached; only encoded slice PNGs are.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import nibabel as nib
from PIL import Image


SLICE_CACHE_MAXSIZE = 256


def open_nifti(path: Path | str) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Open `path` with nibabel and return (data, spacing).

    Data is returned as a float32 numpy array regardless of on-disk dtype.
    Spacing is (sx, sy, sz) in mm.
    """
    img = nib.load(str(path))
    arr = np.asarray(img.dataobj, dtype=np.float32)
    zooms = img.header.get_zooms()[:3]
    spacing = (float(zooms[0]), float(zooms[1]), float(zooms[2]))
    return arr, spacing


def slice_to_png(
    arr: np.ndarray,
    *,
    axis: int,
    index: int,
    window: Optional[tuple[float, float]] = None,
) -> bytes:
    """Take a 2-D slice from `arr` along `axis` at `index` and encode as PNG.

    `window` is (low, high) intensity to map to (0, 255); when None, scale
    to the slice's min/max range.
    """
    if arr.ndim != 3:
        raise ValueError(f"expected 3-D array, got shape {arr.shape}")
    idx = max(0, min(arr.shape[axis] - 1, int(index)))
    if axis == 0:
        sl = arr[idx, :, :]
    elif axis == 1:
        sl = arr[:, idx, :]
    elif axis == 2:
        sl = arr[:, :, idx]
    else:
        raise ValueError(f"axis must be 0, 1, or 2; got {axis}")
    if window is not None:
        lo, hi = window
    else:
        lo, hi = float(sl.min()), float(sl.max())
    if hi <= lo:
        norm = np.zeros_like(sl, dtype=np.uint8)
    else:
        norm = np.clip(((sl - lo) / (hi - lo)) * 255.0, 0, 255).astype(np.uint8)
    img = Image.fromarray(norm, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Cache uses a key of (str(path), axis, index, window) so it is hashable.
@lru_cache(maxsize=SLICE_CACHE_MAXSIZE)
def _cached(path: str, axis: int, index: int, window: Optional[tuple[float, float]]) -> bytes:
    arr, _ = open_nifti(Path(path))
    return slice_to_png(arr, axis=axis, index=index, window=window)


def get_slice_png_cached(
    path: str,
    *,
    axis: int,
    index: int,
    window: Optional[tuple[float, float]] = None,
) -> bytes:
    return _cached(path, axis, index, window)


def clear_slice_cache() -> None:
    _cached.cache_clear()


def slice_cache_size() -> int:
    return _cached.cache_info().currsize
```

- [ ] **Step 4: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/unit/test_images_service.py -v
```

Expected: 6 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/services/__init__.py nnunetv2/gui/services/images.py nnunetv2/tests/gui/unit/test_images_service.py
git commit -m "gui(services): NIfTI open + slice-to-PNG with bounded LRU cache"
```

---

## Task 3: `state.cases` — case discovery for a dataset (TDD)

**Files:**
- Create: `nnunetv2/gui/state/cases.py`
- Create: `nnunetv2/tests/gui/unit/test_cases_state.py`

- [ ] **Step 1: Write failing tests**

```python
# nnunetv2/tests/gui/unit/test_cases_state.py
from __future__ import annotations

from pathlib import Path

import pytest

from nnunetv2.gui.state.cases import Case, list_cases_for_dataset


def test_list_cases_empty(gui_config):
    assert list_cases_for_dataset(gui_config, "Dataset999_None") == []


def test_list_cases_basic(populated_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    cases = list_cases_for_dataset(cfg, "Dataset027_ACDC")
    assert len(cases) == 3
    case_ids = sorted(c.id for c in cases)
    assert case_ids == ["case_001", "case_002", "case_003"]
    for c in cases:
        assert len(c.channels) == 1
        assert c.label_path is not None


def test_list_cases_multimodal(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    build_dataset_raw(
        gui_paths["raw"], dataset_id=42, name="BraTS",
        case_ids=["c1", "c2"],
        channels={"0": "T1", "1": "T1ce", "2": "T2", "3": "FLAIR"},
    )
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    cases = list_cases_for_dataset(cfg, "Dataset042_BraTS")
    assert len(cases) == 2
    for c in cases:
        assert len(c.channels) == 4
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/unit/test_cases_state.py -v
```

- [ ] **Step 3: Implement `state/cases.py`**

```python
"""Case discovery for raw datasets (Dataset<XXX>_<Name>/imagesTr)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig

CHANNEL_RE = re.compile(r"^(.+)_(\d{4})\.(.+)$")


class Case(BaseModel):
    id: str
    dataset_id: str
    channels: dict[str, str]   # channel_index_str -> absolute file path
    label_path: Optional[str]


def list_cases_for_dataset(cfg: GuiConfig, dataset_id: str) -> list[Case]:
    raw_dir = Path(cfg.raw) / dataset_id
    images_tr = raw_dir / "imagesTr"
    labels_tr = raw_dir / "labelsTr"
    if not images_tr.is_dir():
        return []
    cases: dict[str, dict[str, str]] = {}
    for f in sorted(images_tr.iterdir()):
        if not f.is_file():
            continue
        m = CHANNEL_RE.match(f.name)
        if not m:
            continue
        case_id = m.group(1)
        chan = m.group(2).lstrip("0") or "0"
        cases.setdefault(case_id, {})[chan] = str(f)
    out: list[Case] = []
    for case_id, channels in sorted(cases.items()):
        label = None
        if labels_tr.is_dir():
            for f in labels_tr.iterdir():
                if f.is_file() and f.name.split(".")[0] == case_id:
                    label = str(f)
                    break
        out.append(Case(id=case_id, dataset_id=dataset_id, channels=channels, label_path=label))
    return out
```

- [ ] **Step 4: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/unit/test_cases_state.py -v
```

Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/state/cases.py nnunetv2/tests/gui/unit/test_cases_state.py
git commit -m "gui(state): Case model + per-dataset case discovery"
```

---

## Task 4: `/api/datasets/{id}/cases` endpoint (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/datasets.py`
- Create: `nnunetv2/tests/gui/api/test_cases_api.py`

- [ ] **Step 1: Write failing tests**

```python
# nnunetv2/tests/gui/api/test_cases_api.py
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


def test_list_cases_for_known_dataset(populated_client):
    r = populated_client.get("/api/datasets/Dataset027_ACDC/cases")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert all("channels" in c for c in body)


def test_list_cases_unknown_dataset(populated_client):
    r = populated_client.get("/api/datasets/Dataset999_None/cases")
    assert r.status_code == 404


def test_list_cases_empty_dataset(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=50, name="Empty", case_ids=[])
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get(f"/api/datasets/{folder}/cases")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_cases_api.py -v
```

- [ ] **Step 3: Add `/cases` route to `routers/datasets.py`**

Inside `make_router()`, after the fingerprint endpoint:

```python
    @router.get("/{dataset_id}/cases", response_model=list[Case])
    def get_cases(dataset_id: str, request: Request) -> list[Case]:
        cfg = request.app.state.gui_config
        if get_dataset(cfg, dataset_id) is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        return list_cases_for_dataset(cfg, dataset_id)
```

Add imports at the top of the file:

```python
from nnunetv2.gui.state.cases import Case, list_cases_for_dataset
```

- [ ] **Step 4: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/api/test_cases_api.py -v
```

Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/gui/routers/datasets.py nnunetv2/tests/gui/api/test_cases_api.py
git commit -m "gui(api): /api/datasets/{id}/cases endpoint"
```

---

## Task 5: `/api/datasets/{id}/cases/{case}/preview` PNG endpoint (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/datasets.py`
- Modify: `nnunetv2/tests/gui/api/test_cases_api.py`
- Modify: `nnunetv2/tests/gui/conftest.py` (add a "populated_nifti_paths" fixture that actually puts a real NIfTI on disk for one case)

- [ ] **Step 1: Add fixture with real NIfTI files**

Append to `nnunetv2/tests/gui/conftest.py`:

```python
@pytest.fixture
def populated_nifti_paths(gui_paths):
    """Like populated_paths but writes real NIfTI bytes for one case."""
    from nnunetv2.tests.gui.fixtures.builders import (
        build_dataset_raw, build_dataset_preprocessed, build_run, build_case_nifti,
    )
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=27, name="ACDC",
                                case_ids=["case_001"])
    build_dataset_preprocessed(gui_paths["preprocessed"], dataset_folder=folder)
    build_run(gui_paths["results"], dataset_folder=folder, configuration="3d_fullres", fold="0")
    # Replace the empty touched files with real NIfTI
    images_tr = gui_paths["raw"] / folder / "imagesTr"
    labels_tr = gui_paths["raw"] / folder / "labelsTr"
    (images_tr / "case_001_0000.nii.gz").unlink()
    (labels_tr / "case_001.nii.gz").unlink()
    build_case_nifti(images_tr, "case_001_0000.nii.gz", shape=(8, 16, 16))
    build_case_nifti(labels_tr, "case_001.nii.gz", shape=(8, 16, 16))
    return gui_paths
```

- [ ] **Step 2: Append failing tests**

Append to `nnunetv2/tests/gui/api/test_cases_api.py`:

```python
@pytest.fixture
def nifti_client(populated_nifti_paths, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", str(populated_nifti_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_nifti_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_nifti_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_preview_returns_png(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/preview?axis=0&slice=4&channel=0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_unknown_case(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_999/preview?axis=0&slice=0")
    assert r.status_code == 404


def test_preview_unknown_channel(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/preview?axis=0&slice=0&channel=9")
    assert r.status_code == 404


def test_labels_returns_png(nifti_client):
    r = nifti_client.get("/api/datasets/Dataset027_ACDC/cases/case_001/labels?axis=0&slice=4")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_labels_for_case_without_label(gui_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_dataset_raw, build_case_nifti
    folder = build_dataset_raw(gui_paths["raw"], dataset_id=60, name="NoLabel",
                                case_ids=["c1"])
    # Remove the label file the builder created
    (gui_paths["raw"] / folder / "labelsTr" / "c1.nii.gz").unlink()
    build_case_nifti(gui_paths["raw"] / folder / "imagesTr", "c1_0000.nii.gz")
    (gui_paths["raw"] / folder / "imagesTr" / "c1_0000.nii.gz").exists()
    monkeypatch.setenv("nnUNet_raw", str(gui_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(gui_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(gui_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))
    r = c.get(f"/api/datasets/{folder}/cases/c1/labels?axis=0&slice=0")
    assert r.status_code == 404
```

- [ ] **Step 3: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_cases_api.py -v
```

- [ ] **Step 4: Add `preview` and `labels` routes**

Inside `routers/datasets.py` `make_router()`:

```python
    @router.get("/{dataset_id}/cases/{case_id}/preview")
    def case_preview(
        dataset_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0, channel: int = 0,
        window_lo: Optional[float] = None, window_hi: Optional[float] = None,
    ) -> Response:
        cfg = request.app.state.gui_config
        cases = list_cases_for_dataset(cfg, dataset_id)
        match = next((c for c in cases if c.id == case_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
        chan_key = str(channel)
        if chan_key not in match.channels:
            raise HTTPException(status_code=404, detail=f"Channel {channel} not found")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        png = get_slice_png_cached(match.channels[chan_key], axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")

    @router.get("/{dataset_id}/cases/{case_id}/labels")
    def case_labels(
        dataset_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0,
    ) -> Response:
        cfg = request.app.state.gui_config
        cases = list_cases_for_dataset(cfg, dataset_id)
        match = next((c for c in cases if c.id == case_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
        if not match.label_path:
            raise HTTPException(status_code=404, detail=f"No label for case {case_id!r}")
        png = get_slice_png_cached(match.label_path, axis=axis, index=slice, window=None)
        return Response(content=png, media_type="image/png")
```

Add imports at top of file:

```python
from typing import Optional
from fastapi import Response
from nnunetv2.gui.services.images import get_slice_png_cached
```

- [ ] **Step 5: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/api/test_cases_api.py -v
```

Expected: 8 passes (3 from Task 4 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/datasets.py nnunetv2/tests/gui/api/test_cases_api.py nnunetv2/tests/gui/conftest.py
git commit -m "gui(api): case preview + labels PNG endpoints with axis/slice/channel/window"
```

---

## Task 6: `/api/runs/{run_id}/predictions` listing (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/runs.py`
- Create: `nnunetv2/tests/gui/api/test_predictions_api.py`
- Modify: `nnunetv2/tests/gui/fixtures/builders.py` (add `build_run_predictions(...)`)

- [ ] **Step 1: Builder helper**

Append to `nnunetv2/tests/gui/fixtures/builders.py`:

```python
def build_run_predictions(
    fold_dir: Path,
    *,
    case_ids: Iterable[str] = ("case_001",),
    use_real_nifti: bool = False,
) -> Path:
    """Create a fold_<n>/predictions/ directory with one .nii.gz per case_id."""
    pred_dir = fold_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        path = pred_dir / f"{cid}.nii.gz"
        if use_real_nifti:
            build_case_nifti(pred_dir, f"{cid}.nii.gz", shape=(8, 16, 16))
        else:
            path.touch()
    return pred_dir
```

- [ ] **Step 2: Write failing tests**

```python
# nnunetv2/tests/gui/api/test_predictions_api.py
from __future__ import annotations

import pytest


@pytest.fixture
def predictions_client(populated_nifti_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_run_predictions
    fold_dir = (populated_nifti_paths["results"]
                / "Dataset027_ACDC" / "nnUNetPlans__nnUNetTrainer__3d_fullres" / "fold_0")
    build_run_predictions(fold_dir, case_ids=["case_001"], use_real_nifti=True)
    monkeypatch.setenv("nnUNet_raw", str(populated_nifti_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_nifti_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_nifti_paths["results"]))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    return TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))


def test_list_predictions_empty_run(populated_client):
    # No predictions/ dir on fold_0
    r = populated_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    assert r.json() == []


def test_list_predictions_populated(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == "case_001"


def test_prediction_preview(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_001?axis=0&slice=4"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_prediction_preview_unknown_case(predictions_client):
    r = predictions_client.get(
        "/api/runs/Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0/predictions/case_999?axis=0&slice=0"
    )
    assert r.status_code == 404


def test_predictions_on_unknown_run(client):
    r = client.get("/api/runs/Dataset999_X/x__y__z/fold_0/predictions")
    assert r.status_code == 404
```

(The fixture `populated_client` was added in Task 4's test file — reuse via conftest or inline. To avoid duplication, move both fixtures into `conftest.py` as `populated_client` and `predictions_client`. The exact placement is up to the implementer; just keep both files importable.)

- [ ] **Step 3: Run; confirm fail**

```bash
pytest nnunetv2/tests/gui/api/test_predictions_api.py -v
```

- [ ] **Step 4: Implement endpoints on `routers/runs.py`**

Inside `make_router()`, after `get_one`:

```python
    @router.get("/{run_id:path}/predictions")
    def list_predictions(run_id: str, request: Request) -> list[dict]:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        pred_dir = Path(run.output_folder) / "predictions"
        if not pred_dir.is_dir():
            return []
        out: list[dict] = []
        for f in sorted(pred_dir.iterdir()):
            if not f.is_file():
                continue
            stem = f.name.split(".")[0]
            out.append({"case_id": stem, "path": str(f)})
        return out

    @router.get("/{run_id:path}/predictions/{case_id}")
    def prediction_preview(
        run_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0,
        window_lo: Optional[float] = None, window_hi: Optional[float] = None,
    ) -> Response:
        cfg = request.app.state.gui_config
        run = get_run(cfg, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        pred_dir = Path(run.output_folder) / "predictions"
        # Find the file with matching stem
        match = None
        if pred_dir.is_dir():
            for f in pred_dir.iterdir():
                if f.is_file() and f.name.split(".")[0] == case_id:
                    match = f
                    break
        if match is None:
            raise HTTPException(status_code=404, detail=f"No prediction for {case_id!r}")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        png = get_slice_png_cached(str(match), axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")
```

Add imports at top of file:

```python
from pathlib import Path
from fastapi import Response
from nnunetv2.gui.services.images import get_slice_png_cached
```

**Note:** the `:path` converter on `/{run_id:path}/predictions` will greedily match — FastAPI evaluates routes in declaration order, so make sure `predictions` and `predictions/{case_id}` are declared *before* `/{run_id:path}` if they would otherwise conflict. In practice the trailing `/predictions` segment makes them distinct, but verify with the contract tests.

- [ ] **Step 5: Run; confirm pass**

```bash
pytest nnunetv2/tests/gui/api/test_predictions_api.py -v
```

Expected: 5 passes.

- [ ] **Step 6: Commit**

```bash
git add nnunetv2/gui/routers/runs.py nnunetv2/tests/gui/fixtures/builders.py nnunetv2/tests/gui/api/test_predictions_api.py nnunetv2/tests/gui/conftest.py
git commit -m "gui(api): /api/runs/{id}/predictions list + per-case PNG preview"
```

---

## Task 7: Frontend types + API helpers + cases store

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/stores/cases.ts`

- [ ] **Step 1: Add to `types.ts`**

```ts
export interface Case {
  id: string;
  dataset_id: string;
  channels: Record<string, string>;
  label_path: string | null;
}

export interface Prediction {
  case_id: string;
  path: string;
}
```

- [ ] **Step 2: Add to `api.ts`**

```ts
// Append after existing endpoints:
import type { Case, Prediction } from './types';

export const imageEndpoints = {
  getCases: (datasetId: string): Promise<Case[]> =>
    api.get<Case[]>(`/api/datasets/${encodeURIComponent(datasetId)}/cases`),

  getCasePreviewUrl: (
    datasetId: string, caseId: string,
    opts: { axis: number; slice: number; channel: number; window?: [number, number] },
  ): string => {
    const q = new URLSearchParams({
      axis: String(opts.axis),
      slice: String(opts.slice),
      channel: String(opts.channel),
    });
    if (opts.window) {
      q.set('window_lo', String(opts.window[0]));
      q.set('window_hi', String(opts.window[1]));
    }
    return `/api/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/preview?${q}`;
  },

  getCaseLabelsUrl: (
    datasetId: string, caseId: string,
    opts: { axis: number; slice: number },
  ): string => {
    const q = new URLSearchParams({ axis: String(opts.axis), slice: String(opts.slice) });
    return `/api/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/labels?${q}`;
  },

  getPredictions: (runId: string): Promise<Prediction[]> =>
    api.get<Prediction[]>(`/api/runs/${runId}/predictions`),

  getPredictionPreviewUrl: (
    runId: string, caseId: string,
    opts: { axis: number; slice: number },
  ): string => {
    const q = new URLSearchParams({ axis: String(opts.axis), slice: String(opts.slice) });
    return `/api/runs/${runId}/predictions/${encodeURIComponent(caseId)}?${q}`;
  },
};
```

- [ ] **Step 3: Create `stores/cases.ts`**

```ts
import { imageEndpoints } from '../api';
import { ApiError } from '../api';
import type { Case } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Case[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createCasesStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();
  function emit() { for (const l of listeners) l(current); }

  return {
    get(): State { return current; },
    subscribe(l: Listener): () => void {
      listeners.add(l); l(current);
      return () => listeners.delete(l);
    },
    async load(datasetId: string): Promise<void> {
      current = { kind: 'loading' }; emit();
      try {
        current = { kind: 'loaded', data: await imageEndpoints.getCases(datasetId) };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
```

- [ ] **Step 4: svelte-check**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/stores/cases.ts
git commit -m "gui(frontend): types + image/prediction endpoints + cases store"
```

---

## Task 8: `NiiVueViewer` + `Canvas2DViewer` components

**Files:**
- Create: `frontend/src/lib/viewer/NiiVueViewer.svelte`
- Create: `frontend/src/lib/viewer/Canvas2DViewer.svelte`
- Create: `frontend/src/lib/viewer/NiiVueViewer.test.ts`

- [ ] **Step 1: Write a lightweight failing test**

The full WebGL surface of NiiVue is not testable in jsdom. We instead test that the component mounts and instantiates the mocked Niivue class with the right volume URLs.

```ts
// frontend/src/lib/viewer/NiiVueViewer.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock @niivue/niivue before importing the component
const loadVolumes = vi.fn(async () => undefined);
const setOpacity = vi.fn();
const NiivueMock = vi.fn().mockImplementation(() => ({
  attachToCanvas: vi.fn(),
  loadVolumes,
  setOpacity,
  setSliceType: vi.fn(),
  setVolume: vi.fn(),
}));
vi.mock('@niivue/niivue', () => ({ Niivue: NiivueMock }));

import { render } from '@testing-library/svelte';
import NiiVueViewer from './NiiVueViewer.svelte';

describe('NiiVueViewer', () => {
  beforeEach(() => {
    NiivueMock.mockClear();
    loadVolumes.mockClear();
  });

  it('instantiates Niivue and loads the volume URL', async () => {
    render(NiiVueViewer, { props: { volumeUrl: '/api/volume.nii.gz' } });
    // Wait one tick for onMount
    await new Promise((r) => setTimeout(r, 0));
    expect(NiivueMock).toHaveBeenCalledTimes(1);
    expect(loadVolumes).toHaveBeenCalledWith([
      expect.objectContaining({ url: '/api/volume.nii.gz' }),
    ]);
  });

  it('also loads overlay when provided', async () => {
    render(NiiVueViewer, {
      props: { volumeUrl: '/api/v.nii.gz', overlayUrl: '/api/o.nii.gz' },
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(loadVolumes).toHaveBeenCalledWith([
      expect.objectContaining({ url: '/api/v.nii.gz' }),
      expect.objectContaining({ url: '/api/o.nii.gz' }),
    ]);
  });
});
```

Add `@testing-library/svelte` as a dev dep if not yet present:

```bash
cd frontend && npm install --save-dev @testing-library/svelte
```

- [ ] **Step 2: Confirm failure**

```bash
cd frontend && npm test -- viewer
```

- [ ] **Step 3: Implement `NiiVueViewer.svelte`**

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Niivue } from '@niivue/niivue';

  let {
    volumeUrl,
    overlayUrl = undefined,
    overlayOpacity = 0.5,
    axis = 0,
    slice = undefined as number | undefined,
  }: {
    volumeUrl: string;
    overlayUrl?: string;
    overlayOpacity?: number;
    axis?: number;
    slice?: number;
  } = $props();

  let canvas: HTMLCanvasElement | undefined;
  let nv: ReturnType<typeof Niivue.prototype.constructor> | null = null;

  onMount(async () => {
    if (!canvas) return;
    nv = new Niivue({ logLevel: 'warn' });
    nv.attachToCanvas(canvas);
    const volumes: { url: string; opacity?: number }[] = [{ url: volumeUrl }];
    if (overlayUrl) volumes.push({ url: overlayUrl, opacity: overlayOpacity });
    await nv.loadVolumes(volumes);
    nv.setSliceType(axis);
  });

  $effect(() => {
    if (!nv) return;
    nv.setSliceType(axis);
    if (overlayUrl) nv.setOpacity(1, overlayOpacity);
  });

  onDestroy(() => {
    // NiiVue does not expose a tidy dispose; let GC handle it after canvas detach.
    nv = null;
  });
</script>

<div class="w-full h-[480px] bg-bg-soft border border-border-soft rounded">
  <canvas bind:this={canvas} class="w-full h-full block"></canvas>
</div>
```

- [ ] **Step 4: Implement `Canvas2DViewer.svelte` (fallback)**

```svelte
<script lang="ts">
  let { src, alt = 'preview' }: { src: string; alt?: string } = $props();
</script>

<div class="w-full bg-bg-soft border border-border-soft rounded p-2 flex items-center justify-center">
  <img {src} {alt} class="max-w-full max-h-[480px] object-contain" />
</div>
```

- [ ] **Step 5: Run; confirm pass**

```bash
cd frontend && npm test -- viewer
```

Expected: 2 passes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/viewer/NiiVueViewer.svelte frontend/src/lib/viewer/Canvas2DViewer.svelte frontend/src/lib/viewer/NiiVueViewer.test.ts frontend/package.json frontend/package-lock.json
git commit -m "gui(frontend): NiiVueViewer + Canvas2DViewer fallback components"
```

---

## Task 9: `CasesList` + `CaseViewer` + DatasetDetail wiring

**Files:**
- Create: `frontend/src/components/CasesList.svelte`
- Create: `frontend/src/components/CaseViewer.svelte`
- Modify: `frontend/src/components/DatasetDetail.svelte`

- [ ] **Step 1: `CasesList.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createCasesStore } from '../lib/stores/cases';
  import type { Case } from '../lib/types';

  let { datasetId, selectedId, onSelect }: {
    datasetId: string;
    selectedId: string | null;
    onSelect: (c: Case) => void;
  } = $props();

  const cases = createCasesStore();
  let state = $state(cases.get());

  onMount(() => {
    const unsub = cases.subscribe((s) => (state = s));
    cases.load(datasetId);
    return unsub;
  });

  $effect(() => { cases.load(datasetId); });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 px-2 py-1">Cases</h4>
  {#if state.kind === 'loading' || state.kind === 'idle'}
    <p class="px-2 py-1 text-xs text-slate-500">Loading…</p>
  {:else if state.kind === 'error'}
    <p class="px-2 py-1 text-xs text-err">{state.error.message}</p>
  {:else if state.data.length === 0}
    <p class="px-2 py-1 text-xs text-slate-500">No cases (imagesTr/ empty)</p>
  {:else}
    <ul class="text-xs max-h-80 overflow-auto">
      {#each state.data as c}
        <li>
          <button
            class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
            class:text-accent={c.id === selectedId}
            class:text-slate-300={c.id !== selectedId}
            onclick={() => onSelect(c)}
          >
            {c.id} <span class="text-slate-500">· {Object.keys(c.channels).length}ch{c.label_path ? ' · GT' : ''}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
```

- [ ] **Step 2: `CaseViewer.svelte`**

```svelte
<script lang="ts">
  import { imageEndpoints } from '../lib/api';
  import Canvas2DViewer from '../lib/viewer/Canvas2DViewer.svelte';
  import NiiVueViewer from '../lib/viewer/NiiVueViewer.svelte';
  import type { Case } from '../lib/types';

  let { datasetId, case: caseObj }: { datasetId: string; case: Case } = $props();

  let axis = $state(0);
  let slice = $state(0);
  let channel = $state(0);
  let overlayOn = $state(false);
  let opacity = $state(0.5);
  // Phase 2 uses 2D PNG previews (fast). NiiVue full-volume rendering is wired
  // but defaults off — the server doesn't expose raw NIfTI URLs yet (Phase 6).
  let mode = $state<'png' | 'niivue'>('png');

  const channels = $derived(Object.keys(caseObj.channels).sort());

  const previewUrl = $derived(
    imageEndpoints.getCasePreviewUrl(datasetId, caseObj.id, {
      axis, slice, channel: Number(channels[channel] ?? 0),
    })
  );

  const labelUrl = $derived(
    caseObj.label_path && overlayOn
      ? imageEndpoints.getCaseLabelsUrl(datasetId, caseObj.id, { axis, slice })
      : null
  );
</script>

<div class="space-y-2">
  <div class="flex gap-2 text-xs items-center">
    <label class="text-slate-500">Axis
      <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={axis}>
        <option value={0}>Z (axial)</option>
        <option value={1}>Y (coronal)</option>
        <option value={2}>X (sagittal)</option>
      </select>
    </label>
    <label class="text-slate-500">Channel
      <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={channel}>
        {#each channels as ch, i}<option value={i}>{ch}</option>{/each}
      </select>
    </label>
    <label class="text-slate-500 flex-1 flex items-center gap-2">Slice
      <input type="range" min="0" max="255" bind:value={slice} class="flex-1" />
      <span class="w-8 text-right text-slate-400">{slice}</span>
    </label>
    {#if caseObj.label_path}
      <label class="text-slate-500 flex items-center gap-1">
        <input type="checkbox" bind:checked={overlayOn} /> Overlay
      </label>
      {#if overlayOn}
        <label class="text-slate-500 flex items-center gap-1">Opacity
          <input type="range" min="0" max="1" step="0.05" bind:value={opacity} />
        </label>
      {/if}
    {/if}
  </div>

  {#if mode === 'png'}
    <Canvas2DViewer src={previewUrl} alt={caseObj.id} />
    {#if labelUrl}
      <p class="text-[10px] text-slate-500">Overlay PNG: <code>{labelUrl}</code></p>
    {/if}
  {:else}
    <NiiVueViewer volumeUrl={previewUrl} overlayUrl={labelUrl ?? undefined} overlayOpacity={opacity} {axis} {slice} />
  {/if}
</div>
```

- [ ] **Step 3: Replace the Cases-tab placeholder in `DatasetDetail.svelte`**

Inside the existing `{#if tab === 'cases'}` branch, replace `<p>Phase 2 placeholder…</p>` with:

```svelte
{#if tab === 'cases'}
  <div class="flex gap-3">
    <div class="w-56 flex-shrink-0">
      <CasesList datasetId={state.data.id} selectedId={selectedCase?.id ?? null} onSelect={(c) => (selectedCase = c)} />
    </div>
    <div class="flex-1 min-w-0">
      {#if selectedCase}
        <CaseViewer datasetId={state.data.id} case={selectedCase} />
      {:else}
        <p class="text-sm text-slate-400">Pick a case on the left.</p>
      {/if}
    </div>
  </div>
```

Also add imports at the top of the script block:

```svelte
import CasesList from './CasesList.svelte';
import CaseViewer from './CaseViewer.svelte';
import type { Case } from '../lib/types';

let selectedCase = $state<Case | null>(null);
```

- [ ] **Step 4: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CasesList.svelte frontend/src/components/CaseViewer.svelte frontend/src/components/DatasetDetail.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Cases tab with list + per-case viewer (PNG slice mode)"
```

---

## Task 10: `PredictionList` + `RunDetail` + Monitor route layout

**Files:**
- Create: `frontend/src/components/PredictionList.svelte`
- Create: `frontend/src/components/RunDetail.svelte`
- Modify: `frontend/src/routes/Monitor.svelte`
- Modify: `frontend/src/components/RunsTable.svelte` (emit a `select` event)

- [ ] **Step 1: Allow RunsTable to emit selection**

In `RunsTable.svelte`, change the props block to also accept `onSelect`:

```svelte
let { filter = {} as RunFilter, onSelect }: { filter?: RunFilter; onSelect?: (r: Run) => void } = $props();
```

And wrap each row in a clickable button or add `onclick={() => onSelect?.(r)}` on the `<tr>`. Highlight selected by tracking `selectedId` via prop or local state — keep the implementation simple; just make rows clickable and bubble the event.

- [ ] **Step 2: `PredictionList.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { imageEndpoints } from '../lib/api';
  import Canvas2DViewer from '../lib/viewer/Canvas2DViewer.svelte';
  import type { Prediction } from '../lib/types';

  let { runId }: { runId: string } = $props();
  let preds = $state<Prediction[]>([]);
  let selected = $state<Prediction | null>(null);
  let axis = $state(0);
  let slice = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function load() {
    loading = true; error = null;
    try {
      preds = await imageEndpoints.getPredictions(runId);
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  onMount(() => { load(); });
  $effect(() => { load(); });

  const previewUrl = $derived(
    selected ? imageEndpoints.getPredictionPreviewUrl(runId, selected.case_id, { axis, slice }) : null
  );
</script>

<div class="space-y-2">
  <h4 class="text-xs uppercase tracking-wider text-slate-500">Predictions</h4>
  {#if loading}
    <p class="text-xs text-slate-500">Loading…</p>
  {:else if error}
    <p class="text-xs text-err">{error}</p>
  {:else if preds.length === 0}
    <p class="text-xs text-slate-500">No predictions on disk for this run yet. (Phase 4 will let you launch predict from the GUI.)</p>
  {:else}
    <div class="flex gap-3">
      <ul class="text-xs w-48">
        {#each preds as p}
          <li>
            <button
              class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
              class:text-accent={selected?.case_id === p.case_id}
              class:text-slate-300={selected?.case_id !== p.case_id}
              onclick={() => (selected = p)}
            >
              {p.case_id}
            </button>
          </li>
        {/each}
      </ul>
      <div class="flex-1 min-w-0">
        {#if selected && previewUrl}
          <div class="flex gap-2 text-xs items-center mb-2">
            <label>Axis <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5" bind:value={axis}>
              <option value={0}>Z</option><option value={1}>Y</option><option value={2}>X</option>
            </select></label>
            <label class="flex-1 flex items-center gap-2">Slice
              <input type="range" min="0" max="255" bind:value={slice} class="flex-1" />
              <span class="w-8 text-right">{slice}</span>
            </label>
          </div>
          <Canvas2DViewer src={previewUrl} alt={selected.case_id} />
        {:else}
          <p class="text-xs text-slate-500">Pick a case to preview.</p>
        {/if}
      </div>
    </div>
  {/if}
</div>
```

- [ ] **Step 3: `RunDetail.svelte`**

```svelte
<script lang="ts">
  import PredictionList from './PredictionList.svelte';
  import type { Run } from '../lib/types';

  let { run }: { run: Run } = $props();
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
  <div class="flex items-center gap-2 text-xs">
    <strong class="text-slate-100">{run.dataset_id}</strong>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">{run.plans_name} · {run.trainer_name} · {run.configuration}</span>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">fold_{run.fold}</span>
    <span class="ml-auto text-xs" class:text-ok={run.status === 'completed'} class:text-slate-500={run.status !== 'completed'}>
      {run.status}
    </span>
  </div>
  <p class="text-[10px] text-slate-600 mt-1">Live curves / log / image samples land in Phase 3.</p>
</div>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <PredictionList runId={run.id} />
</div>
```

- [ ] **Step 4: Update Monitor route**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import RunsTable from '../components/RunsTable.svelte';
  import RunDetail from '../components/RunDetail.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Run, RunFilter } from '../lib/types';

  const ws = createWorkspaceStore();
  let workspaceId = $state<string | null>(ws.get());
  onMount(() => ws.subscribe((v) => (workspaceId = v)));
  let filter = $derived<RunFilter>(workspaceId ? { dataset_id: workspaceId } : {});

  let selected = $state<Run | null>(null);
</script>

<h2 class="text-lg font-semibold text-slate-100">Monitor</h2>
<p class="text-xs text-amber-400 mt-1">Live curves + log tail land in Phase 3. Phase 2 adds prediction review for completed runs.</p>

<div class="mt-4 grid grid-cols-12 gap-3">
  <div class="col-span-7 min-w-0">
    <RunsTable {filter} onSelect={(r) => (selected = r)} />
  </div>
  <div class="col-span-5 min-w-0">
    {#if selected}
      <RunDetail run={selected} />
    {:else}
      <p class="text-xs text-slate-500">Pick a run on the left to inspect predictions.</p>
    {/if}
  </div>
</div>
```

- [ ] **Step 5: svelte-check + build**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PredictionList.svelte frontend/src/components/RunDetail.svelte frontend/src/components/RunsTable.svelte frontend/src/routes/Monitor.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): RunDetail + PredictionList — case preview for completed runs"
```

---

## Task 11: Check in `tiny.nii.gz` fixture + smoke + docs

**Files:**
- Create: `nnunetv2/tests/gui/fixtures/data/__init__.py`
- Create: `nnunetv2/tests/gui/fixtures/data/tiny.nii.gz` (≈4 KB, binary)
- Create: `nnunetv2/tests/gui/api/test_image_viewer_smoke.py`
- Modify: `documentation/gui.md`

- [ ] **Step 1: Generate the fixture once and commit**

```bash
python -c "
from pathlib import Path
from nnunetv2.tests.gui.fixtures.builders import build_case_nifti
out = Path('nnunetv2/tests/gui/fixtures/data')
out.mkdir(parents=True, exist_ok=True)
build_case_nifti(out, 'tiny.nii.gz', shape=(8, 16, 16))
print(out / 'tiny.nii.gz')
"
ls -lh nnunetv2/tests/gui/fixtures/data/tiny.nii.gz
```

This should produce a ≈3-5 KB file. Add an `__init__.py` next to it (empty) so Python treats it as a package and `pkg_resources` style lookup works.

- [ ] **Step 2: Write a smoke test that round-trips the fixture through the API**

```python
# nnunetv2/tests/gui/api/test_image_viewer_smoke.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def test_full_pipeline_smoke(tmp_path, monkeypatch):
    """End-to-end: real NIfTI on disk → /api/datasets/.../cases/.../preview → PNG."""
    raw = tmp_path / "raw"; pre = tmp_path / "pre"; res = tmp_path / "res"
    for p in (raw, pre, res): p.mkdir()

    fixture = Path(__file__).parent.parent / "fixtures" / "data" / "tiny.nii.gz"
    ds = raw / "Dataset100_Tiny"
    (ds / "imagesTr").mkdir(parents=True)
    (ds / "labelsTr").mkdir(parents=True)
    shutil.copy(fixture, ds / "imagesTr" / "case_a_0000.nii.gz")
    shutil.copy(fixture, ds / "labelsTr" / "case_a.nii.gz")
    (ds / "dataset.json").write_text('{"channel_names": {"0": "CT"}, "labels": {"background": 0, "fg": 1}, "numTraining": 1, "file_ending": ".nii.gz"}')

    monkeypatch.setenv("nnUNet_raw", str(raw))
    monkeypatch.setenv("nnUNet_preprocessed", str(pre))
    monkeypatch.setenv("nnUNet_results", str(res))
    from fastapi.testclient import TestClient
    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app
    c = TestClient(create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)))

    r = c.get("/api/datasets/Dataset100_Tiny/cases")
    assert r.status_code == 200 and len(r.json()) == 1

    r = c.get("/api/datasets/Dataset100_Tiny/cases/case_a/preview?axis=0&slice=4&channel=0")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    r = c.get("/api/datasets/Dataset100_Tiny/cases/case_a/labels?axis=0&slice=4")
    assert r.status_code == 200
```

- [ ] **Step 3: Run; full suite green**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && cd ..
```

- [ ] **Step 4: Update `documentation/gui.md`**

Mark Phase 2 done in the Roadmap and append to "What you can do today":

```markdown
2. **Image viewer** ✓ — NiiVue + PNG slice preview, case browser per dataset, prediction review per run.
```

- [ ] **Step 5: Commit**

```bash
git add nnunetv2/tests/gui/fixtures/data/ nnunetv2/tests/gui/api/test_image_viewer_smoke.py documentation/gui.md
git commit -m "gui(tests+docs): tiny.nii.gz fixture + end-to-end smoke + Phase 2 roadmap mark"
```

---

## Task 12: PR / CI gate

- [ ] **Step 1: `pytest nnunetv2/tests/gui/`** — all green, expected total ≈ 80 tests (Phase 1 ≈ 60 + ≈ 20 new).
- [ ] **Step 2: `cd frontend && npm test`** — all green.
- [ ] **Step 3: `cd frontend && npx svelte-check`** — 0 errors.
- [ ] **Step 4: Boot `nnUNetv2_gui` against `$nnUNet_raw` containing a real dataset; manually:**
  - Open Datasets → pick a dataset → Cases tab → confirm list populates and a slice preview renders.
  - Open Monitor → pick a completed run → confirm prediction list renders (or "No predictions" if none on disk).

- [ ] **Step 5: Push branch, open PR, ensure GitHub Actions `gui` workflow stays green.**

---

## Done condition

Phase 2 is complete when:

- [ ] All gui pytest tests pass on host + clean env.
- [ ] All frontend vitest tests pass.
- [ ] svelte-check is 0 errors.
- [ ] Real NIfTI files render in the Datasets → Cases tab (axis switch + slice scrubber work).
- [ ] Prediction PNG previews render for a run that has a `predictions/` folder.
- [ ] LRU cache stays bounded at 256 entries (verified by `test_lru_cache_bounded`).
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 2 completion.

Then move on to Phase 3 (Live monitoring — TB tailer, SSE, Monitor curves + log + image samples).
