# nnU-Net GUI — Phase 4 (Job Launching) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This phase has the trickiest state machine in the entire GUI build — read the "State machine, locking, and re-attach" section before opening Task 1.

**Goal:** Pure-GUI workflow end-to-end. The browser can launch `nnUNetv2_plan_and_preprocess`, `nnUNetv2_train`, and `nnUNetv2_predict`. Multiple folds queue serially. Stop sends SIGTERM (then SIGKILL after grace). The server can restart without killing the launched processes; on boot it re-attaches by probing PIDs. The Jobs page gains stop/cancel/restart actions.

**Architecture:** A `jobs/launcher.py` module owns `subprocess.Popen` with `start_new_session=True` (Linux/macOS) or `creationflags=CREATE_NEW_PROCESS_GROUP` (Windows). A `jobs/reaper.py` background task supervises each Popen, awaiting its `wait()` from a thread executor and writing the terminal state to SQLite. A `jobs/queue.py` runs **serial v1** — exactly one running job per `(kind, output_run_id)` queue slot; queued jobs become `running` only when the previous finishes. `services/cli_renderer.py` turns Pydantic form payloads into the equivalent `nnUNetv2_*` CLI string for both preview and execution. Pydantic models live next to repo functions; routers `preprocess.py`, `train.py`, `predict.py` are thin form-validation layers. The existing read-only `jobs.py` router gains write actions: `POST /api/jobs/{id}/stop`, `POST /api/jobs/{id}/restart`, `POST /api/jobs/{id}/cancel` (queued only). A `/api/system/gpu` endpoint reports `pynvml` data when available, degrading to an empty list.

### State machine, locking, and re-attach

State machine (already declared in spec):

```
   POST → queued
   queued → starting → running
   running → completed (exit 0)
   running → failed (exit != 0)
   running → killed (POST /stop)
   queued → cancelled (POST /cancel)
   any non-terminal → unknown (server boot, PID gone but no terminal state)
```

**Locking model** (matters for correctness):
- Each queue is keyed by a `slot` string (default: `"global"` — serial v1 means everything queues on the same global slot). Future phases can shard by `(dataset_id, fold)` etc., but for v1 we keep it simple.
- The reaper holds a single global `asyncio.Lock` while transitioning a job out of `running` so the queue advance is atomic with status update.
- The launcher acquires the same lock while flipping `starting → running` and stashing PID/PGID. Two simultaneous POSTs cannot both promote to running; the second waits.
- The SQLite layer is single-writer (FastAPI server), so the lock is purely intra-process — no SQLite lock contention.

**Re-attach on server boot:** `reaper.attach_on_boot(cfg)` scans `job WHERE status IN ('queued','starting','running')`. For each:
1. `queued`: leave as-is; queue picks them up.
2. `starting` or `running` with non-null `pid`: probe with `os.kill(pgid, 0)` (signal 0 = check existence).
   - If alive → spawn a fresh reaper coroutine that calls `os.waitpid(pid, 0)` (Linux) or `psutil.Process(pid).wait()` cross-platform; resume tailing the log file.
   - If dead → if a `checkpoint_final.pth` (training) or output folder content (predict) exists, mark `completed`; otherwise `unknown` and require the user to reconcile from the Jobs page.

**Tech Stack:** Adds Python `psutil` and `pynvml` (optional — degrades to empty list if unavailable). No new frontend deps.

**Spec reference:** `docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md` → "Job lifecycle state machine", "Why one subprocess per job", and "UI Pages" → "Train" / "Predict" / "Jobs". Architectural decision: serial-only queue v1; ensembling, find_best, postproc go through the same launcher (this phase wires preprocess/train/predict; Phase 6 builds on the same launcher for the rest).

**TDD discipline:** Every transition is tested. The launcher tests use a `sleep_helper.py` test script (real subprocess, short-lived). The reaper is tested by spawning a Popen of `python -c "import time; time.sleep(0.2)"` and asserting the row transitions to `completed`. Re-attach is tested by inserting fake `running` rows with a real-but-dead PID and asserting transition to `failed` or `unknown`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `nnunetv2/gui/jobs/__init__.py` | Package marker |
| `nnunetv2/gui/jobs/launcher.py` | `spawn(cfg, kind, argv, env, log_path, output_run_id) -> Job`. Uses `start_new_session=True` on POSIX or `CREATE_NEW_PROCESS_GROUP` on Windows. Returns the persisted `Job` with PID/PGID/status=running. |
| `nnunetv2/gui/jobs/reaper.py` | `run_reaper(app, job)` async coroutine — awaits process exit via thread executor, transitions row, advances queue. `attach_on_boot(app)` for restart. |
| `nnunetv2/gui/jobs/queue.py` | `enqueue(cfg, kind, argv, ..., slot="global")`, `advance(slot)`, `cancel_queued(cfg, job_id)`. Holds an `asyncio.Lock` per slot at app scope. |
| `nnunetv2/gui/jobs/signals.py` | OS-specific stop helpers: `terminate(pgid)`, `kill(pgid)`. Catches `ProcessLookupError`. |
| `nnunetv2/gui/services/cli_renderer.py` | Form payload → `["nnUNetv2_train", "27", "3d_fullres", "0", "--npz"]`. Pure function; one entry per supported CLI subcommand. |
| `nnunetv2/gui/services/gpu.py` | `gpu_info()` returns `[{index, name, memory_total_mb, memory_used_mb, util_pct}]` via `pynvml`. Returns `[]` if pynvml missing. |
| `nnunetv2/gui/routers/preprocess.py` | `POST /api/preprocess` — Pydantic body → enqueue + spawn |
| `nnunetv2/gui/routers/train.py` | `POST /api/train` — multi-fold expansion → N queued jobs (one per fold) |
| `nnunetv2/gui/routers/predict.py` | `POST /api/predict` — enqueue + spawn |
| `nnunetv2/gui/routers/jobs.py` (mod) | Add `POST /{id}/stop`, `POST /{id}/cancel`, `POST /{id}/restart` |
| `nnunetv2/gui/routers/system.py` (mod) | Add `GET /api/system/gpu` |
| `nnunetv2/gui/server.py` (mod) | Add startup hook: `attach_on_boot`, mount `app.state.queue_locks`; shutdown hook: cancel reaper tasks (but **never** terminate the subprocesses themselves) |
| `nnunetv2/gui/state/jobs.py` (mod) | Add `list_active_pids(cfg)`, `list_queued(cfg, slot)`, `set_status_running(cfg, job_id, pid, pgid)` convenience writers |
| `nnunetv2/tests/gui/unit/test_cli_renderer.py` | Pure-function tests per subcommand |
| `nnunetv2/tests/gui/unit/test_launcher.py` | Launcher round-trip with a tiny `sleep_helper.py` script |
| `nnunetv2/tests/gui/unit/test_reaper.py` | Reaper marks job completed/failed; re-attach for live-vs-dead PID |
| `nnunetv2/tests/gui/unit/test_queue.py` | Serial-queue advance correctness |
| `nnunetv2/tests/gui/unit/test_signals.py` | terminate + kill flow with a short subprocess |
| `nnunetv2/tests/gui/api/test_preprocess_api.py` | Form contract + dry-run argv check |
| `nnunetv2/tests/gui/api/test_train_api.py` | Multi-fold expansion; CLI preview equivalence |
| `nnunetv2/tests/gui/api/test_predict_api.py` | Form contract + envelope errors |
| `nnunetv2/tests/gui/api/test_jobs_actions.py` | Stop/cancel/restart end-to-end |
| `nnunetv2/tests/gui/api/test_gpu_api.py` | pynvml present + missing branches |
| `nnunetv2/tests/gui/helpers/sleep_helper.py` | Tiny script: `import sys, time; time.sleep(float(sys.argv[1])); sys.exit(int(sys.argv[2]))` — used as fake nnUNet command |
| `frontend/src/lib/types.ts` (mod) | `PreprocessRequest`, `TrainRequest`, `PredictRequest`, `GpuInfo` |
| `frontend/src/lib/api.ts` (mod) | `postPreprocess`, `postTrain`, `postPredict`, `stopJob`, `cancelJob`, `restartJob`, `getGpuInfo`, `previewCli` (optional helper) |
| `frontend/src/lib/forms/CliPreview.svelte` | Renders the equivalent CLI string with a copy button |
| `frontend/src/lib/forms/PreprocessForm.svelte` | Dataset picker, planner dropdown, flags. Submits, then navigates to Monitor for the resulting job. |
| `frontend/src/lib/forms/TrainForm.svelte` | Dataset/config/plans/trainer/folds-chips/GPU count/pretrained-path/flags. GPU contention warning. |
| `frontend/src/lib/forms/PredictForm.svelte` | Input folder, output folder, dataset, configuration, folds chips (`all` = ensemble), checkpoint, step size, `--disable_tta`, `--save_probabilities`, `-c`, device. |
| `frontend/src/components/JobActionsCell.svelte` | Stop/cancel/restart buttons; only enabled for valid states |
| `frontend/src/components/JobsTable.svelte` (mod) | Wire JobActionsCell; auto-refresh after action |
| `frontend/src/routes/Train.svelte` (mod) | Replace stub with `<TrainForm>` + right rail queue |
| `frontend/src/routes/Predict.svelte` (mod) | Replace stub with `<PredictForm>` + per-case review pane from Phase 2 |
| `frontend/src/components/PreprocessLauncher.svelte` | Lives in the Datasets → Preprocess action button overlay |
| `frontend/src/components/DatasetDetail.svelte` (mod) | "Preprocess" action button opens `<PreprocessLauncher>` modal |
| `pyproject.toml` (mod) | Add `psutil>=5.9` and `pynvml>=11` to `[gui]` extra |

