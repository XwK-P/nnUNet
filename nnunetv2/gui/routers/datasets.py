"""Datasets router."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from nnunetv2.gui.state.cases import Case, list_cases_for_dataset
from nnunetv2.gui.state.datasets import (
    Dataset, list_datasets, get_dataset, fingerprint_dict,
)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/datasets", tags=["datasets"])

    @router.get("", response_model=list[Dataset])
    def list_all(request: Request) -> list[Dataset]:
        return list_datasets(request.app.state.gui_config)

    @router.get("/{dataset_id}", response_model=Dataset)
    def get_one(dataset_id: str, request: Request) -> Dataset:
        d = get_dataset(request.app.state.gui_config, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        return d

    @router.get("/{dataset_id}/plans")
    def get_plans(dataset_id: str, request: Request) -> dict:
        cfg = request.app.state.gui_config
        d = get_dataset(cfg, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        # Look for plans.json under any results subfolder for this dataset (any run).
        results_dataset_dir = Path(cfg.results) / dataset_id
        if results_dataset_dir.is_dir():
            for run_dir in results_dataset_dir.iterdir():
                plans_path = run_dir / "plans.json"
                if plans_path.is_file():
                    try:
                        return json.loads(plans_path.read_text())
                    except json.JSONDecodeError:
                        continue
        raise HTTPException(status_code=404, detail="No plans.json found for this dataset")

    @router.get("/{dataset_id}/fingerprint")
    def get_fingerprint(dataset_id: str, request: Request) -> dict:
        cfg = request.app.state.gui_config
        d = get_dataset(cfg, dataset_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        fp = fingerprint_dict(d)
        if fp is None:
            raise HTTPException(status_code=404, detail="No fingerprint available")
        return fp

    @router.get("/{dataset_id}/cases", response_model=list[Case])
    def get_cases(dataset_id: str, request: Request) -> list[Case]:
        cfg = request.app.state.gui_config
        if get_dataset(cfg, dataset_id) is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id!r} not found")
        return list_cases_for_dataset(cfg, dataset_id)

    return router
