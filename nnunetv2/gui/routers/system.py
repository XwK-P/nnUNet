from __future__ import annotations

import logging
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.config import EDITABLE_ENV_VARS


GUI_VERSION = "0.1.0"

# In-memory log level for the GUI server. Survives only for the process
# lifetime — settings UI displays this and the PUT route updates it.
_LOG_LEVEL: dict[str, str] = {"level": "INFO"}


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

    @router.get("/gpu")
    def gpu() -> list[dict]:
        from nnunetv2.gui.services.gpu import gpu_info
        return gpu_info()

    @router.get("/env")
    def env() -> dict:
        return {
            "vars": [
                {
                    "name": name,
                    "value": os.environ.get(name),
                    "editable": True,
                }
                for name in EDITABLE_ENV_VARS
            ],
        }

    @router.get("/log_level")
    def get_log_level() -> dict:
        return {"level": _LOG_LEVEL["level"]}

    @router.put("/log_level")
    def put_log_level(payload: dict) -> dict:
        level = (payload.get("level") or "").upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise HTTPException(status_code=400, detail="invalid level")
        _LOG_LEVEL["level"] = level
        logging.getLogger().setLevel(level)
        return {"level": _LOG_LEVEL["level"]}

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
