from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GuiConfig:
    raw: Path
    preprocessed: Path
    results: Path
    host: str
    port: int
    token: Optional[str]

    @property
    def state_dir(self) -> Path:
        return self.results / ".nnunet_gui"

    @property
    def state_db(self) -> Path:
        return self.state_dir / "state.db"

    @classmethod
    def from_env_and_args(
        cls,
        *,
        host: str,
        port: int,
        token: Optional[str],
        raw_override: Optional[Path] = None,
        preprocessed_override: Optional[Path] = None,
        results_override: Optional[Path] = None,
    ) -> GuiConfig:
        if host not in ("127.0.0.1", "localhost", "::1") and not token:
            raise ValueError(
                f"Refusing to bind {host!r} without --token. "
                "Non-loopback hosts must provide a bearer token."
            )

        resolved = {
            "nnUNet_raw": raw_override or _from_env("nnUNet_raw"),
            "nnUNet_preprocessed": preprocessed_override or _from_env("nnUNet_preprocessed"),
            "nnUNet_results": results_override or _from_env("nnUNet_results"),
        }
        missing = [name for name, val in resolved.items() if val is None]
        if missing:
            raise EnvironmentError(
                f"Required env var(s) not set: {', '.join(missing)}"
            )

        return cls(
            raw=resolved["nnUNet_raw"],
            preprocessed=resolved["nnUNet_preprocessed"],
            results=resolved["nnUNet_results"],
            host=host,
            port=port,
            token=token,
        )


def _from_env(name: str) -> Optional[Path]:
    val = os.environ.get(name)
    return Path(val) if val else None


def job_env(cfg: GuiConfig) -> dict[str, str]:
    """Build the env passed to spawned nnUNet CLIs.

    nnunetv2/paths.py reads nnUNet_raw/preprocessed/results from
    ``os.environ`` at import time in the child process, so the GUI's
    own GuiConfig overrides (from ``nnUNetv2_gui --raw/--preprocessed
    /--results``) must be re-injected into the env before launching a
    job. Otherwise the child resolves paths from the unmodified parent
    env, which may be missing or stale relative to what the GUI itself
    used to find datasets/runs/results.
    """
    env = os.environ.copy()
    env["nnUNet_raw"] = str(cfg.raw)
    env["nnUNet_preprocessed"] = str(cfg.preprocessed)
    env["nnUNet_results"] = str(cfg.results)
    return env


# Allowlist of nnUNet-related env vars surfaced in the Settings UI.
EDITABLE_ENV_VARS: tuple[str, ...] = (
    "nnUNet_raw",
    "nnUNet_preprocessed",
    "nnUNet_results",
    "nnUNet_def_n_proc",
    "nnUNet_n_proc_DA",
    "nnUNet_tb_logdir",
    "nnUNet_wandb_enabled",
    "nnUNet_tb_image_every_n_epochs",
    "nnUNet_compile",
)
