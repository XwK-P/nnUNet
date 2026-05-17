from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_REQUIRED_ENV = ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results")


def _resolve_required(name: str, override: Optional[Path]) -> Path:
    if override is not None:
        return override
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(f"Required env var '{name}' is not set")
    return Path(val)


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
    ) -> "GuiConfig":
        if host not in ("127.0.0.1", "localhost", "::1") and not token:
            raise ValueError(
                f"Refusing to bind {host!r} without --token. "
                "Non-loopback hosts must provide a bearer token."
            )

        overrides = {
            "nnUNet_raw": raw_override,
            "nnUNet_preprocessed": preprocessed_override,
            "nnUNet_results": results_override,
        }
        missing = [
            name for name, ovr in overrides.items()
            if ovr is None and not os.environ.get(name)
        ]
        if missing:
            raise EnvironmentError(
                f"Required env var(s) not set: {', '.join(missing)}"
            )

        return cls(
            raw=_resolve_required("nnUNet_raw", raw_override),
            preprocessed=_resolve_required("nnUNet_preprocessed", preprocessed_override),
            results=_resolve_required("nnUNet_results", results_override),
            host=host,
            port=port,
            token=token,
        )
