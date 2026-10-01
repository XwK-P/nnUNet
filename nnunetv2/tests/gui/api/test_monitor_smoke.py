"""Phase 3 smoke test.

Boots a real uvicorn server in a background thread, opens an SSE stream
to /sse/runs/{id}/events, writes a brand-new TB scalar in a separate
thread mid-stream, and asserts that the new event lands on the SSE wire
within a generous deadline.

We deliberately avoid the sync TestClient and the in-process ASGITransport
here because both buffer SSE chunks: TestClient does not propagate
http.disconnect to the ASGI app (see the documented skip in
test_monitor_sse.py), and httpx.ASGITransport does not flush
StreamingResponse chunks per-yield. A real server-on-loopback fully
exercises the production wire format.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from contextlib import closing

import pytest
import requests
import uvicorn


def _pick_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread:
    def __init__(self, app, port: int) -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        # Wait for the server to bind.
        for _ in range(50):
            if self.server.started:
                return
            time.sleep(0.1)
        raise RuntimeError("uvicorn never reported started=True within 5s")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def test_live_metric_appears_in_sse(populated_paths, monkeypatch):
    from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir

    fold_dir = (
        populated_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
    )
    tb_dir = fold_dir / "tensorboard"
    build_tb_event_dir(tb_dir, scalars={"train_loss": [(0, 1.0)]})

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))

    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    port = _pick_port()
    app = create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=port, token=None))
    server = _ServerThread(app, port)
    server.start()

    new_step_written = threading.Event()

    def write_new_metric() -> None:
        time.sleep(0.8)
        build_tb_event_dir(tb_dir, scalars={"train_loss": [(1, 0.4)]})
        new_step_written.set()

    writer = threading.Thread(target=write_new_metric, daemon=True)
    writer.start()

    try:
        run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
        url = f"http://127.0.0.1:{port}/sse/runs/{run_id}/events"
        deadline = time.monotonic() + 10.0
        new_step_seen = False

        with requests.get(url, stream=True, timeout=15) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            buf = ""
            for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    buf += chunk
                    while "\n\n" in buf:
                        raw, buf = buf.split("\n\n", 1)
                        if raw.startswith("event: metric"):
                            data_str = raw.split("data: ", 1)[1]
                            data = json.loads(data_str)
                            if data.get("step") == 1 and data.get("key") == "train_loss":
                                new_step_seen = True
                                break
                if new_step_seen or time.monotonic() > deadline:
                    break
    finally:
        writer.join(timeout=2.0)
        server.stop()

    assert new_step_written.is_set(), "background writer did not run"
    assert new_step_seen, "live metric (step=1) did not arrive via SSE within 10 s"


def test_sse_replay_does_not_duplicate_into_live_tail(populated_paths, monkeypatch):
    """Replay emits each (key, step) once; the live tail must not re-emit
    the same steps on its first poll. Otherwise long-running monitor
    sessions accumulate duplicate points and the client-side ring buffer
    doubles up memory pressure.
    """
    from nnunetv2.tests.gui.fixtures.builders import build_tb_event_dir

    fold_dir = (
        populated_paths["results"]
        / "Dataset027_ACDC"
        / "nnUNetPlans__nnUNetTrainer__3d_fullres"
        / "fold_0"
    )
    tb_dir = fold_dir / "tensorboard"
    build_tb_event_dir(
        tb_dir,
        scalars={"train_loss": [(0, 1.0), (1, 0.7), (2, 0.5)]},
    )

    monkeypatch.setenv("nnUNet_raw", str(populated_paths["raw"]))
    monkeypatch.setenv("nnUNet_preprocessed", str(populated_paths["preprocessed"]))
    monkeypatch.setenv("nnUNet_results", str(populated_paths["results"]))

    from nnunetv2.gui.config import GuiConfig
    from nnunetv2.gui.server import create_app

    port = _pick_port()
    app = create_app(GuiConfig.from_env_and_args(host="127.0.0.1", port=port, token=None))
    server = _ServerThread(app, port)
    server.start()

    seen: list[tuple[str, int]] = []
    try:
        run_id = "Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0"
        url = f"http://127.0.0.1:{port}/sse/runs/{run_id}/events"
        # Short per-read timeout: once replay drains we expect the live tail
        # to stay silent (no new TB writes here), so the next read should
        # block until our timeout fires, at which point we move on. Without
        # this the connection would hang for the full 15s heartbeat interval.
        with requests.get(url, stream=True, timeout=(5, 3)) as r:
            assert r.status_code == 200
            buf = ""
            try:
                for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        buf += chunk
                        while "\n\n" in buf:
                            raw, buf = buf.split("\n\n", 1)
                            if raw.startswith("event: metric"):
                                data = json.loads(raw.split("data: ", 1)[1])
                                seen.append((data["key"], int(data["step"])))
            except requests.exceptions.ConnectionError:
                # Read timeout after the live tail goes idle — expected; means
                # the server didn't emit duplicates while we were waiting.
                pass
    finally:
        server.stop()

    train_loss_steps = [step for k, step in seen if k == "train_loss"]
    assert train_loss_steps == [0, 1, 2], (
        f"replay should emit each step exactly once; got {train_loss_steps}"
    )
