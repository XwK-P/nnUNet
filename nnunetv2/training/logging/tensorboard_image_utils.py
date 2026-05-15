"""Helpers for rendering nnU-Net validation samples for TensorBoard logging.

Pure numpy/matplotlib — no torch or nnU-Net imports. Produces a single
``(3, H, 3*W)`` float32 array in [0, 1] containing
``[input | input + GT overlay | input + pred overlay]``.
"""
from __future__ import annotations

import matplotlib
import numpy as np

_OVERLAY_ALPHA = 0.4
_COLORMAP = matplotlib.colormaps["tab10"]


def _to_label_map(arr: np.ndarray, spatial_ndim: int) -> np.ndarray:
    """Collapse a region-based multi-channel target to a single-channel label map.

    A leading channel of size 1 is treated as a redundant dim (squeezed) rather
    than argmaxed, which would silently zero everything out.
    """
    if arr.ndim == spatial_ndim + 1 and arr.shape[0] > 1:
        return np.argmax(arr, axis=0).astype(np.int64)
    if arr.ndim == spatial_ndim + 1 and arr.shape[0] == 1:
        return arr[0].astype(np.int64)
    return arr.astype(np.int64)


def _mid_axial(arr: np.ndarray) -> np.ndarray:
    """Return the central depth slice of a 3D array. No-op for 2D."""
    if arr.ndim == 3:  # D, H, W
        return arr[arr.shape[0] // 2]
    return arr


def _normalize_to_unit(slice_2d: np.ndarray) -> np.ndarray:
    lo = float(slice_2d.min())
    hi = float(slice_2d.max())
    if hi - lo < 1e-8:
        return np.zeros_like(slice_2d, dtype=np.float32)
    return ((slice_2d - lo) / (hi - lo)).astype(np.float32)


def _grayscale_to_rgb(slice_2d: np.ndarray) -> np.ndarray:
    """Convert (H, W) -> (3, H, W)."""
    return np.stack([slice_2d, slice_2d, slice_2d], axis=0)


def _overlay(rgb_chw: np.ndarray, label_map: np.ndarray) -> np.ndarray:
    """Alpha-blend a categorical color overlay onto an RGB image. Background label 0 is transparent."""
    out = rgb_chw.copy()
    unique_labels = np.unique(label_map)
    for lbl in unique_labels:
        if lbl == 0:
            continue
        # tab10 has 10 colors; classes >= 10 wrap around. Acceptable: nnU-Net rarely has >10 fg classes,
        # and a colliding color is better than a hard cap or a noisier colormap.
        color = np.array(_COLORMAP(int(lbl) % 10)[:3], dtype=np.float32)  # (3,)
        mask = (label_map == lbl)
        for c in range(3):
            out[c][mask] = (1 - _OVERLAY_ALPHA) * out[c][mask] + _OVERLAY_ALPHA * color[c]
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def render_sample(data: np.ndarray, target: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """Render a single sample as a 3-panel (input | GT | pred) image.

    Args:
        data: Input volume/image, shape ``(C, H, W)`` for 2D or ``(C, D, H, W)`` for 3D.
              Only channel 0 is rendered.
        target: Ground truth labels. Either ``(H, W)`` / ``(D, H, W)`` integer label map,
                or a region-based one-hot-like array with an extra leading channel dim.
        pred: Predicted label map, same shape conventions as ``target`` (without channel dim).

    Returns:
        ``(3, H, 3*W)`` float32 array in [0, 1].
    """
    # Pick channel 0 of input.
    data_ch0 = data[0]  # (H, W) or (D, H, W)
    spatial_ndim = data_ch0.ndim  # 2 or 3

    target_lm = _to_label_map(target, spatial_ndim)
    pred_lm = _to_label_map(pred, spatial_ndim)

    data_slice = _mid_axial(data_ch0)
    target_slice = _mid_axial(target_lm)
    pred_slice = _mid_axial(pred_lm)

    base = _normalize_to_unit(data_slice)            # (H, W)
    base_rgb = _grayscale_to_rgb(base)               # (3, H, W)
    gt_rgb = _overlay(base_rgb, target_slice)        # (3, H, W)
    pred_rgb = _overlay(base_rgb, pred_slice)        # (3, H, W)

    panel = np.concatenate([base_rgb, gt_rgb, pred_rgb], axis=2)  # (3, H, 3*W)
    return panel.astype(np.float32)
