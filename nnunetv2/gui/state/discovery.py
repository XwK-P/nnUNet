"""Filesystem scanners that turn nnU-Net on-disk artifacts into model records."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DATASET_DIR_RE = re.compile(r"^Dataset(\d{3})_(.+)$")


@dataclass(frozen=True)
class DiscoveredDataset:
    id: str
    dataset_id_int: Optional[int]
    name: Optional[str]
    raw_path: str
    case_count: int
    modality_count: int


def scan_raw_datasets(raw_root: Path) -> list[DiscoveredDataset]:
    """Walk `raw_root` and return one DiscoveredDataset per Dataset<XXX>_<Name> dir."""
    if not raw_root.is_dir():
        return []
    out: list[DiscoveredDataset] = []
    for entry in sorted(raw_root.iterdir()):
        if not entry.is_dir():
            continue
        m = DATASET_DIR_RE.match(entry.name)
        if not m:
            continue
        ds = _read_one_raw(entry, m)
        out.append(ds)
    return out


def _read_one_raw(folder: Path, name_match: re.Match[str]) -> DiscoveredDataset:
    dataset_id_int = int(name_match.group(1))
    name = name_match.group(2)
    cases, modalities = _count_cases_and_modalities(folder)
    return DiscoveredDataset(
        id=folder.name,
        dataset_id_int=dataset_id_int,
        name=name,
        raw_path=str(folder),
        case_count=cases,
        modality_count=modalities,
    )


def _count_cases_and_modalities(folder: Path) -> tuple[int, int]:
    # Prefer dataset.json if present (authoritative for channels)
    modality_count = 0
    ds_json = folder / "dataset.json"
    if ds_json.is_file():
        try:
            data = json.loads(ds_json.read_text())
            channels = data.get("channel_names") or {}
            modality_count = len(channels)
        except (json.JSONDecodeError, OSError):
            modality_count = 0

    images_tr = folder / "imagesTr"
    if not images_tr.is_dir():
        return 0, modality_count
    case_ids: set[str] = set()
    for f in images_tr.iterdir():
        # Pattern: <case>_<NNNN>.<ext-or-extensions>
        stem = f.name.split(".")[0]  # strip multi-suffix .nii.gz
        # last "_NNNN" is the modality index
        m = re.match(r"^(.+)_(\d{4})$", stem)
        if not m:
            continue
        case_ids.add(m.group(1))
    return len(case_ids), modality_count
