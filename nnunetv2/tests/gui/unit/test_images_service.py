from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from nnunetv2.gui.services.images import (
    open_nifti, slice_to_png, get_slice_png_cached, clear_slice_cache,
)


@pytest.fixture
def nifti_file(tmp_path):
    from nnunetv2.tests.gui.fixtures.builders import build_case_nifti
    return build_case_nifti(tmp_path, "case_001_0000.nii.gz", shape=(8, 16, 32))


def test_open_nifti_returns_array_and_spacing(nifti_file):
    arr, spacing = open_nifti(nifti_file)
    assert arr.shape == (8, 16, 32)
    assert arr.dtype.kind == "f"
    assert len(spacing) == 3


def test_slice_to_png_axial(nifti_file):
    arr, _ = open_nifti(nifti_file)
    png_bytes = slice_to_png(arr, axis=0, index=4)
    img = Image.open(io.BytesIO(png_bytes))
    # Axis 0 with shape (8,16,32) -> 16x32 image
    assert img.size == (32, 16)


def test_slice_to_png_out_of_range_clamps(nifti_file):
    arr, _ = open_nifti(nifti_file)
    # Index past end should clamp to last valid slice, not crash
    png_bytes = slice_to_png(arr, axis=0, index=999)
    # Must be a real PNG (signature) — exact size depends on slice content
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_slice_to_png_respects_window(nifti_file):
    arr, _ = open_nifti(nifti_file)
    # Same slice, different windows → different PNGs
    a = slice_to_png(arr, axis=0, index=0, window=(0, 100))
    b = slice_to_png(arr, axis=0, index=0, window=(0, 1000))
    assert a != b


def test_lru_cache_returns_same_bytes(nifti_file):
    clear_slice_cache()
    a = get_slice_png_cached(str(nifti_file), axis=0, index=0, window=None)
    b = get_slice_png_cached(str(nifti_file), axis=0, index=0, window=None)
    assert a is b  # cache returns the exact same bytes object


def test_slice_to_png_accepts_2d_array():
    """2D nnUNet datasets (and 2D probability maps) reach slice_to_png as
    rank-2 arrays. The function must render them instead of 500'ing the
    image preview endpoint.
    """
    arr = np.arange(16 * 8, dtype=np.float32).reshape(16, 8)
    # axis=0 should give us the first column; axis=2 (the promoted singleton)
    # should give us the whole image.
    png0 = slice_to_png(arr, axis=0, index=4)
    png_last = slice_to_png(arr, axis=2, index=0)
    assert png0[:8] == b"\x89PNG\r\n\x1a\n"
    assert png_last[:8] == b"\x89PNG\r\n\x1a\n"


def test_slice_to_png_rejects_other_ranks():
    bad = np.zeros((2, 2, 2, 2), dtype=np.float32)
    with pytest.raises(ValueError, match="2-D or 3-D"):
        slice_to_png(bad, axis=0, index=0)


def test_lru_cache_bounded(nifti_file):
    clear_slice_cache()
    # Fill with > 256 entries; the first should evict.
    for i in range(260):
        get_slice_png_cached(str(nifti_file), axis=0, index=i % 8, window=(float(i), float(i + 1)))
    # Total cached entries should not exceed the bound (default 256)
    from nnunetv2.gui.services.images import slice_cache_size
    assert slice_cache_size() <= 256
