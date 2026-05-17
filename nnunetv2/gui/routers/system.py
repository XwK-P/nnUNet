from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastapi import APIRouter, Request


GUI_VERSION = "0.1.0"


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system"])

    @router.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @router.get("/version")
    def version() -> dict:
        try:
            nnunet_version = _pkg_version("nnunetv2")
        except PackageNotFoundError:
            nnunet_version = "unknown"
        return {"nnunetv2": nnunet_version, "gui": GUI_VERSION}

    @router.get("/diag")
    def diag(request: Request) -> dict:
        cfg = request.app.state.gui_config
        return {
            "gui": GUI_VERSION,
            "python": sys.version,
            "platform": platform.platform(),
            "host": cfg.host,
            "port": cfg.port,
            "paths": {
                "raw": str(cfg.raw),
                "preprocessed": str(cfg.preprocessed),
                "results": str(cfg.results),
                "state_db": str(cfg.state_db),
            },
        }

    return router
