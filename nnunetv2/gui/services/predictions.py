"""Helpers for resolving and rendering prediction files.

Both the runs router (run-scoped previews) and the predict router
(arbitrary-folder previews triggered from the Predict page metrics
table) need to: enumerate prediction files in a folder, dedupe by
stem with a suffix preference (e.g. .nii.gz wins over .nii), and
dispatch decoding by file format (NIfTI / PNG passthrough / TIFF
re-encode / unsupported -> 415). Centralising those rules avoids
drift between the two endpoints.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import Response

from nnunetv2.gui.services.images import get_slice_png_cached


# Suffixes recognised as prediction files. The tuple order is also the
# preference ranking when multiple formats share a stem.
PRED_SUFFIXES = (".nii.gz", ".nii", ".nrrd", ".mha", ".tif", ".tiff", ".png")


def is_prediction_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suf) for suf in PRED_SUFFIXES)


def strip_pred_suffix(name: str) -> str:
    lower = name.lower()
    for suf in PRED_SUFFIXES:
        if lower.endswith(suf):
            return name[: -len(suf)]
    return name.split(".")[0]


def suffix_rank(name: str) -> int:
    """Index into PRED_SUFFIXES (lower is preferred). Non-prediction
    names rank last so they never beat a real prediction file.
    """
    lower = name.lower()
    for i, suf in enumerate(PRED_SUFFIXES):
        if lower.endswith(suf):
            return i
    return len(PRED_SUFFIXES)


def find_prediction_for_case(pred_dir: Path, case_id: str) -> Optional[Path]:
    """Return the preferred prediction file for ``case_id`` under
    ``pred_dir``, or ``None`` if nothing matches. Lower suffix rank
    wins; ties are broken by filename for determinism.
    """
    if not pred_dir.is_dir():
        return None
    candidates = [
        f for f in pred_dir.iterdir()
        if f.is_file()
        and is_prediction_file(f.name)
        and strip_pred_suffix(f.name) == case_id
    ]
    candidates.sort(key=lambda f: (suffix_rank(f.name), f.name))
    return candidates[0] if candidates else None


def render_prediction_preview(
    match: Path,
    *,
    axis: int,
    slice: int,
    window: Optional[tuple[float, float]],
) -> Response:
    """Decode the prediction at ``match`` and return a PNG-bytes
    Response, dispatching by suffix:

    * .nii / .nii.gz -> existing NIfTI loader + slice_to_png
    * .png           -> served verbatim (axis/slice/window ignored)
    * .tif / .tiff   -> PIL multi-frame, ``slice`` selects frame, PNG re-encoded
    * else (.nrrd, .mha, ...) -> 415, since no decoder is wired up yet

    Raises HTTPException(415) for unsupported formats so callers get a
    clear "not supported" status instead of a NIfTI 500.
    """
    name_lower = match.name.lower()
    if name_lower.endswith((".nii.gz", ".nii")):
        png = get_slice_png_cached(str(match), axis=axis, index=slice, window=window)
        return Response(content=png, media_type="image/png")
    if name_lower.endswith(".png"):
        return Response(content=match.read_bytes(), media_type="image/png")
    if name_lower.endswith((".tif", ".tiff")):
        from PIL import Image
        with Image.open(str(match)) as img:
            n_frames = getattr(img, "n_frames", 1)
            frame = max(0, min(n_frames - 1, int(slice)))
            img.seek(frame)
            buf = io.BytesIO()
            img.convert("L").save(buf, format="PNG")
            return Response(content=buf.getvalue(), media_type="image/png")
    raise HTTPException(
        status_code=415,
        detail=f"Preview not supported for {match.suffix!r}",
    )
