from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.jobs.queue import JobQueue
from nnunetv2.gui.jobs.reaper import attach_on_boot as reaper_attach
from nnunetv2.gui.routers import dashboard as dashboard_router
from nnunetv2.gui.routers import datasets as datasets_router
from nnunetv2.gui.routers import jobs as jobs_router
from nnunetv2.gui.routers import monitor as monitor_router
from nnunetv2.gui.routers import preprocess as preprocess_router
from nnunetv2.gui.routers import runs as runs_router
from nnunetv2.gui.routers import system as system_router
from nnunetv2.gui.routers import train as train_router
from nnunetv2.gui.services.sse import RunStreamHub
from nnunetv2.gui.state.discovery import reconcile


log = logging.getLogger("nnunetv2.gui")


def create_app(cfg: GuiConfig) -> FastAPI:
    init_db(cfg)
    reconcile(cfg)

    app = FastAPI(
        title="nnU-Net GUI",
        version=system_router.GUI_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.gui_config = cfg
    app.state.run_stream_hub = RunStreamHub()
    app.state.job_queue = JobQueue(cfg)

    @app.on_event("startup")
    async def _attach_jobs_on_boot() -> None:
        tasks = await reaper_attach(cfg)
        app.state._boot_reaper_tasks = tasks

    @app.on_event("shutdown")
    async def _shutdown_jobs() -> None:
        # Critical: do NOT terminate the subprocesses themselves.
        # Just stop tailing/reaping — they continue under their detached pgid.
        for t in getattr(app.state, "_boot_reaper_tasks", []):
            t.cancel()

    app.include_router(system_router.make_router())
    app.include_router(datasets_router.make_router())
    app.include_router(runs_router.make_router())
    app.include_router(dashboard_router.make_router())
    app.include_router(monitor_router.make_router())
    app.include_router(jobs_router.make_router())
    app.include_router(preprocess_router.make_router())
    app.include_router(train_router.make_router())

    is_loopback = cfg.host in ("127.0.0.1", "localhost", "::1")

    web_dir = Path(__file__).resolve().parent / "web"
    if (web_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    else:
        @app.get("/")
        def _placeholder() -> dict:
            return {
                "status": "placeholder",
                "message": (
                    "Frontend bundle not built yet. "
                    "Run `cd frontend && npm install && npm run build`."
                ),
            }

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled in %s: %s\n%s", request.url.path, exc, traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "kind": "internal_error",
                "message": str(exc) if is_loopback else "Internal server error",
                "retryable": False,
                "details": None,
            },
        )

    return app
