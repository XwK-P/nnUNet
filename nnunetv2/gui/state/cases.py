"""Case discovery for raw datasets (Dataset<XXX>_<Name>/imagesTr)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig

CHANNEL_RE = re.compile(r"^(.+)_(\d{4})\.(.+)$")

# Fallback suffix list when dataset.json's file_ending is missing or malformed.
# Order doesn't matter for correctness here — we just need to peel off the
# extension to recover the case id.
_KNOWN_LABEL_SUFFIXES = (
    ".nii.gz", ".nii", ".nrrd", ".mha", ".mhd",
    ".tif", ".tiff", ".png", ".npy", ".npz",
)


def _read_file_ending(raw_dir: Path) -> Optional[str]:
    ds_json = raw_dir / "dataset.json"
    if not ds_json.is_file():
        return None
    try:
        data = json.loads(ds_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    fe = data.get("file_ending")
    if isinstance(fe, str) and fe.startswith("."):
        return fe
    return None


def _label_stem(name: str, file_ending: Optional[str]) -> str:
    """Strip the dataset's file_ending (or a known label suffix) from
    `name` and return the case id. Falls back to ``name`` unchanged so
    dotted case ids like ``patient.v1`` survive even when no suffix can
    be matched — splitting at the first dot would silently truncate
    them and break label attachment.
    """
    lower = name.lower()
    if file_ending and lower.endswith(file_ending.lower()):
        return name[: -len(file_ending)]
    for suf in _KNOWN_LABEL_SUFFIXES:
        if lower.endswith(suf):
            return name[: -len(suf)]
    return name


class Case(BaseModel):
    id: str
    dataset_id: str
    channels: dict[str, str]   # channel_index_str -> absolute file path
    label_path: Optional[str]


def list_cases_for_dataset(cfg: GuiConfig, dataset_id: str) -> list[Case]:
    raw_dir = Path(cfg.raw) / dataset_id
    images_tr = raw_dir / "imagesTr"
    labels_tr = raw_dir / "labelsTr"
    if not images_tr.is_dir():
        return []
    cases: dict[str, dict[str, str]] = {}
    for f in sorted(images_tr.iterdir()):
        if not f.is_file():
            continue
        m = CHANNEL_RE.match(f.name)
        if not m:
            continue
        case_id = m.group(1)
        chan = m.group(2).lstrip("0") or "0"
        cases.setdefault(case_id, {})[chan] = str(f)
    file_ending = _read_file_ending(raw_dir)
    out: list[Case] = []
    for case_id, channels in sorted(cases.items()):
        label = None
        if labels_tr.is_dir():
            for f in labels_tr.iterdir():
                if f.is_file() and _label_stem(f.name, file_ending) == case_id:
                    label = str(f)
                    break
        out.append(Case(id=case_id, dataset_id=dataset_id, channels=channels, label_path=label))
    return out
