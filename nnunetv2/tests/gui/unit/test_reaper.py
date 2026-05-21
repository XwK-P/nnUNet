from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.launcher import spawn
from nnunetv2.gui.jobs.reaper import attach_on_boot, run_reaper
from nnunetv2.gui.state.jobs import Job, get_job, insert_job


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
async def test_reaper_uses_proc_wait_when_handle_is_provided(gui_config):
    """If JobQueue hands the Popen handle to run_reaper, it must call
    proc.wait() instead of going through psutil. proc.wait() is
    authoritative even after the child has been reaped by CPython's
    subprocess._active cleanup (the race that produced the recent
    CI flake where status='unknown' replaced 'completed').

    We simulate that race here by sleeping past the child's exit AND
    deliberately picking a pid the test process never owned (psutil
    would return None for unknown pid). The reaper should still
    transition the row to 'completed' because proc.wait() gives the
    real exit code.
    """
    import subprocess
    import time
    from nnunetv2.gui.state.jobs import insert_job

    init_db(gui_config)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.exit(0)"],
    )
    real_pid = proc.pid
    proc.wait(timeout=5)  # let the child exit and become a zombie/reaped
    time.sleep(0.05)
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json="[]",
        pid=real_pid, pgid=real_pid, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    # With proc handed in, the reaper takes proc.wait() -> 0 (already
    # waited; subprocess caches returncode), so we get 'completed'
    # rather than 'unknown' from disk-evidence fallback.
    await asyncio.wait_for(
        run_reaper(gui_config, j.id, real_pid, proc=proc), timeout=5,
    )
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "completed", (
        f"with Popen handle, run_reaper must use proc.wait(); got {fetched.status}"
    )
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
async def test_reaper_uses_disk_evidence_when_exit_code_unknown(gui_config, monkeypatch):
    """Re-attached non-child processes return None from psutil.Process.wait().

    The reaper must not treat that as 'failed'; it should defer to disk
    evidence (checkpoint_final.pth for trainings) and otherwise mark the
    row 'unknown' for an operator to reconcile.
    """
    init_db(gui_config)
    # Simulate the path attach_on_boot would take: a row in 'running' state
    # for a train job that already produced checkpoint_final.pth on disk.
    run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
    fold_dir = gui_config.results / run_id
    fold_dir.mkdir(parents=True, exist_ok=True)
    (fold_dir / "checkpoint_final.pth").write_bytes(b"x")
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json="[]", pid=1, pgid=1,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=run_id, created_by="gui",
        error_message=None, slot="global",
    ))
    # Force _wait_process_blocking → None (the "non-child" case).
    monkeypatch.setattr(
        "nnunetv2.gui.jobs.reaper._wait_process_blocking",
        lambda pid, proc=None: None,
    )
    await asyncio.wait_for(run_reaper(gui_config, j.id, j.pid), timeout=5)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "completed", (
        "disk evidence (checkpoint_final.pth) should drive status to "
        "completed when the actual exit code is unrecoverable"
    )


@pytest.mark.asyncio
async def test_reaper_unknown_when_no_disk_evidence_and_no_exit_code(gui_config, monkeypatch):
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="predict", args_json="[]", pid=1, pgid=1,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    monkeypatch.setattr(
        "nnunetv2.gui.jobs.reaper._wait_process_blocking",
        lambda pid, proc=None: None,
    )
    await asyncio.wait_for(run_reaper(gui_config, j.id, j.pid), timeout=5)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "unknown"
    assert fetched.error_message and "re-attached" in fetched.error_message


@pytest.mark.asyncio
async def test_reaper_preserves_killed_status_after_stop(gui_config):
    """When /api/jobs/{id}/stop has already marked the row 'killed', the
    reaper must not rewrite that status to 'failed' based on the SIGTERM
    exit code it observes when the subprocess actually exits.
    """
    from datetime import datetime, timezone
    from nnunetv2.gui.state.jobs import update_job_status
    init_db(gui_config)
    argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.1", "3"]
    job = spawn(gui_config, kind="train", argv=argv, env=os.environ.copy(),
                log_path=str(gui_config.results / "r_killed.log"))
    # Simulate the stop handler running before the reaper observes the exit.
    stop_time = datetime.now(timezone.utc)
    update_job_status(gui_config, job.id, status="killed", ended_at=stop_time)
    await asyncio.wait_for(run_reaper(gui_config, job.id, job.pid), timeout=5)
    fetched = get_job(gui_config, job.id)
    assert fetched.status == "killed", "reaper overwrote a user-initiated kill"
    # Exit code still recorded for diagnostics.
    assert fetched.exit_code == 3
    # ended_at preserved from the stop handler.
    assert fetched.ended_at is not None


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


