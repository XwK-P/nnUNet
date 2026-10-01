"""Cross-run aggregation: metric histories + summary stats."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.runs import get_run


class MetricPoint(BaseModel):
    step: int
    value: float
    wall_time: Optional[float] = None


class RunMetrics(BaseModel):
    run_id: str
    series: dict[str, list[MetricPoint]]  # metric key -> ordered points


class RunSummary(BaseModel):
    run_id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    status: str
    foreground_mean_dice: Optional[float] = None
    per_class_dice: Optional[dict[str, float]] = None


def gather_run_metrics(
    cfg: GuiConfig,
    run_ids: list[str],
    *,
    metric_keys: Optional[list[str]] = None,
) -> list[RunMetrics]:
    """Read tensorboard events for each run id; return per-run metric series.

    Uses the existing Phase 3 `read_all_metrics` helper for a one-shot scalar read.
    Unknown / non-existent runs return `RunMetrics(run_id=..., series={})`.
    """
    from nnunetv2.gui.services.tb_tailer import read_all_metrics

    out: list[RunMetrics] = []
    for rid in run_ids:
        run = get_run(cfg, rid)
        series: dict[str, list[MetricPoint]] = {}
        if run is not None:
            event_dir = Path(run.output_folder) / "tensorboard"
            if event_dir.is_dir():
                try:
                    for ev in read_all_metrics(event_dir):
                        key = ev.get("key")
                        if metric_keys is not None and key not in metric_keys:
                            continue
                        series.setdefault(key, []).append(
                            MetricPoint(step=int(ev["step"]),
                                        value=float(ev["value"]),
                                        wall_time=ev.get("wall_time"))
                        )
                except Exception:  # pragma: no cover - degraded mode
                    series = {}
            # Ensure deterministic order by step
            for k, pts in series.items():
                pts.sort(key=lambda p: p.step)
        out.append(RunMetrics(run_id=rid, series=series))
    return out


def gather_run_summaries(cfg: GuiConfig, run_ids: list[str]) -> list[RunSummary]:
    """Read each run's row + validation/summary.json into a flat RunSummary."""
    out: list[RunSummary] = []
    for rid in run_ids:
        run = get_run(cfg, rid)
        if run is None:
            # Synthesize a placeholder so the caller sees a 1:1 alignment.
            out.append(RunSummary(
                run_id=rid, dataset_id="?", plans_name="?", trainer_name="?",
                configuration="?", fold="?", status="unknown",
            ))
            continue
        fg, per_class = _read_summary(Path(run.output_folder))
        out.append(RunSummary(
            run_id=run.id,
            dataset_id=run.dataset_id,
            plans_name=run.plans_name,
            trainer_name=run.trainer_name,
            configuration=run.configuration,
            fold=run.fold,
            status=run.status,
            foreground_mean_dice=fg,
            per_class_dice=per_class,
        ))
    return out


def _finite_float(x: object) -> Optional[float]:
    """Return float(x) if it's a finite number, else None.

    nnUNet writes NaN to summary.json when a class is absent in a run
    (and Inf in degenerate cases); FastAPI's JSON encoder rejects
    non-finite floats and would 500 the entire compare response. Coerce
    those to None so the field renders as missing rather than killing
    the request.
    """
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _read_summary(fold_dir: Path) -> tuple[Optional[float], Optional[dict[str, float]]]:
    fp = fold_dir / "validation" / "summary.json"
    if not fp.is_file():
        return None, None
    try:
        data = json.loads(fp.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None
    fg_block = data.get("foreground_mean") or {}
    fg = _finite_float(fg_block.get("Dice")) if isinstance(fg_block, dict) else None
    per_class: dict[str, float] = {}
    mean_block = data.get("mean") or {}
    if isinstance(mean_block, dict):
        for label, metrics in mean_block.items():
            if isinstance(metrics, dict) and "Dice" in metrics:
                v = _finite_float(metrics["Dice"])
                if v is not None:
                    per_class[str(label)] = v
    return fg, (per_class or None)
