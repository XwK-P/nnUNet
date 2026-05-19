"""Models = runs grouped by (dataset, plans, trainer, configuration)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.state.runs import RunFilter, list_runs


class Checkpoint(BaseModel):
    name: str
    path: str
    size_bytes: int


class ModelFold(BaseModel):
    fold: str
    output_folder: str
    status: str  # completed | abandoned | training | unknown
    checkpoints: list[Checkpoint]


class Model(BaseModel):
    id: str  # <dataset>/<plans>__<trainer>__<config>
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    folds: list[ModelFold]


def _model_id(dataset_id: str, plans_name: str, trainer_name: str, configuration: str) -> str:
    return f"{dataset_id}/{plans_name}__{trainer_name}__{configuration}"


def list_models(cfg: GuiConfig) -> list[Model]:
    """Group every discovered run by (dataset, plans, trainer, configuration)."""
    runs = list_runs(cfg, RunFilter())
    by_key: dict[str, list] = {}
    for r in runs:
        key = _model_id(r.dataset_id, r.plans_name, r.trainer_name, r.configuration)
        by_key.setdefault(key, []).append(r)
    out: list[Model] = []
    for key, group in sorted(by_key.items()):
        first = group[0]
        folds = [
            ModelFold(
                fold=r.fold,
                output_folder=r.output_folder,
                status=r.status,
                checkpoints=list_checkpoints(Path(r.output_folder)),
            )
            for r in sorted(group, key=lambda x: x.fold)
        ]
        out.append(Model(
            id=key,
            dataset_id=first.dataset_id,
            plans_name=first.plans_name,
            trainer_name=first.trainer_name,
            configuration=first.configuration,
            folds=folds,
        ))
    return out


def get_model(
    cfg: GuiConfig, dataset_id: str, plans_name: str, trainer_name: str, configuration: str,
) -> Optional[Model]:
    target = _model_id(dataset_id, plans_name, trainer_name, configuration)
    for m in list_models(cfg):
        if m.id == target:
            return m
    return None


def list_checkpoints(fold_dir: Path) -> list[Checkpoint]:
    if not fold_dir.is_dir():
        return []
    out: list[Checkpoint] = []
    for p in sorted(fold_dir.glob("checkpoint_*.pth")):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out.append(Checkpoint(name=p.name, path=str(p), size_bytes=size))
    return out
