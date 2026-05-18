"""Case discovery for raw datasets (Dataset<XXX>_<Name>/imagesTr)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nnunetv2.gui.config import GuiConfig

CHANNEL_RE = re.compile(r"^(.+)_(\d{4})\.(.+)$")


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
    out: list[Case] = []
    for case_id, channels in sorted(cases.items()):
        label = None
        if labels_tr.is_dir():
            for f in labels_tr.iterdir():
                if f.is_file() and f.name.split(".")[0] == case_id:
                    label = str(f)
                    break
        out.append(Case(id=case_id, dataset_id=dataset_id, channels=channels, label_path=label))
    return out
