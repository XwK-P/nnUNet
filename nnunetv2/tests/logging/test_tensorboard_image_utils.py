import numpy as np
import pytest

from nnunetv2.training.logging.tensorboard_image_utils import render_sample


def test_render_sample_2d_shape_and_range():
    data = np.random.randn(1, 16, 24).astype(np.float32)  # C, H, W
    target = np.zeros((16, 24), dtype=np.int64)
    target[4:10, 6:14] = 1
    pred = np.zeros((16, 24), dtype=np.int64)
    pred[5:11, 7:15] = 1

    out = render_sample(data, target, pred)

    assert out.shape == (3, 16, 24 * 3), f"unexpected shape {out.shape}"
    assert out.dtype == np.float32
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_render_sample_3d_uses_mid_axial_slice():
    data = np.random.randn(1, 8, 16, 24).astype(np.float32)  # C, D, H, W
    target = np.zeros((8, 16, 24), dtype=np.int64)
    target[4, 4:10, 6:14] = 1  # only mid slice has GT
    pred = np.zeros((8, 16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)

    assert out.shape == (3, 16, 24 * 3)
    assert out.dtype == np.float32


def test_render_sample_region_based_target_collapsed_via_argmax():
    data = np.random.randn(1, 16, 24).astype(np.float32)
    # Region-based: target is (num_regions, H, W) one-hot-ish
    target = np.zeros((3, 16, 24), dtype=np.float32)
    target[1, 4:10, 6:14] = 1.0
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)


def test_render_sample_all_background_is_safe():
    data = np.random.randn(1, 16, 24).astype(np.float32)
    target = np.zeros((16, 24), dtype=np.int64)
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)
    # GT and pred panels should equal the input panel exactly when no overlay
    left = out[:, :, :24]
    mid = out[:, :, 24:48]
    right = out[:, :, 48:]
    np.testing.assert_allclose(mid, left)
    np.testing.assert_allclose(right, left)


def test_render_sample_constant_input_does_not_divide_by_zero():
    data = np.zeros((1, 16, 24), dtype=np.float32)
    target = np.zeros((16, 24), dtype=np.int64)
    pred = np.zeros((16, 24), dtype=np.int64)

    out = render_sample(data, target, pred)
    assert out.shape == (3, 16, 24 * 3)
    assert np.isfinite(out).all()