---

## Task 1: New deps + `sleep_helper.py` + `JobFilter.slot` extension (TDD)

**Files:**
- Modify: `pyproject.toml`
- Modify: `nnunetv2/gui/db.py` (add `slot` column to `job` table)
- Modify: `nnunetv2/gui/state/jobs.py`
- Create: `nnunetv2/tests/gui/helpers/__init__.py` (empty)
- Create: `nnunetv2/tests/gui/helpers/sleep_helper.py`

- [ ] **Step 1: Deps + helper script**

Add to `pyproject.toml` `[gui]`: `"psutil>=5.9"`, `"pynvml>=11"`. (Mark pynvml as actually optional — the import inside `services/gpu.py` is guarded.)

```python
# nnunetv2/tests/gui/helpers/sleep_helper.py
"""Test-only helper: sleep for N seconds, exit with given code.

Usage:  python -m nnunetv2.tests.gui.helpers.sleep_helper 0.5 0
"""
import sys
import time

if __name__ == "__main__":
    secs = float(sys.argv[1])
    code = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    time.sleep(secs)
    sys.exit(code)
```

- [ ] **Step 2: Add `slot` column**

```python
# in db.py job_table, add:
Column("slot", String, nullable=False, default="global"),
```

(SQLite will allow appending a column on a fresh DB; for existing DBs in tests, `init_db` re-creates from scratch.)

- [ ] **Step 3: Failing test for slot defaulting**

```python
# nnunetv2/tests/gui/unit/test_jobs_repo.py (append)
def test_job_default_slot_is_global(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, _make())
    assert j.slot == "global"
```

- [ ] **Step 4: Add `slot: str = "global"` to `Job` model + serialization**

```python
class Job(BaseModel):
    # ... existing fields ...
    slot: str = "global"
```

- [ ] **Step 5: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_jobs_repo.py -v
git add pyproject.toml nnunetv2/gui/db.py nnunetv2/gui/state/jobs.py nnunetv2/tests/gui/helpers/ nnunetv2/tests/gui/unit/test_jobs_repo.py
git commit -m "gui(jobs): psutil/pynvml deps, slot column, sleep_helper test fixture"
```

---

## Task 2: `services/cli_renderer.py` — form-to-argv (TDD)

**Files:**
- Modify: `nnunetv2/gui/services/cli_renderer.py`
- Create: `nnunetv2/tests/gui/unit/test_cli_renderer.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_cli_renderer.py
from __future__ import annotations

from nnunetv2.gui.services.cli_renderer import (
    PreprocessRequest, TrainRequest, PredictRequest,
    render_preprocess, render_train, render_predict, argv_to_cli_string,
)


def test_render_preprocess_minimal():
    req = PreprocessRequest(dataset_id=27, verify_dataset_integrity=True)
    argv = render_preprocess(req)
    assert argv[0] == "nnUNetv2_plan_and_preprocess"
    assert "-d" in argv and "27" in argv
    assert "--verify_dataset_integrity" in argv


def test_render_preprocess_with_planner():
    req = PreprocessRequest(dataset_id=27, planner="nnUNetPlannerResEncL")
    argv = render_preprocess(req)
    assert "-pl" in argv and "nnUNetPlannerResEncL" in argv


def test_render_train_basic():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0", npz=True)
    argv = render_train(req)
    assert argv == ["nnUNetv2_train", "27", "3d_fullres", "0", "--npz"]


def test_render_train_with_trainer_and_plans():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0",
                       trainer="nnUNetTrainerCustom", plans="nnUNetResEncUNetLPlans")
    argv = render_train(req)
    assert "-tr" in argv and "nnUNetTrainerCustom" in argv
    assert "-p" in argv and "nnUNetResEncUNetLPlans" in argv


def test_render_train_continue_flag():
    req = TrainRequest(dataset_id=27, configuration="3d_fullres", fold="0", continue_training=True)
    argv = render_train(req)
    assert "--c" in argv


def test_render_predict_minimal():
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out", folds=["all"])
    argv = render_predict(req)
    assert argv[0] == "nnUNetv2_predict"
    assert "-i" in argv and "/in" in argv
    assert "-o" in argv and "/out" in argv
    assert "-d" in argv and "27" in argv
    assert "-c" in argv and "3d_fullres" in argv
    assert "-f" in argv and "all" in argv


def test_render_predict_save_probabilities():
    req = PredictRequest(dataset_id=27, configuration="3d_fullres",
                          input_folder="/in", output_folder="/out", folds=["0", "1"],
                          save_probabilities=True, disable_tta=True)
    argv = render_predict(req)
    assert "--save_probabilities" in argv
    assert "--disable_tta" in argv
    # multi-fold: "-f 0 1" — argparse-style
    f_idx = argv.index("-f")
    assert argv[f_idx + 1 : f_idx + 3] == ["0", "1"]


def test_argv_to_cli_string_quotes_paths():
    s = argv_to_cli_string(["nnUNetv2_predict", "-i", "/a path/with space", "-o", "/o"])
    assert "'/a path/with space'" in s or '"/a path/with space"' in s
```

- [ ] **Step 2: Implement `cli_renderer.py`**

```python
# nnunetv2/gui/services/cli_renderer.py
"""Pure functions mapping Pydantic form payloads to argv lists.

These are the *only* place CLI flags are emitted, so the equivalent-CLI
preview shown in the UI is guaranteed identical to what's executed.
"""
from __future__ import annotations

import shlex
from typing import Optional

from pydantic import BaseModel, Field


class PreprocessRequest(BaseModel):
    dataset_id: int
    verify_dataset_integrity: bool = False
    planner: Optional[str] = None
    configurations: Optional[list[str]] = None  # subset of 2d/3d_fullres/3d_lowres
    no_pp: bool = False  # --no_pp
    npfp: Optional[int] = None  # num fingerprint processes
    np: Optional[int] = None    # num preprocess processes


class TrainRequest(BaseModel):
    dataset_id: int
    configuration: str
    fold: str  # '0'..'4' or 'all'
    trainer: Optional[str] = None
    plans: Optional[str] = None
    pretrained_weights: Optional[str] = None
    num_gpus: int = 1
    npz: bool = False
    continue_training: bool = False  # --c
    val_only: bool = False           # --val
    val_best: bool = False           # --val_best
    disable_checkpointing: bool = False
    device: str = "cuda"


class PredictRequest(BaseModel):
    dataset_id: int
    configuration: str
    input_folder: str
    output_folder: str
    folds: list[str] = Field(default_factory=lambda: ["all"])
    trainer: Optional[str] = None
    plans: Optional[str] = None
    checkpoint: str = "checkpoint_final"  # or 'checkpoint_best'
    step_size: float = 0.5
    disable_tta: bool = False
    save_probabilities: bool = False
    continue_prediction: bool = False  # -c
    device: str = "cuda"


