from __future__ import annotations

from pathlib import Path

from nnunetv2.tests.gui.fixtures.builders import build_minimal_niigz


def test_build_minimal_niigz_writes_valid_file(tmp_path: Path):
    p = build_minimal_niigz(tmp_path / "case_001_0000.nii.gz", shape=(4, 4, 4))
    assert p.is_file()
    assert p.stat().st_size > 0
    # Confirm nibabel can open it back
    import nibabel as nib
    img = nib.load(str(p))
    arr = img.get_fdata()
    assert arr.shape == (4, 4, 4)
