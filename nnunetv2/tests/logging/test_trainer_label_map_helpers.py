"""Unit tests for the small label-map helpers used by the TB image logging hook.

These exercise pure tensor logic without instantiating a full trainer (which would require
a dataset, plans, GPU, etc.).
"""
import torch

from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer


def test_onehot_to_highest_active_label_2d():
    # (B=1, C=3, H=2, W=2)
    one_hot = torch.tensor([[
        [[0, 1], [0, 0]],  # region 0 active at (0,1)
        [[1, 1], [0, 0]],  # region 1 active at (0,0) and (0,1)
        [[0, 0], [1, 0]],  # region 2 active at (1,0)
    ]], dtype=torch.long)

    out = nnUNetTrainer._onehot_to_highest_active_label(one_hot)

    assert out.shape == (1, 2, 2)
    # (0,0): only region 1 active -> label 2
    # (0,1): regions 0 and 1 active -> highest active = label 2
    # (1,0): only region 2 active -> label 3
    # (1,1): no region active -> label 0
    assert out[0, 0, 0].item() == 2
    assert out[0, 0, 1].item() == 2
    assert out[0, 1, 0].item() == 3
    assert out[0, 1, 1].item() == 0


def test_onehot_to_highest_active_label_3d():
    # (B=1, C=2, D=2, H=2, W=2) - all-zero except one voxel in region 1
    one_hot = torch.zeros((1, 2, 2, 2, 2), dtype=torch.long)
    one_hot[0, 1, 1, 0, 1] = 1

    out = nnUNetTrainer._onehot_to_highest_active_label(one_hot)

    assert out.shape == (1, 2, 2, 2)
    assert out[0, 1, 0, 1].item() == 2  # region 1 -> label 2 (1-indexed)
    # All other voxels are background
    assert (out == 0).sum().item() == 7


def test_onehot_to_highest_active_label_all_background():
    one_hot = torch.zeros((2, 3, 4, 4), dtype=torch.long)
    out = nnUNetTrainer._onehot_to_highest_active_label(one_hot)
    assert out.shape == (2, 4, 4)
    assert (out == 0).all().item()