@pytest.mark.asyncio
async def test_attach_on_boot_waits_group_when_leader_pid_is_dead(gui_config, monkeypatch):
    """When the recorded leader pid is dead but the pgid still has live
    children (DDP / torchrun after the launcher exits), the reaper must
    wait on the GROUP — waiting on the dead pid would return None
    immediately and terminalise the row while workers are still
    running.

    Stub is_alive so only the pgid registers as alive, capture the
    wait_pgid kwarg passed to run_reaper, and assert it matches.
    """
    init_db(gui_config)
    dead_pid, alive_pgid = 700001, 700099
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json="[]",
        pid=dead_pid, pgid=alive_pgid, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))

    def fake_is_alive(probe: int) -> bool:
        return probe == alive_pgid  # pid is dead

    captured: dict = {}

    async def fake_reaper(cfg, job_id, pid, *, proc=None, wait_pgid=None):
        captured["pid"] = pid
        captured["wait_pgid"] = wait_pgid

    monkeypatch.setattr("nnunetv2.gui.jobs.reaper.is_alive", fake_is_alive)
    monkeypatch.setattr("nnunetv2.gui.jobs.reaper.run_reaper", fake_reaper)

    tasks = await attach_on_boot(gui_config)
    assert len(tasks) == 1
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
    # The reaper was instructed to wait on the GROUP, not the dead pid.
    assert captured["wait_pgid"] == alive_pgid, (
        f"expected wait_pgid={alive_pgid}, got {captured}"
    )


@pytest.mark.asyncio
async def test_run_reaper_with_wait_pgid_polls_until_group_drops(gui_config, monkeypatch):
    """run_reaper(..., wait_pgid=N) must block until is_alive(N) is
    False, then go through the disk-evidence branch (because exit code
    is unrecoverable for non-child workers).
    """
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="predict", args_json="[]",
        pid=500001, pgid=500099, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    # Group reports alive for the first probe, then dead.
    state = {"calls": 0}

    def is_alive_then_drop(probe: int) -> bool:
        state["calls"] += 1
        return state["calls"] <= 1

    monkeypatch.setattr("nnunetv2.gui.jobs.reaper.is_alive", is_alive_then_drop)
    # Shorten the poll so the test isn't a 0.5s sleep.
    import nnunetv2.gui.jobs.reaper as reaper_mod
    real_wait = reaper_mod._wait_group_blocking
    monkeypatch.setattr(
        reaper_mod, "_wait_group_blocking",
        lambda pgid, poll_interval=0.01: real_wait(pgid, poll_interval=0.01),
    )

    await asyncio.wait_for(
        run_reaper(gui_config, j.id, j.pid, wait_pgid=j.pgid), timeout=2
    )
    fetched = get_job(gui_config, j.id)
    # No exit code available; disk-evidence falls through to 'unknown'
    # for a predict job (no checkpoint_final.pth to look at).
    assert fetched.status == "unknown"


@pytest.mark.asyncio
async def test_attach_on_boot_probes_pgid_not_pid(gui_config, monkeypatch):
    """The reattach liveness check must probe the process *group*, not
    the bare pid. A DDP / torchrun training whose group leader has
    already exited (while worker children keep writing) would
    otherwise be misclassified as terminal at server restart, leaving
    the workers unmanaged and the row stale.

    Simulate that pattern with a recorded job where pid is dead but
    pgid still has live children: monkey-patch is_alive to return
    True only for the pgid value.
    """
    init_db(gui_config)
    # Distinct pid vs pgid so we can prove which one was probed.
    dead_pid, alive_pgid = 998877, 998811
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json="[]",
        pid=dead_pid, pgid=alive_pgid, status="running",
        started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None,
        created_by="gui", error_message=None, slot="global",
    ))
    probed: list[int] = []

    def fake_is_alive(probe: int) -> bool:
        probed.append(probe)
        return probe == alive_pgid

    # Patch the symbol attach_on_boot imports.
    monkeypatch.setattr("nnunetv2.gui.jobs.reaper.is_alive", fake_is_alive)
    # Stop the reaper from actually waiting on a fake pid.
    async def noop_reaper(*a, **k):  # noqa: ANN001 - test stub
        return None
    monkeypatch.setattr("nnunetv2.gui.jobs.reaper.run_reaper", noop_reaper)

    tasks = await attach_on_boot(gui_config)
    # First probe must be the pgid (the load-bearing one); a second
    # probe of pid is fine — it's how the new code decides whether
    # the leader is dead and the reaper needs group-polling.
    assert probed and probed[0] == alive_pgid, (
        f"expected attach_on_boot to probe the pgid {alive_pgid} first, got {probed}"
    )
    # And scheduled a reaper for the still-live group.
    assert len(tasks) == 1
    # Status stays "running" — reaper was scheduled, not declared terminal.
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "running"


@pytest.mark.asyncio
async def test_attach_on_boot_marks_failed_for_no_pid(gui_config):
    init_db(gui_config)
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=None, pgid=None,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=None, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "failed"
    assert fetched.error_message and "no pid" in fetched.error_message


@pytest.mark.asyncio
async def test_attach_on_boot_recovers_completed_for_train_with_final_ckpt(gui_config, tmp_path):
    init_db(gui_config)
    run_id = "Dataset027_ACDC/p__t__c/fold_0"
    out = gui_config.results / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkpoint_final.pth").write_bytes(b"x")
    j = insert_job(gui_config, Job(
        id=None, kind="train", args_json='[]', pid=999999, pgid=999999,
        status="running", started_at=None, ended_at=None, exit_code=None,
        log_path=None, output_run_id=run_id, created_by="gui",
        error_message=None, slot="global",
    ))
    await attach_on_boot(gui_config)
    fetched = get_job(gui_config, j.id)
    assert fetched.status == "completed"
