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


# Keys we copy from the GUI's process env into spawned children.
# Deliberately tight: anything not on this list (or matching one of
# JOB_ENV_PREFIXES below) is dropped so unrelated secrets — cloud
# keys, CI tokens, browser cookies, terminal mux state — never reach
# disk via state.db's env_json column or any API response.
JOB_ENV_KEYS: tuple[str, ...] = (
    # Process bootstrap
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "TMPDIR", "TEMP", "TMP",
    # Locale (matters for filesystem and Python text behaviour)
    "LANG", "LC_ALL", "LC_CTYPE",
    # GPU / accelerator
    "CUDA_VISIBLE_DEVICES", "CUDA_HOME", "CUDA_PATH",
    "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
    "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES",
    "PYTORCH_CUDA_ALLOC_CONF",
    # Threading / numerics
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    # Python runtime
    "PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV", "CONDA_PREFIX",
    # Windows essentials so the spawned process can find DLLs and tmp.
    "SYSTEMROOT", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "COMSPEC",
)

# Any env var whose name starts with these prefixes is copied through.
# `nnUNet_*` lets users tune nnUNet runtime behaviour (e.g. tb_logdir,
# n_proc_DA, image_every_n_epochs) without us having to enumerate
# every knob.
JOB_ENV_PREFIXES: tuple[str, ...] = ("nnUNet_",)


def job_env(cfg: GuiConfig) -> dict[str, str]:
    """Build the env passed to spawned nnUNet CLIs.

    Only an allowlist (``JOB_ENV_KEYS`` plus ``JOB_ENV_PREFIXES``) is
    copied from the GUI's process env into the child, then
    ``nnUNet_raw``/``nnUNet_preprocessed``/``nnUNet_results`` are
    overridden from ``GuiConfig`` so the spawned CLI resolves paths
    the same way the GUI did. The full process env is *not* copied:
    that would silently store unrelated secrets in ``state.db`` and
    surface them on /api/jobs.
    """
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in JOB_ENV_KEYS or any(k.startswith(p) for p in JOB_ENV_PREFIXES):
            env[k] = v
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
