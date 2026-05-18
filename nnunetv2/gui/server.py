from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.db import init_db
from nnunetv2.gui.routers import system as system_router


log = logging.getLogger("nnunetv2.gui")


def create_app(cfg: GuiConfig) -> FastAPI:
    init_db(cfg)

    app = FastAPI(
        title="nnU-Net GUI",
        version=system_router.GUI_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.gui_config = cfg

    app.include_router(system_router.make_router())

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
