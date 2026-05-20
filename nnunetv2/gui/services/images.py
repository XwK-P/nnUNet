"""On-demand NIfTI slice decoding for the GUI image viewer.

Returns PNG-encoded slices with an LRU cache bounded by item count.
No disk cache — the cache is per-process and survives only as long as the
server. Volumes themselves are not cached; only encoded slice PNGs are.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import nibabel as nib
from PIL import Image


SLICE_CACHE_MAXSIZE = 256


def volume_shape(path: Path | str) -> tuple[int, int, int]:
    """Return the (d0, d1, d2) shape of `path` without loading voxels.

    nibabel reads only the header — much cheaper than open_nifti when the
    caller just wants axis lengths (e.g. to bound the slice slider).
    """
    img = nib.load(str(path))
    shape = img.shape
    if len(shape) < 3:
        # Pad 2D images to a 3-tuple so downstream slider logic doesn't
        # have to special-case them.
        return (int(shape[0]), int(shape[1]) if len(shape) > 1 else 1, 1)
    return (int(shape[0]), int(shape[1]), int(shape[2]))


def open_nifti(path: Path | str) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Open `path` with nibabel and return (data, spacing).

    Data is returned as a float32 numpy array regardless of on-disk dtype.
    Spacing is (sx, sy, sz) in mm.
    """
    img = nib.load(str(path))
    arr = np.asarray(img.dataobj, dtype=np.float32)
    zooms = img.header.get_zooms()[:3]
    spacing = (float(zooms[0]), float(zooms[1]), float(zooms[2]))
    return arr, spacing


def slice_to_png(
    arr: np.ndarray,
    *,
    axis: int,
    index: int,
    window: Optional[tuple[float, float]] = None,
) -> bytes:
    """Take a 2-D slice from `arr` along `axis` at `index` and encode as PNG.

    `window` is (low, high) intensity to map to (0, 255); when None, scale
    to the slice's min/max range.
    """
    if arr.ndim != 3:
        raise ValueError(f"expected 3-D array, got shape {arr.shape}")
    idx = max(0, min(arr.shape[axis] - 1, int(index)))
    if axis == 0:
        sl = arr[idx, :, :]
    elif axis == 1:
        sl = arr[:, idx, :]
    elif axis == 2:
        sl = arr[:, :, idx]
    else:
        raise ValueError(f"axis must be 0, 1, or 2; got {axis}")
    if window is not None:
        lo, hi = window
    else:
        lo, hi = float(sl.min()), float(sl.max())
    if hi <= lo:
        norm = np.zeros_like(sl, dtype=np.uint8)
    else:
        norm = np.clip(((sl - lo) / (hi - lo)) * 255.0, 0, 255).astype(np.uint8)
    img = Image.fromarray(norm, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Cache uses a key of (str(path), axis, index, window) so it is hashable.
@lru_cache(maxsize=SLICE_CACHE_MAXSIZE)
def _cached(path: str, axis: int, index: int, window: Optional[tuple[float, float]]) -> bytes:
    arr, _ = open_nifti(Path(path))
    return slice_to_png(arr, axis=axis, index=index, window=window)


def get_slice_png_cached(
    path: str,
    *,
    axis: int,
    index: int,
    window: Optional[tuple[float, float]] = None,
) -> bytes:
    return _cached(path, axis, index, window)


def clear_slice_cache() -> None:
    _cached.cache_clear()


def slice_cache_size() -> int:
    return _cached.cache_info().currsize