def render_preprocess(req: PreprocessRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_plan_and_preprocess", "-d", str(req.dataset_id)]
    if req.verify_dataset_integrity:
        argv.append("--verify_dataset_integrity")
    if req.planner:
        argv += ["-pl", req.planner]
    if req.configurations:
        argv += ["-c"] + req.configurations
    if req.no_pp:
        argv.append("--no_pp")
    if req.npfp is not None:
        argv += ["-npfp", str(req.npfp)]
    if req.np is not None:
        argv += ["-np", str(req.np)]
    return argv


def render_train(req: TrainRequest) -> list[str]:
    argv: list[str] = ["nnUNetv2_train", str(req.dataset_id), req.configuration, req.fold]
    if req.trainer:
        argv += ["-tr", req.trainer]
    if req.plans:
        argv += ["-p", req.plans]
    if req.pretrained_weights:
        argv += ["-pretrained_weights", req.pretrained_weights]
    if req.num_gpus > 1:
        argv += ["-num_gpus", str(req.num_gpus)]
    if req.npz:
        argv.append("--npz")
    if req.continue_training:
        argv.append("--c")
    if req.val_only:
        argv.append("--val")
    if req.val_best:
        argv.append("--val_best")
    if req.disable_checkpointing:
        argv.append("--disable_checkpointing")
    if req.device != "cuda":
        argv += ["-device", req.device]
    return argv


def render_predict(req: PredictRequest) -> list[str]:
    argv: list[str] = [
        "nnUNetv2_predict",
        "-i", req.input_folder,
        "-o", req.output_folder,
        "-d", str(req.dataset_id),
        "-c", req.configuration,
        "-f", *req.folds,
    ]
    if req.trainer:
        argv += ["-tr", req.trainer]
    if req.plans:
        argv += ["-p", req.plans]
    if req.checkpoint != "checkpoint_final":
        argv += ["-chk", req.checkpoint]
    if req.step_size != 0.5:
        argv += ["-step_size", str(req.step_size)]
    if req.disable_tta:
        argv.append("--disable_tta")
    if req.save_probabilities:
        argv.append("--save_probabilities")
    if req.continue_prediction:
        argv.append("-c")
    if req.device != "cuda":
        argv += ["-device", req.device]
    return argv


def argv_to_cli_string(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)
```

- [ ] **Step 3: Run; pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_cli_renderer.py -v
git add nnunetv2/gui/services/cli_renderer.py nnunetv2/tests/gui/unit/test_cli_renderer.py
git commit -m "gui(services): pydantic-form-to-CLI-argv renderer (preprocess/train/predict)"
```

---

## Task 3: `jobs/signals.py` + `terminate` / `kill` helpers (TDD)

**Files:**
- Create: `nnunetv2/gui/jobs/__init__.py` (empty)
- Create: `nnunetv2/gui/jobs/signals.py`
- Create: `nnunetv2/tests/gui/unit/test_signals.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_signals.py
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from nnunetv2.gui.jobs.signals import terminate, kill_group


def _spawn_long_sleep() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "30"],
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def test_terminate_sends_sigterm():
    p = _spawn_long_sleep()
    pgid = os.getpgid(p.pid) if os.name == "posix" else p.pid
    terminate(pgid)
    code = p.wait(timeout=5)
    # SIGTERM exit on POSIX is -15; on Windows it's 1
    assert code is not None


def test_kill_group_sends_sigkill():
    p = _spawn_long_sleep()
    pgid = os.getpgid(p.pid) if os.name == "posix" else p.pid
    kill_group(pgid)
    code = p.wait(timeout=5)
    assert code is not None


def test_terminate_already_dead_is_noop():
    p = _spawn_long_sleep()
    p.kill(); p.wait(timeout=5)
    # Should not raise
    pgid = p.pid
    terminate(pgid)
```

- [ ] **Step 2: Implement `signals.py`**

```python
"""Cross-platform signal helpers — never raise on already-dead pgid."""
from __future__ import annotations

import os
import signal
import sys


def terminate(pgid: int) -> None:
    """SIGTERM the entire process group (POSIX) or send Ctrl-Break (Windows)."""
    try:
        if os.name == "posix":
            os.killpg(pgid, signal.SIGTERM)
        elif sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP allows sending CTRL_BREAK_EVENT to the pid
            os.kill(pgid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    except (ProcessLookupError, OSError):
        pass


def kill_group(pgid: int) -> None:
    """SIGKILL the process group; on Windows TerminateProcess via os.kill."""
    try:
        if os.name == "posix":
            os.killpg(pgid, signal.SIGKILL)
        elif sys.platform == "win32":
            os.kill(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def is_alive(pgid: int) -> bool:
    """Return True if pgid still has at least one live process."""
    if pgid <= 0:
        return False
    try:
        os.kill(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_signals.py -v
git add nnunetv2/gui/jobs/__init__.py nnunetv2/gui/jobs/signals.py nnunetv2/tests/gui/unit/test_signals.py
git commit -m "gui(jobs): signal helpers (terminate, kill_group, is_alive)"
```

---

## Task 4: `jobs/launcher.py` — spawn and persist (TDD)

**Files:**
- Create: `nnunetv2/gui/jobs/launcher.py`
- Create: `nnunetv2/tests/gui/unit/test_launcher.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_launcher.py
from __future__ import annotations

import os
import sys
import time

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.signals import is_alive
from nnunetv2.gui.state.jobs import get_job


def test_spawn_creates_running_job(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.5", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "test.log"),
                output_run_id="Dataset027_ACDC/x__y__z/fold_0")
    assert job.status == "running"
    assert job.pid is not None
    assert job.pgid is not None
    # Verify it's actually running
    assert is_alive(job.pgid)
    # Wait for it to finish naturally
    deadline = time.time() + 5
    while time.time() < deadline and is_alive(job.pgid):
        time.sleep(0.05)
    assert not is_alive(job.pgid)


def test_spawn_writes_argv_and_log_path(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]
    job = spawn(gui_config, kind="predict", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "predict.log"),
                output_run_id=None)
    fetched = get_job(gui_config, job.id)
    import json
    assert json.loads(fetched.args_json) == argv
    assert fetched.log_path == str(gui_config.results / "predict.log")


def test_spawn_creates_detached_process_group(gui_config):
    """On POSIX, the child's pgid must differ from the parent's."""
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.3", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "x.log"),
                output_run_id=None)
    if os.name == "posix":
        assert job.pgid != os.getpgrp()
```

- [ ] **Step 2: Implement `jobs/launcher.py`**

```python
"""Spawn nnUNet CLI subprocesses in their own process group, persist the job row.

The subprocess inherits a clean copy of the parent env (with the three
nnUNet_* vars guaranteed present). stdout+stderr are redirected to log_path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.jobs import Job, insert_job, update_job_status


def _popen_kwargs() -> dict:
    if os.name == "posix":
        return {"start_new_session": True}
    elif sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {}


def spawn(
    cfg: GuiConfig,
    *,
    kind: str,
    argv: list[str],
    env: dict[str, str],
    log_path: str,
    output_run_id: Optional[str] = None,
    slot: str = "global",
) -> Job:
    """Spawn `argv` in its own process group, persist & return the Job."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    # Insert in 'starting' first so the row exists even if Popen raises.
    started_at = datetime.now(timezone.utc)
    job = insert_job(cfg, Job(
        id=None, kind=kind, args_json=json.dumps(argv),
        pid=None, pgid=None, status="starting",
        started_at=started_at, ended_at=None, exit_code=None,
        log_path=log_path, output_run_id=output_run_id,
        created_by="gui", error_message=None, slot=slot,
    ))
    try:
        log_fh = open(log_path, "ab", buffering=0)
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **_popen_kwargs(),
        )
        pgid = os.getpgid(proc.pid) if os.name == "posix" else proc.pid
        update_job_status(cfg, job.id, status="running", pid=proc.pid, pgid=pgid)
    except Exception as e:
        update_job_status(cfg, job.id, status="failed", ended_at=datetime.now(timezone.utc),
                          exit_code=-1, error_message=f"spawn failed: {e}")
        raise
    # Re-fetch to return the updated row
    from nnunetv2.gui.state.jobs import get_job
    fresh = get_job(cfg, job.id)
    assert fresh is not None
    return fresh
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_launcher.py -v
git add nnunetv2/gui/jobs/launcher.py nnunetv2/tests/gui/unit/test_launcher.py
git commit -m "gui(jobs): launcher.spawn with detached process group + status persistence"
```

---

## Task 5: `jobs/reaper.py` — observe exit, update status (TDD)

**Files:**
- Create: `nnunetv2/gui/jobs/reaper.py`
- Create: `nnunetv2/tests/gui/unit/test_reaper.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_reaper.py
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.reaper import run_reaper, attach_on_boot
from nnunetv2.gui.state.jobs import get_job, Job, insert_job


@pytest.mark.asyncio
async def test_reaper_marks_completed_on_clean_exit(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r.log"))
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "completed"
    assert fetched.exit_code == 0


@pytest.mark.asyncio
async def test_reaper_marks_failed_on_nonzero_exit(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "3"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r2.log"))
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "failed"
    assert fetched.exit_code == 3


@pytest.mark.asyncio
async def test_attach_on_boot_marks_unknown_for_dead_pid(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=999999, pgid=999999,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status in ("failed", "unknown")


@pytest.mark.asyncio
async def test_attach_on_boot_reattaches_live_pid(gui_config):
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "1.0", "0"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r3.log"))
    # Simulate restart: re-run attach. Should detect alive and schedule reaper.
    tasks = await attach_on_boot(gui_config)
    assert len(tasks) == 1
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "completed"
```

- [ ] **Step 2: Implement `reaper.py`**

```python
"""Reaper supervises spawned processes and updates job status on exit.

run_reaper(cfg, job_id, pid):
  Spawns a thread executor task awaiting os.waitpid (POSIX) or psutil wait
  (cross-platform), then transitions the row.

attach_on_boot(cfg):
  Walks all non-terminal jobs and either schedules a reaper coroutine
  (live pid) or transitions to failed/unknown (dead pid).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.signals import is_alive
from nnunetv2.gui.state.jobs import JobFilter, get_job, list_jobs, update_job_status


def _wait_process_blocking(pid: int) -> int:
    """Block until pid exits; return exit code (0 if cannot determine)."""
    try:
        import psutil
        p = psutil.Process(pid)
        try:
            return p.wait()
        except psutil.NoSuchProcess:
            return -1
    except ImportError:
        # POSIX fallback
        if os.name == "posix":
            try:
                _, status = os.waitpid(pid, 0)
                if os.WIFEXITED(status):
                    return os.WEXITSTATUS(status)
                return -1
            except ChildProcessError:
                # PID is not a child of this process; poll instead.
                while is_alive(pid):
                    import time
                    time.sleep(0.5)
                return 0
        return -1


async def run_reaper(cfg: GuiConfig, job_id: int, pid: int) -> None:
    """Await `pid` exit and write the terminal status row."""
    loop = asyncio.get_running_loop()
    exit_code = await loop.run_in_executor(None, _wait_process_blocking, pid)
    final_status = "completed" if exit_code == 0 else "failed"
    update_job_status(
        cfg, job_id,
        status=final_status,
        ended_at=datetime.now(timezone.utc),
        exit_code=exit_code,
    )


async def attach_on_boot(cfg: GuiConfig) -> list[asyncio.Task]:
    """Sweep non-terminal jobs; reschedule reapers for live PIDs."""
    scheduled: list[asyncio.Task] = []
    for job in list_jobs(cfg, JobFilter()):
        if job.status not in ("queued", "starting", "running"):
            continue
        if job.status == "queued":
            # Will be picked up by the queue advancer; nothing to do here.
            continue
        if job.pid is None:
            update_job_status(cfg, job.id, status="failed",
                              ended_at=datetime.now(timezone.utc),
                              error_message="no pid recorded")
            continue
        if is_alive(job.pid):
            task = asyncio.create_task(run_reaper(cfg, job.id, job.pid))
            scheduled.append(task)
        else:
            # Decide between completed/failed/unknown using disk evidence
            terminal = _disk_evidence_terminal_status(cfg, job)
            update_job_status(cfg, job.id, status=terminal,
                              ended_at=datetime.now(timezone.utc),
                              error_message=("process gone, no disk evidence" if terminal == "unknown" else None))
    return scheduled


def _disk_evidence_terminal_status(cfg: GuiConfig, job) -> str:
    """Best-effort: train jobs with a final checkpoint = completed; else unknown."""
    if job.kind == "train" and job.output_run_id:
        ckpt = Path(cfg.results) / job.output_run_id / "checkpoint_final.pth"
        if ckpt.is_file():
            return "completed"
    return "unknown"
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_reaper.py -v
git add nnunetv2/gui/jobs/reaper.py nnunetv2/tests/gui/unit/test_reaper.py
git commit -m "gui(jobs): reaper coroutine + attach_on_boot for restart-safe lifecycle"
```

---

## Task 6: `jobs/queue.py` — serial queue (TDD)

**Files:**
- Create: `nnunetv2/gui/jobs/queue.py`
- Create: `nnunetv2/tests/gui/unit/test_queue.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/unit/test_queue.py
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.queue import JobQueue
from nnunetv2.gui.state.jobs import JobFilter, list_jobs


@pytest.mark.asyncio
async def test_queue_runs_jobs_serially(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)

    argv1 = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.3", "0"]
    argv2 = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "0"]

    j1 = await q.enqueue(kind="train", argv=argv1, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j1.log"))
    j2 = await q.enqueue(kind="train", argv=argv2, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j2.log"))

    # j1 should be running, j2 queued.
    await asyncio.sleep(0.1)
    j1_now = list_jobs(gui_config, JobFilter())[0]
    # Wait for both to finish
    await q.drain(timeout=5)
    statuses = [j.status for j in list_jobs(gui_config, JobFilter())]
    assert set(statuses) == {"completed"}
    # Ordering: j2.started_at >= j1.ended_at (serial)
    j1f = next(j for j in list_jobs(gui_config, JobFilter()) if j.id == j1.id)
    j2f = next(j for j in list_jobs(gui_config, JobFilter()) if j.id == j2.id)
    assert j2f.started_at >= j1f.ended_at


@pytest.mark.asyncio
async def test_queue_cancel_queued_only(gui_config):
    init_db(gui_config)
    q = JobQueue(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.5", "0"]

    j1 = await q.enqueue(kind="train", argv=argv, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j1.log"))
    j2 = await q.enqueue(kind="train", argv=argv, env=os.environ.copy(),
                          log_path=str(gui_config.results / "j2.log"))
    # j2 is queued; cancel it
    await asyncio.sleep(0.05)
    ok = await q.cancel(j2.id)
    assert ok
    # Cancelling the already-running j1 returns False (must use stop)
    ok = await q.cancel(j1.id)
    assert ok is False
    await q.drain(timeout=5)
    from nnunetv2.gui.state.jobs import get_job
    assert get_job(gui_config, j2.id).status == "cancelled"
```

- [ ] **Step 2: Implement `queue.py`**

```python
"""Single-host serial job queue.

Each slot has its own asyncio.Lock + worker. v1 ships with a single
'global' slot; future phases shard by dataset/fold.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.reaper import run_reaper
from nnunetv2.gui.state.jobs import Job, JobFilter, get_job, insert_job, list_jobs, update_job_status


class JobQueue:
    def __init__(self, cfg: GuiConfig) -> None:
        self.cfg = cfg
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(
        self,
        *, kind: str, argv: list[str], env: dict[str, str], log_path: str,
        output_run_id: Optional[str] = None, slot: str = "global",
    ) -> Job:
        """Persist a queued row and kick the worker if idle."""
        # Persist as 'queued' first so the UI sees it immediately.
        job = insert_job(self.cfg, Job(
            id=None, kind=kind, args_json=json.dumps(argv),
            pid=None, pgid=None, status="queued",
            started_at=None, ended_at=None, exit_code=None,
            log_path=log_path, output_run_id=output_run_id,
            created_by="gui", error_message=None, slot=slot,
        ))
        # Kick worker; it picks up the next 'queued' job in this slot.
        t = asyncio.create_task(self._worker_kick(slot))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return job

    async def _worker_kick(self, slot: str) -> None:
        lock = self._locks[slot]
        if lock.locked():
            return  # another worker is already running
        async with lock:
            while True:
                next_job = self._pop_next_queued(slot)
                if next_job is None:
                    return
                # Re-spawn (now becomes 'running')
                # We need to delete the 'queued' row and re-insert via spawn, OR
                # update the row in-place. We update in-place to preserve id.
                await self._launch_in_place(next_job)
                # Reaper runs inline so the lock is held until exit (serial).
                if next_job.pid is None:
                    continue  # spawn failed; row marked failed by launcher
                await run_reaper(self.cfg, next_job.id, next_job.pid)

    async def _launch_in_place(self, queued: Job) -> None:
        """Promote a queued row to running by spawning the subprocess."""
        from nnunetv2.gui.jobs.launcher import _popen_kwargs
        import subprocess
        from pathlib import Path
        argv = json.loads(queued.args_json)
        log_path = queued.log_path or str(Path(self.cfg.results) / f"job_{queued.id}.log")
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            log_fh = open(log_path, "ab", buffering=0)
            proc = subprocess.Popen(
                argv, env=os.environ.copy(),
                stdout=log_fh, stderr=subprocess.STDOUT,
                close_fds=True, **_popen_kwargs(),
            )
            pgid = os.getpgid(proc.pid) if os.name == "posix" else proc.pid
            update_job_status(self.cfg, queued.id, status="running",
                              pid=proc.pid, pgid=pgid,
                              started_at=datetime.now(timezone.utc))
            # Refresh local copy
            queued.pid = proc.pid
            queued.pgid = pgid
            queued.status = "running"
        except Exception as e:
            update_job_status(self.cfg, queued.id, status="failed",
                              ended_at=datetime.now(timezone.utc),
                              error_message=f"spawn failed: {e}")

    def _pop_next_queued(self, slot: str) -> Optional[Job]:
        candidates = [j for j in list_jobs(self.cfg, JobFilter(status="queued"))
                      if j.slot == slot]
        if not candidates:
            return None
        return candidates[-1]  # list_jobs sorts desc by id; pick oldest → last

    async def cancel(self, job_id: int) -> bool:
        """Cancel a queued job. Returns False if the job is no longer queued."""
        j = get_job(self.cfg, job_id)
        if j is None or j.status != "queued":
            return False
        update_job_status(self.cfg, job_id, status="cancelled",
                          ended_at=datetime.now(timezone.utc))
        return True

    async def drain(self, timeout: float = 30.0) -> None:
        """For tests: await all outstanding workers."""
        await asyncio.wait_for(asyncio.gather(*list(self._tasks), return_exceptions=True), timeout=timeout)
```

**Note:** `_pop_next_queued` order: `list_jobs` orders by id desc, so oldest is last. The implementation must pick the oldest-queued.

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/unit/test_queue.py -v
git add nnunetv2/gui/jobs/queue.py nnunetv2/tests/gui/unit/test_queue.py
git commit -m "gui(jobs): serial JobQueue with per-slot lock + cancel"
```

---

## Task 7: Wire queue + boot attach into `server.py`

**Files:**
- Modify: `nnunetv2/gui/server.py`

- [ ] **Step 1: Add startup + shutdown handlers**

```python
# in create_app, after app = FastAPI(...):
from nnunetv2.gui.jobs.queue import JobQueue
from nnunetv2.gui.jobs.reaper import attach_on_boot as reaper_attach

app.state.job_queue = JobQueue(cfg)

@app.on_event("startup")
async def _attach_jobs_on_boot() -> None:
    tasks = await reaper_attach(cfg)
    app.state._boot_reaper_tasks = tasks

@app.on_event("shutdown")
async def _shutdown_jobs() -> None:
    # Critical: do NOT terminate the subprocesses themselves.
    # Just stop tailing/reaping — they will continue under their detached pgid.
    for t in getattr(app.state, "_boot_reaper_tasks", []):
        t.cancel()
```

- [ ] **Step 2: Quick smoke test**

```bash
pytest nnunetv2/tests/gui/ -v -k "reaper or queue or launcher" 
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add nnunetv2/gui/server.py
git commit -m "gui(server): startup hook to attach on boot; shutdown does NOT kill subprocesses"
```

---

## Task 8: Preprocess router + dataset detail "Preprocess" button (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/preprocess.py`
- Modify: `nnunetv2/gui/server.py` (include router)
- Create: `nnunetv2/tests/gui/api/test_preprocess_api.py`

- [ ] **Step 1: Failing tests**

```python
# nnunetv2/tests/gui/api/test_preprocess_api.py
def test_preprocess_dry_run_returns_argv(populated_client):
    r = populated_client.post("/api/preprocess?dry_run=true",
                               json={"dataset_id": 27, "verify_dataset_integrity": True})
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][:2] == ["nnUNetv2_plan_and_preprocess", "-d"]
    assert "27" in body["argv"]
    assert body["cli"].startswith("nnUNetv2_plan_and_preprocess")
    assert "job_id" not in body  # dry-run doesn't enqueue


def test_preprocess_enqueue_creates_job(populated_client):
    r = populated_client.post("/api/preprocess",
                               json={"dataset_id": 27})
    assert r.status_code == 201
    body = r.json()
    assert "job_id" in body


def test_preprocess_validation_error(populated_client):
    r = populated_client.post("/api/preprocess", json={})
    assert r.status_code == 422  # FastAPI validation
```

- [ ] **Step 2: Implement `routers/preprocess.py`**

```python
"""POST /api/preprocess — render argv, optionally enqueue."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from nnunetv2.gui.services.cli_renderer import (
    PreprocessRequest, render_preprocess, argv_to_cli_string,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/preprocess", tags=["preprocess"])

    @router.post("")
    async def enqueue(req: PreprocessRequest, request: Request,
                       dry_run: bool = False) -> dict:
        argv = render_preprocess(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return {"argv": argv, "cli": cli}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        import os
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs" / f"preprocess_d{req.dataset_id}.log")
        job = await q.enqueue(kind="preprocess", argv=argv, env=os.environ.copy(),
                               log_path=log_path)
        return {"job_id": job.id, "argv": argv, "cli": cli}

    return router
```

Set the status code via a wrapper:

```python
from fastapi import status
# in router decorator:
@router.post("", status_code=status.HTTP_201_CREATED)
```

(Adjust the dry-run test to expect 201; or short-circuit dry-run to 200 with a Response.)

- [ ] **Step 3: Wire + pass + commit**

```python
# server.py
from nnunetv2.gui.routers import preprocess as preprocess_router
# ...
app.include_router(preprocess_router.make_router())
```

```bash
pytest nnunetv2/tests/gui/api/test_preprocess_api.py -v
git add nnunetv2/gui/routers/preprocess.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_preprocess_api.py
git commit -m "gui(api): POST /api/preprocess (dry-run + enqueue)"
```

---

## Task 9: Train router with multi-fold expansion (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/train.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/api/test_train_api.py`

The train form's `folds` field is a list. The route fans out **one queued job per fold** so they execute serially.

- [ ] **Step 1: Failing tests**

```python
def test_train_dry_run_single_fold(populated_client):
    r = populated_client.post("/api/train?dry_run=true",
                               json={"dataset_id": 27, "configuration": "3d_fullres", "folds": ["0"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["argv"][:4] == ["nnUNetv2_train", "27", "3d_fullres", "0"]


def test_train_dry_run_multifold(populated_client):
    r = populated_client.post("/api/train?dry_run=true",
                               json={"dataset_id": 27, "configuration": "3d_fullres",
                                      "folds": ["0", "1", "2"]})
    body = r.json()
    assert len(body["jobs"]) == 3
    folds = [j["argv"][3] for j in body["jobs"]]
    assert folds == ["0", "1", "2"]


def test_train_enqueue_creates_n_jobs(populated_client):
    r = populated_client.post("/api/train",
                               json={"dataset_id": 27, "configuration": "3d_fullres",
                                      "folds": ["0", "1"]})
    assert r.status_code == 201
    body = r.json()
    assert len(body["job_ids"]) == 2


def test_train_includes_npz_when_requested(populated_client):
    r = populated_client.post("/api/train?dry_run=true",
                               json={"dataset_id": 27, "configuration": "3d_fullres",
                                      "folds": ["0"], "npz": True})
    body = r.json()
    assert "--npz" in body["jobs"][0]["argv"]
```

- [ ] **Step 2: Implement `routers/train.py`**

```python
"""POST /api/train — fan a multi-fold request into N queued jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from nnunetv2.gui.services.cli_renderer import (
    TrainRequest, render_train, argv_to_cli_string,
)


class TrainBatchRequest(BaseModel):
    dataset_id: int
    configuration: str
    folds: list[str] = Field(default_factory=lambda: ["0"])
    trainer: Optional[str] = None
    plans: Optional[str] = None
    pretrained_weights: Optional[str] = None
    num_gpus: int = 1
    npz: bool = False
    continue_training: bool = False
    val_only: bool = False
    val_best: bool = False
    disable_checkpointing: bool = False
    device: str = "cuda"


def _per_fold_requests(batch: TrainBatchRequest) -> list[TrainRequest]:
    out = []
    for f in batch.folds:
        out.append(TrainRequest(
            dataset_id=batch.dataset_id,
            configuration=batch.configuration,
            fold=f,
            trainer=batch.trainer,
            plans=batch.plans,
            pretrained_weights=batch.pretrained_weights,
            num_gpus=batch.num_gpus,
            npz=batch.npz,
            continue_training=batch.continue_training,
            val_only=batch.val_only,
            val_best=batch.val_best,
            disable_checkpointing=batch.disable_checkpointing,
            device=batch.device,
        ))
    return out


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/train", tags=["train"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def enqueue(batch: TrainBatchRequest, request: Request,
                       dry_run: bool = False) -> dict:
        per_fold = _per_fold_requests(batch)
        jobs_render = [{"argv": render_train(r), "cli": argv_to_cli_string(render_train(r))}
                       for r in per_fold]
        if dry_run:
            return {"jobs": jobs_render}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        import os
        job_ids: list[int] = []
        plans = batch.plans or "nnUNetPlans"
        trainer = batch.trainer or "nnUNetTrainer"
        for fold_req, rendered in zip(per_fold, jobs_render):
            output_run_id = f"Dataset{batch.dataset_id:03d}/{plans}__{trainer}__{batch.configuration}/fold_{fold_req.fold}"
            log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs"
                           / f"train_d{batch.dataset_id}_{batch.configuration}_f{fold_req.fold}.log")
            j = await q.enqueue(kind="train", argv=rendered["argv"],
                                 env=os.environ.copy(), log_path=log_path,
                                 output_run_id=output_run_id)
            job_ids.append(j.id)
        return {"job_ids": job_ids, "jobs": jobs_render}

    return router
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_train_api.py -v
git add nnunetv2/gui/routers/train.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_train_api.py
git commit -m "gui(api): POST /api/train fans multi-fold into N queued jobs"
```

---

## Task 10: Predict router (TDD)

**Files:**
- Create: `nnunetv2/gui/routers/predict.py`
- Modify: `nnunetv2/gui/server.py`
- Create: `nnunetv2/tests/gui/api/test_predict_api.py`

- [ ] **Step 1: Failing tests**

```python
def test_predict_dry_run(populated_client, tmp_path):
    in_dir = tmp_path / "in"; out_dir = tmp_path / "out"
    in_dir.mkdir(); out_dir.mkdir()
    r = populated_client.post("/api/predict?dry_run=true", json={
        "dataset_id": 27, "configuration": "3d_fullres",
        "input_folder": str(in_dir), "output_folder": str(out_dir),
        "folds": ["all"], "save_probabilities": True,
    })
    body = r.json()
    assert body["argv"][0] == "nnUNetv2_predict"
    assert "--save_probabilities" in body["argv"]


def test_predict_validation_missing_paths(populated_client):
    r = populated_client.post("/api/predict",
                               json={"dataset_id": 27, "configuration": "3d_fullres"})
    assert r.status_code == 422
```

- [ ] **Step 2: Implement `routers/predict.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, status

from nnunetv2.gui.services.cli_renderer import (
    PredictRequest, render_predict, argv_to_cli_string,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/predict", tags=["predict"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def enqueue(req: PredictRequest, request: Request, dry_run: bool = False) -> dict:
        argv = render_predict(req)
        cli = argv_to_cli_string(argv)
        if dry_run:
            return {"argv": argv, "cli": cli}
        q = request.app.state.job_queue
        cfg = request.app.state.gui_config
        import os
        log_path = str(Path(cfg.results) / ".nnunet_gui" / "logs"
                       / f"predict_d{req.dataset_id}_{req.configuration}.log")
        j = await q.enqueue(kind="predict", argv=argv,
                             env=os.environ.copy(), log_path=log_path)
        return {"job_id": j.id, "argv": argv, "cli": cli}

    return router
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_predict_api.py -v
git add nnunetv2/gui/routers/predict.py nnunetv2/gui/server.py nnunetv2/tests/gui/api/test_predict_api.py
git commit -m "gui(api): POST /api/predict enqueue + dry-run"
```

---

## Task 11: Job write actions: stop / cancel / restart (TDD)

**Files:**
- Modify: `nnunetv2/gui/routers/jobs.py`
- Create: `nnunetv2/tests/gui/api/test_jobs_actions.py`

- [ ] **Step 1: Failing tests**

```python
def test_stop_running_job(populated_client, monkeypatch):
    import os, sys, time
    from nnunetv2.gui.jobs.launcher import spawn
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "30"]
    job = spawn(cfg, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(cfg.results / "stoptest.log"))
    r = populated_client.post(f"/api/jobs/{job.id}/stop")
    assert r.status_code in (200, 202)
    # Wait briefly for the kill to take effect
    deadline = time.time() + 5
    from nnunetv2.gui.jobs.signals import is_alive
    while time.time() < deadline and is_alive(job.pgid):
        time.sleep(0.1)
    assert not is_alive(job.pgid)


def test_cancel_queued_job(populated_client):
    # Insert a queued job directly
    from nnunetv2.gui.state.jobs import Job, insert_job
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    j = insert_job(cfg, Job(id=None, kind="train", args_json="[]",
                            pid=None, pgid=None, status="queued",
                            started_at=None, ended_at=None, exit_code=None,
                            log_path=None, output_run_id=None,
                            created_by="gui", error_message=None, slot="global"))
    r = populated_client.post(f"/api/jobs/{j.id}/cancel")
    assert r.status_code == 200


def test_cancel_running_job_rejected(populated_client):
    from nnunetv2.gui.state.jobs import Job, insert_job
    from nnunetv2.gui.config import GuiConfig
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    j = insert_job(cfg, Job(id=None, kind="train", args_json="[]",
                            pid=999999, pgid=999999, status="running",
                            started_at=None, ended_at=None, exit_code=None,
                            log_path=None, output_run_id=None,
                            created_by="gui", error_message=None, slot="global"))
    r = populated_client.post(f"/api/jobs/{j.id}/cancel")
    assert r.status_code == 409


def test_restart_finished_job(populated_client):
    from nnunetv2.gui.state.jobs import Job, insert_job
    from nnunetv2.gui.config import GuiConfig
    import sys
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05"]
    import json
    j = insert_job(cfg, Job(id=None, kind="train",
                            args_json=json.dumps(argv),
                            pid=None, pgid=None, status="failed",
                            started_at=None, ended_at=None, exit_code=1,
                            log_path=str(cfg.results / "r.log"),
                            output_run_id=None, created_by="gui",
                            error_message=None, slot="global"))
    r = populated_client.post(f"/api/jobs/{j.id}/restart")
    assert r.status_code == 201
    assert "new_job_id" in r.json()
```

- [ ] **Step 2: Implement actions in `routers/jobs.py`**

```python
    @router.post("/{job_id}/stop")
    async def stop(job_id: int, request: Request) -> dict:
        from nnunetv2.gui.jobs.signals import terminate, kill_group, is_alive
        cfg = request.app.state.gui_config
        from nnunetv2.gui.state.jobs import get_job, update_job_status
        from datetime import datetime, timezone
        j = get_job(cfg, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if j.status not in ("starting", "running"):
            raise HTTPException(status_code=409,
                detail=f"Cannot stop a job in status {j.status!r}")
        if j.pgid is None:
            raise HTTPException(status_code=500, detail="job has no pgid recorded")
        terminate(j.pgid)
        # Grace period 5s
        import asyncio
        deadline = asyncio.get_event_loop().time() + 5
        while is_alive(j.pgid) and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.2)
        if is_alive(j.pgid):
            kill_group(j.pgid)
            await asyncio.sleep(0.5)
        update_job_status(cfg, job_id, status="killed",
                          ended_at=datetime.now(timezone.utc))
        return {"ok": True, "status": "killed"}

    @router.post("/{job_id}/cancel")
    async def cancel(job_id: int, request: Request) -> dict:
        q = request.app.state.job_queue
        ok = await q.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=409,
                detail="Cannot cancel — job is not queued (use /stop)")
        return {"ok": True, "status": "cancelled"}

    @router.post("/{job_id}/restart", status_code=201)
    async def restart(job_id: int, request: Request) -> dict:
        cfg = request.app.state.gui_config
        from nnunetv2.gui.state.jobs import get_job
        old = get_job(cfg, job_id)
        if old is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if old.status not in ("completed", "failed", "killed", "cancelled", "unknown"):
            raise HTTPException(status_code=409,
                detail=f"Cannot restart a job in status {old.status!r}")
        import json, os
        argv = json.loads(old.args_json)
        log_path = old.log_path or str(cfg.results / f".nnunet_gui/logs/restart_{job_id}.log")
        new = await request.app.state.job_queue.enqueue(
            kind=old.kind, argv=argv, env=os.environ.copy(),
            log_path=log_path, output_run_id=old.output_run_id,
            slot=old.slot,
        )
        return {"new_job_id": new.id}
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_jobs_actions.py -v
git add nnunetv2/gui/routers/jobs.py nnunetv2/tests/gui/api/test_jobs_actions.py
git commit -m "gui(api): POST /jobs/{id}/stop|cancel|restart"
```

---

## Task 12: GPU info endpoint (TDD)

**Files:**
- Create: `nnunetv2/gui/services/gpu.py`
- Modify: `nnunetv2/gui/routers/system.py`
- Create: `nnunetv2/tests/gui/api/test_gpu_api.py`

- [ ] **Step 1: Failing tests**

```python
def test_gpu_info_returns_list(client):
    r = client.get("/api/system/gpu")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # Cannot assert non-empty on CI (no GPU); only that the shape is correct.
    for g in body:
        assert {"index", "name", "memory_total_mb", "memory_used_mb", "util_pct"} <= set(g)


def test_gpu_info_no_pynvml(client, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pynvml", None)  # force ImportError on next import
    # NOTE: This monkeypatch may need a separate fixture pattern; the key thing
    # is the endpoint returns [] without crashing.
    r = client.get("/api/system/gpu")
    assert r.status_code == 200
    assert r.json() == [] or isinstance(r.json(), list)
```

- [ ] **Step 2: Implement `gpu.py`**

```python
# nnunetv2/gui/services/gpu.py
"""GPU info via pynvml; degrades to [] if pynvml is unavailable or fails."""
from __future__ import annotations


def gpu_info() -> list[dict]:
    try:
        import pynvml
    except Exception:
        return []
    try:
        pynvml.nvmlInit()
    except Exception:
        return []
    try:
        out: list[dict] = []
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            try:
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                out.append({
                    "index": i,
                    "name": name,
                    "memory_total_mb": int(mem.total / 1024 / 1024),
                    "memory_used_mb": int(mem.used / 1024 / 1024),
                    "util_pct": int(util.gpu),
                })
            except Exception:
                continue
        return out
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
```

Add `GET /api/system/gpu` to `routers/system.py`:

```python
@router.get("/gpu")
def gpu(request: Request) -> list[dict]:
    from nnunetv2.gui.services.gpu import gpu_info
    return gpu_info()
```

- [ ] **Step 3: Pass + commit**

```bash
pytest nnunetv2/tests/gui/api/test_gpu_api.py -v
git add nnunetv2/gui/services/gpu.py nnunetv2/gui/routers/system.py nnunetv2/tests/gui/api/test_gpu_api.py
git commit -m "gui(api): /api/system/gpu via pynvml with graceful degrade"
```

---

## Task 13: Frontend types + API calls for new endpoints

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add types**

```ts
export interface PreprocessRequest {
  dataset_id: number;
  verify_dataset_integrity?: boolean;
  planner?: string;
  configurations?: string[];
}

export interface TrainBatchRequest {
  dataset_id: number;
  configuration: string;
  folds: string[];
  trainer?: string;
  plans?: string;
  pretrained_weights?: string;
  num_gpus?: number;
  npz?: boolean;
  continue_training?: boolean;
  val_only?: boolean;
  val_best?: boolean;
  disable_checkpointing?: boolean;
  device?: string;
}

export interface PredictRequest {
  dataset_id: number;
  configuration: string;
  input_folder: string;
  output_folder: string;
  folds: string[];
  checkpoint?: string;
  step_size?: number;
  disable_tta?: boolean;
  save_probabilities?: boolean;
  continue_prediction?: boolean;
  device?: string;
}

export interface GpuInfo {
  index: number;
  name: string;
  memory_total_mb: number;
  memory_used_mb: number;
  util_pct: number;
}
```

- [ ] **Step 2: Add API helpers**

```ts
export const launchEndpoints = {
  postPreprocess: (req: PreprocessRequest, dryRun = false) =>
    api.post(`/api/preprocess${dryRun ? '?dry_run=true' : ''}`, req),
  postTrain: (req: TrainBatchRequest, dryRun = false) =>
    api.post(`/api/train${dryRun ? '?dry_run=true' : ''}`, req),
  postPredict: (req: PredictRequest, dryRun = false) =>
    api.post(`/api/predict${dryRun ? '?dry_run=true' : ''}`, req),
  stopJob: (id: number) => api.post(`/api/jobs/${id}/stop`, {}),
  cancelJob: (id: number) => api.post(`/api/jobs/${id}/cancel`, {}),
  restartJob: (id: number) => api.post(`/api/jobs/${id}/restart`, {}),
  getGpuInfo: () => api.get<GpuInfo[]>('/api/system/gpu'),
};
```

- [ ] **Step 3: Commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && cd ..
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "gui(frontend): types + API helpers for launch endpoints + GPU info"
```

---

## Task 14: `CliPreview` + `PreprocessForm` + `TrainForm` + `PredictForm`

**Files:**
- Create: `frontend/src/lib/forms/CliPreview.svelte`
- Create: `frontend/src/lib/forms/PreprocessForm.svelte`
- Create: `frontend/src/lib/forms/TrainForm.svelte`
- Create: `frontend/src/lib/forms/PredictForm.svelte`

- [ ] **Step 1: `CliPreview.svelte`** — props `{ cli: string }`, copy-to-clipboard button:

```svelte
<script lang="ts">
  let { cli }: { cli: string } = $props();
  let copied = $state(false);

  async function copy() {
    await navigator.clipboard.writeText(cli);
    copied = true;
    setTimeout(() => (copied = false), 1500);
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2 font-mono text-[11px] flex gap-2 items-start">
  <code class="flex-1 break-all">{cli}</code>
  <button class="px-2 py-0.5 bg-bg-panel rounded text-slate-300 hover:bg-bg-soft" onclick={copy}>
    {copied ? 'copied!' : 'copy'}
  </button>
</div>
```

- [ ] **Step 2: `PreprocessForm.svelte`** — dataset_id (from workspace), planner dropdown (`nnUNetPlannerResEncM/L/XL` chips), verify-integrity checkbox. On submit, calls `postPreprocess(...)`. Live CLI preview via dry-run on every change.

```svelte
<script lang="ts">
  import { launchEndpoints } from '../api';
  import CliPreview from './CliPreview.svelte';

  let { datasetIdInt }: { datasetIdInt: number } = $props();

  let planner = $state<string>('');
  let verify = $state(true);
  let argv = $state<string[]>([]);
  let cli = $state<string>('');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let jobId = $state<number | null>(null);

  $effect(() => {
    launchEndpoints.postPreprocess({
      dataset_id: datasetIdInt,
      verify_dataset_integrity: verify,
      planner: planner || undefined,
    }, true).then((r: any) => {
      argv = r.argv; cli = r.cli;
    });
  });

  async function submit() {
    submitting = true; error = null;
    try {
      const r: any = await launchEndpoints.postPreprocess({
        dataset_id: datasetIdInt,
        verify_dataset_integrity: verify,
        planner: planner || undefined,
      });
      jobId = r.job_id;
    } catch (e: unknown) { error = (e as Error).message; }
    finally { submitting = false; }
  }
</script>

<div class="space-y-3">
  <label class="block text-xs">
    Planner
    <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={planner}>
      <option value="">Default</option>
      <option value="nnUNetPlannerResEncM">ResEnc M</option>
      <option value="nnUNetPlannerResEncL">ResEnc L</option>
      <option value="nnUNetPlannerResEncXL">ResEnc XL</option>
    </select>
  </label>
  <label class="block text-xs">
    <input type="checkbox" bind:checked={verify} /> Verify dataset integrity
  </label>
  <CliPreview {cli} />
  <button class="px-3 py-1 bg-accent rounded text-white text-xs disabled:opacity-50"
          disabled={submitting} onclick={submit}>
    {submitting ? 'Launching…' : 'Launch preprocess'}
  </button>
  {#if jobId}<p class="text-xs text-ok">Queued as job #{jobId}</p>{/if}
  {#if error}<p class="text-xs text-err">{error}</p>{/if}
</div>
```

- [ ] **Step 3: `TrainForm.svelte`** — dataset (from workspace), configuration chips (2d, 3d_fullres, 3d_lowres, 3d_cascade_fullres), folds multi-chip, num_gpus, trainer/plans text fields, `--npz` checkbox, "Launch" button. Live CLI preview via dry-run.

(See [Phase 4 spec § Train](docs/superpowers/specs/2026-05-16-nnunet-gui-manager-design.md#train) for the field list — implement them all but in a compact UI. GPU contention warning fires when `num_gpus * estimated_mb > free_mb` from `getGpuInfo()`.)

```svelte
<script lang="ts">
  import { launchEndpoints } from '../api';
  import CliPreview from './CliPreview.svelte';
  import type { GpuInfo } from '../types';

  let { datasetIdInt }: { datasetIdInt: number } = $props();

  let configuration = $state('3d_fullres');
  let folds = $state<string[]>(['0']);
  let trainer = $state(''); let plans = $state('');
  let num_gpus = $state(1); let npz = $state(false); let cont = $state(false);
  let lines = $state<{cli: string; fold: string}[]>([]);
  let gpu = $state<GpuInfo[]>([]);
  let jobIds = $state<number[]>([]);
  let submitting = $state(false); let error = $state<string | null>(null);

  const CONFIGS = ['2d', '3d_fullres', '3d_lowres', '3d_cascade_fullres'];
  const ALL_FOLDS = ['0', '1', '2', '3', '4', 'all'];

  function toggleFold(f: string) {
    folds = folds.includes(f) ? folds.filter((x) => x !== f) : [...folds, f];
  }

  $effect(() => {
    launchEndpoints.postTrain({
      dataset_id: datasetIdInt, configuration, folds,
      trainer: trainer || undefined, plans: plans || undefined,
      num_gpus, npz, continue_training: cont,
    }, true).then((r: any) => {
      lines = r.jobs.map((j: any, i: number) => ({ cli: j.cli, fold: folds[i] }));
    });
  });

  // Pull GPU info once
  $effect(() => { launchEndpoints.getGpuInfo().then((g) => (gpu = g)); });

  const projectedMb = $derived(num_gpus * 11000); // rough nnUNetTrainer default
  const freeMb = $derived(gpu.reduce((s, g) => s + (g.memory_total_mb - g.memory_used_mb), 0));
  const gpuWarn = $derived(gpu.length > 0 && projectedMb > freeMb);

  async function submit() {
    submitting = true; error = null;
    try {
      const r: any = await launchEndpoints.postTrain({
        dataset_id: datasetIdInt, configuration, folds,
        trainer: trainer || undefined, plans: plans || undefined,
        num_gpus, npz, continue_training: cont,
      });
      jobIds = r.job_ids;
    } catch (e: unknown) { error = (e as Error).message; }
    finally { submitting = false; }
  }
</script>

<div class="space-y-3 text-xs">
  <div>Configuration:
    {#each CONFIGS as c}
      <button class="px-2 py-0.5 rounded mr-1"
              class:bg-accent={configuration === c} class:text-white={configuration === c}
              class:bg-bg-panel={configuration !== c} class:text-slate-300={configuration !== c}
              onclick={() => (configuration = c)}>{c}</button>
    {/each}
  </div>
  <div>Folds:
    {#each ALL_FOLDS as f}
      <button class="px-2 py-0.5 rounded mr-1"
              class:bg-accent={folds.includes(f)} class:text-white={folds.includes(f)}
              class:bg-bg-panel={!folds.includes(f)} class:text-slate-300={!folds.includes(f)}
              onclick={() => toggleFold(f)}>{f}</button>
    {/each}
  </div>
  <div class="flex gap-3">
    <label>Trainer <input class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={trainer} placeholder="nnUNetTrainer" /></label>
    <label>Plans <input class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={plans} placeholder="nnUNetPlans" /></label>
    <label>num_gpus <input type="number" min="1" class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1 w-12" bind:value={num_gpus} /></label>
  </div>
  <div>
    <label class="mr-3"><input type="checkbox" bind:checked={npz} /> --npz</label>
    <label><input type="checkbox" bind:checked={cont} /> continue (--c)</label>
  </div>

  {#if gpuWarn}
    <p class="text-amber-400">GPU warning: projected ~{projectedMb} MB &gt; free ~{freeMb} MB</p>
  {/if}

  <div class="space-y-1">
    {#each lines as l}
      <CliPreview cli={l.cli} />
    {/each}
  </div>

  <button class="px-3 py-1 bg-accent rounded text-white disabled:opacity-50" disabled={submitting || folds.length === 0} onclick={submit}>
    {submitting ? 'Queueing…' : `Launch ${folds.length} fold${folds.length > 1 ? 's' : ''}`}
  </button>
  {#if jobIds.length}<p class="text-ok">Queued jobs: {jobIds.join(', ')}</p>{/if}
  {#if error}<p class="text-err">{error}</p>{/if}
</div>
```

- [ ] **Step 4: `PredictForm.svelte`** — same shape: input/output folder text inputs, dataset/configuration, folds multi-chip with `all`, checkpoint dropdown, `--save_probabilities`, `--disable_tta`, device, live CLI preview, launch button.

(Paraphrase of TrainForm with predict-specific fields — see `PredictRequest` model.)

- [ ] **Step 5: svelte-check + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json
git add frontend/src/lib/forms/
git commit -m "gui(frontend): preprocess/train/predict launch forms with live CLI preview"
```

---

## Task 15: Train / Predict / Datasets routes wired to forms

**Files:**
- Modify: `frontend/src/routes/Train.svelte`
- Modify: `frontend/src/routes/Predict.svelte`
- Modify: `frontend/src/components/DatasetDetail.svelte` (Preprocess action button + modal)

- [ ] **Step 1: `Train.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import TrainForm from '../lib/forms/TrainForm.svelte';

  const ws = createWorkspaceStore();
  const ds = createDatasetsStore();
  let workspaceId = $state<string | null>(ws.get());
  let dsState = $state(ds.get());

  onMount(() => {
    const u1 = ws.subscribe((v) => (workspaceId = v));
    const u2 = ds.subscribe((s) => (dsState = s));
    ds.load();
    return () => { u1(); u2(); };
  });

  function datasetIntFor(id: string | null): number | null {
    if (!id || dsState.kind !== 'loaded') return null;
    const m = dsState.data.find((d) => d.id === id);
    return m?.dataset_id_int ?? null;
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Train</h2>
{#if !workspaceId}
  <p class="text-xs text-slate-400 mt-2">Pick a dataset in the header first.</p>
{:else if datasetIntFor(workspaceId) === null}
  <p class="text-xs text-slate-500 mt-2">Loading dataset…</p>
{:else}
  <div class="mt-4 max-w-2xl">
    <TrainForm datasetIdInt={datasetIntFor(workspaceId) as number} />
  </div>
{/if}
```

- [ ] **Step 2: `Predict.svelte`** — same shape with `<PredictForm>` + the Phase 2 PredictionList for browsing the output folder afterwards.

- [ ] **Step 3: `DatasetDetail.svelte`** — add a "Preprocess" action button in the existing header bar that opens a small dialog containing `<PreprocessForm datasetIdInt={...}/>`. The dialog can be a `<details>`/`<summary>` collapsible for minimal new dependencies.

- [ ] **Step 4: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/routes/Train.svelte frontend/src/routes/Predict.svelte frontend/src/components/DatasetDetail.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): Train + Predict + Datasets-Preprocess routes wired to launch forms"
```

---

## Task 16: `JobActionsCell` + wire into JobsTable

**Files:**
- Create: `frontend/src/components/JobActionsCell.svelte`
- Modify: `frontend/src/components/JobsTable.svelte`

- [ ] **Step 1: `JobActionsCell.svelte`** — buttons enabled depending on `job.status`. Calls `launchEndpoints.stopJob`/`cancelJob`/`restartJob`, then triggers a reload of the jobs store via a prop callback.

```svelte
<script lang="ts">
  import { launchEndpoints } from '../lib/api';
  import type { Job } from '../lib/types';

  let { job, onChanged }: { job: Job; onChanged: () => void } = $props();
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function run(action: 'stop' | 'cancel' | 'restart') {
    busy = true; error = null;
    try {
      if (action === 'stop') await launchEndpoints.stopJob(job.id);
      else if (action === 'cancel') await launchEndpoints.cancelJob(job.id);
      else await launchEndpoints.restartJob(job.id);
      onChanged();
    } catch (e: unknown) { error = (e as Error).message; }
    finally { busy = false; }
  }

  const canStop = $derived(['starting', 'running'].includes(job.status));
  const canCancel = $derived(job.status === 'queued');
  const canRestart = $derived(['completed', 'failed', 'killed', 'cancelled', 'unknown'].includes(job.status));
</script>

<div class="flex gap-1">
  <button class="text-[10px] px-1 py-0.5 rounded" class:bg-bg-panel={canStop}
          class:text-slate-300={canStop} class:text-slate-700={!canStop}
          disabled={!canStop || busy} onclick={() => run('stop')}>stop</button>
  <button class="text-[10px] px-1 py-0.5 rounded" class:bg-bg-panel={canCancel}
          class:text-slate-300={canCancel} class:text-slate-700={!canCancel}
          disabled={!canCancel || busy} onclick={() => run('cancel')}>cancel</button>
  <button class="text-[10px] px-1 py-0.5 rounded" class:bg-bg-panel={canRestart}
          class:text-slate-300={canRestart} class:text-slate-700={!canRestart}
          disabled={!canRestart || busy} onclick={() => run('restart')}>restart</button>
</div>
{#if error}<span class="text-[10px] text-err">{error}</span>{/if}
```

- [ ] **Step 2: Wire into `JobsTable.svelte`** — add an Actions column on each row, passing `onChanged={() => jobs.load()}`.

- [ ] **Step 3: svelte-check + build + commit**

```bash
cd frontend && npx svelte-check --tsconfig ./tsconfig.json && npm run build
git add frontend/src/components/JobActionsCell.svelte frontend/src/components/JobsTable.svelte nnunetv2/gui/web/
git commit -m "gui(frontend): JobActionsCell (stop/cancel/restart) wired into JobsTable"
```

---

## Task 17: End-to-end pure-GUI smoke + docs

**Files:**
- Create: `nnunetv2/tests/gui/api/test_pure_gui_smoke.py`
- Modify: `documentation/gui.md`

- [ ] **Step 1: Smoke test using `sleep_helper` masquerading as a CLI**

This test bypasses real nnUNet binaries and verifies the queue + launcher + reaper + actions all wire together via TestClient.

```python
# nnunetv2/tests/gui/api/test_pure_gui_smoke.py
import json
import sys
import time

import pytest


def test_launch_then_stop(populated_client):
    # Override argv via monkeypatching cli_renderer is overkill; instead we
    # call into the queue directly via a small helper endpoint? No — for v1
    # we just rely on the dry_run path + a direct queue.enqueue() call to
    # confirm the lifecycle.
    from nnunetv2.gui.config import GuiConfig
    import os, asyncio
    cfg = GuiConfig.from_env_and_args(host="127.0.0.1", port=0, token=None)

    # Use the running app's queue
    import nnunetv2.gui.server as srv
    # The TestClient created via populated_client already has app.state.job_queue set
    app = populated_client.app
    q = app.state.job_queue

    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "5", "0"]
    log_path = str(cfg.results / ".nnunet_gui" / "logs" / "smoke.log")
    loop = asyncio.new_event_loop()
    try:
        j = loop.run_until_complete(q.enqueue(
            kind="train", argv=argv, env=os.environ.copy(), log_path=log_path,
        ))
    finally:
        loop.close()
    # Give the worker a moment to promote the job to running
    time.sleep(0.5)
    r = populated_client.post(f"/api/jobs/{j.id}/stop")
    assert r.status_code in (200, 202)
    r = populated_client.get(f"/api/jobs/{j.id}")
    body = r.json()
    assert body["status"] in ("killed", "completed")  # depending on race
```

(In practice, the smoke test is somewhat racy because TestClient runs in its own event loop. The recommendation is to call `populated_client.app.state.job_queue` directly in the test. The implementer may extract this into a helper.)

- [ ] **Step 2: Update `documentation/gui.md`**

Mark Phase 4 done, append:

```markdown
4. **Job launching** ✓ — preprocess / train (multi-fold queue) / predict launched from the GUI; stop/cancel/restart actions in the Jobs page; GPU contention warning + CLI preview.
```

- [ ] **Step 3: Full pyramid green + commit**

```bash
pytest nnunetv2/tests/gui/ -v
cd frontend && npm test && npx svelte-check --tsconfig ./tsconfig.json && npm run build && cd ..
git add nnunetv2/tests/gui/api/test_pure_gui_smoke.py documentation/gui.md nnunetv2/gui/web/
git commit -m "gui(tests+docs): pure-GUI launch smoke + Phase 4 roadmap mark"
```

---

## Task 18: Manual verification checklist (before opening PR)

Boot `nnUNetv2_gui` against a real `nnUNet_raw/Dataset004_Hippocampus`:

- [ ] Datasets → Dataset004_Hippocampus → Preprocess button. Click "Launch" with default planner. Confirm Jobs page shows a `running` row that transitions to `completed`.
- [ ] After preprocess completes, Train tab → pick 3d_fullres + folds [0, 1]. Click "Launch 2 folds". Confirm Jobs page shows fold_0 `running` and fold_1 `queued`. After fold_0 finishes, fold_1 starts.
- [ ] On fold_1, hit Stop. Confirm row turns `killed` within 6 s.
- [ ] After fold_0 completes, Predict tab → fill input/output folders → Launch. Confirm prediction completes and the Predict route shows a per-case viewer (Phase 2 PredictionList).
- [ ] Header job badge shows live counts throughout.
- [ ] Kill `uvicorn` (`pkill -f uvicorn`) **while a training is running** and immediately re-launch `nnUNetv2_gui`. Confirm:
  - The training subprocess is still alive (`ps`/`top`).
  - The Jobs page shows the job as `running` after re-boot.
  - The Monitor curves resume tailing.

If any of these fail, open an issue and link the PR.

---

## Done condition

Phase 4 is complete when:

- [ ] All gui pytest tests pass on host + clean env.
- [ ] All frontend vitest tests pass.
- [ ] svelte-check is 0 errors.
- [ ] The manual checklist in Task 18 passes end-to-end on a Linux or macOS box.
- [ ] Restart-during-training does not kill the subprocess; on reboot the GUI re-attaches and the run shows as `running`.
- [ ] CI workflow green on the PR.
- [ ] Documentation reflects Phase 4 completion.

Then move on to Phase 5 (Compare — multi-run aggregation, overlay chart, sortable filterable table, CSV export).
