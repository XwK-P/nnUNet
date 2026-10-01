"""Datasets router."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from nnunetv2.gui.services.images import get_slice_png_cached
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

    @router.get("/{dataset_id}/cases/{case_id}/preview")
    def case_preview(
        dataset_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0, channel: int = 0,
        window_lo: Optional[float] = None, window_hi: Optional[float] = None,
    ) -> Response:
        cfg = request.app.state.gui_config
        cases = list_cases_for_dataset(cfg, dataset_id)
        match = next((c for c in cases if c.id == case_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
        chan_key = str(channel)
        if chan_key not in match.channels:
            raise HTTPException(status_code=404, detail=f"Channel {channel} not found")
        window = (window_lo, window_hi) if (window_lo is not None and window_hi is not None) else None
        png = get_slice_png_cached(match.channels[chan_key], axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")

    @router.get("/{dataset_id}/cases/{case_id}/shape")
    def case_shape(dataset_id: str, case_id: str, request: Request) -> dict:
        """Return the (d0, d1, d2) shape of the case's channel-0 volume.

        Frontend uses this to bound the slice slider per axis. Reads only
        the NIfTI header so it's cheap to call on case selection.
        """
        from nnunetv2.gui.services.images import volume_shape
        cfg = request.app.state.gui_config
        cases = list_cases_for_dataset(cfg, dataset_id)
        match = next((c for c in cases if c.id == case_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
        if not match.channels:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} has no channels")
        # Shape is volume geometry — same for every channel.
        chan_path = next(iter(sorted(match.channels.items())))[1]
        d0, d1, d2 = volume_shape(chan_path)
        return {"shape": [d0, d1, d2]}

    @router.get("/{dataset_id}/cases/{case_id}/labels")
    def case_labels(
        dataset_id: str, case_id: str, request: Request,
        axis: int = 0, slice: int = 0,
    ) -> Response:
        cfg = request.app.state.gui_config
        cases = list_cases_for_dataset(cfg, dataset_id)
        match = next((c for c in cases if c.id == case_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
        if not match.label_path:
            raise HTTPException(status_code=404, detail=f"No label for case {case_id!r}")
        png = get_slice_png_cached(match.label_path, axis=axis, index=slice, window=None)
        return Response(content=png, media_type="image/png")

    return router
