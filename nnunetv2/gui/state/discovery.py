"""Filesystem scanners that turn nnU-Net on-disk artifacts into model records."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DATASET_DIR_RE = re.compile(r"^Dataset(\d{3})_(.+)$")
RUN_DIR_RE = re.compile(r"^(.+)__(.+)__(.+)$")
FOLD_DIR_RE = re.compile(r"^fold_(.+)$")


@dataclass(frozen=True)
class DiscoveredDataset:
    id: str
    dataset_id_int: Optional[int]
    name: Optional[str]
    raw_path: str
    case_count: int
    modality_count: int


@dataclass(frozen=True)
class DiscoveredRun:
    id: str
    dataset_id: str
    plans_name: str
    trainer_name: str
    configuration: str
    fold: str
    output_folder: str
    status: str  # 'completed' | 'abandoned'


def resolve_dataset_folder(
    raw_root: Path, preprocessed_root: Path, results_root: Path,
    dataset_id_int: int,
) -> Optional[str]:
    """Return the full ``Dataset<NNN>_<Name>`` folder name for an int id.

    nnUNet keys runs and checkpoints by the full folder name (e.g.
    ``Dataset027_ACDC``), not the bare numeric id. Probe raw, preprocessed
    and results in turn — whichever the user has on disk wins. Returns
    None when no candidate exists, leaving the caller to surface a 400.

    Multiple matches (a hand-renamed folder collision) resolve
    deterministically by sorted name.
    """
    prefix = f"Dataset{dataset_id_int:03d}_"
    seen: set[str] = set()
    for root in (raw_root, preprocessed_root, results_root):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.is_dir() and entry.name.startswith(prefix):
                seen.add(entry.name)
    if not seen:
        return None
    return sorted(seen)[0]


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


def scan_preprocessed(preprocessed_root: Path) -> dict[str, str]:
    """Return {dataset_folder_name: absolute_path} for every preprocessed dataset."""
    if not preprocessed_root.is_dir():
        return {}
    out: dict[str, str] = {}
    for entry in sorted(preprocessed_root.iterdir()):
        if not entry.is_dir():
            continue
        if not DATASET_DIR_RE.match(entry.name):
            continue
        out[entry.name] = str(entry)
    return out


def read_fingerprint(dataset_preprocessed_dir: Path) -> Optional[dict]:
    """Read dataset_fingerprint.json if present; return None otherwise."""
    fp = dataset_preprocessed_dir / "dataset_fingerprint.json"
    if not fp.is_file():
        return None
    try:
        return json.loads(fp.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def scan_results_runs(results_root: Path) -> list[DiscoveredRun]:
    """Walk `results_root`, yielding one DiscoveredRun per fold_* directory."""
    if not results_root.is_dir():
        return []
    out: list[DiscoveredRun] = []
    for dataset_dir in sorted(results_root.iterdir()):
        if not dataset_dir.is_dir() or not DATASET_DIR_RE.match(dataset_dir.name):
            continue
        for plans_trainer_config_dir in sorted(dataset_dir.iterdir()):
            if not plans_trainer_config_dir.is_dir():
                continue
            m = RUN_DIR_RE.match(plans_trainer_config_dir.name)
            if not m:
                continue
            plans_name, trainer_name, configuration = m.group(1), m.group(2), m.group(3)
            for fold_dir in sorted(plans_trainer_config_dir.iterdir()):
                if not fold_dir.is_dir():
                    continue
                fm = FOLD_DIR_RE.match(fold_dir.name)
                if not fm:
                    continue
                fold = fm.group(1)
                status = "completed" if (fold_dir / "checkpoint_final.pth").is_file() else "abandoned"
                canonical_id = f"{dataset_dir.name}/{plans_trainer_config_dir.name}/{fold_dir.name}"
                out.append(DiscoveredRun(
                    id=canonical_id,
                    dataset_id=dataset_dir.name,
                    plans_name=plans_name,
                    trainer_name=trainer_name,
                    configuration=configuration,
                    fold=fold,
                    output_folder=str(fold_dir),
                    status=status,
                ))
    return out


def scan_active_runs(cfg) -> list[DiscoveredRun]:
    """Return runs that look in-flight.

    Heuristic: no `checkpoint_final.pth` but a `tensorboard/` directory exists
    and was touched in the last 10 minutes. Used by Phase 3 (read-only) to
    surface CLI-launched trainings on the Monitor route; Phase 4 will rely on
    the launcher's own job rows instead.
    """
    import time

    now = time.time()
    cutoff = 10 * 60  # seconds
    out: list[DiscoveredRun] = []
    for r in scan_results_runs(cfg.results):
        fold_dir = Path(r.output_folder)
        if (fold_dir / "checkpoint_final.pth").is_file():
            continue
        tb = fold_dir / "tensorboard"
        if not tb.is_dir():
            continue
        try:
            mtime = tb.stat().st_mtime
        except OSError:
            continue
        if now - mtime > cutoff:
            continue
        out.append(r)
    return out


def reconcile(cfg) -> None:
    """One-shot scan of raw + preprocessed + results, upserting all records.

    Imports the repositories lazily to keep `discovery` decoupled from `state.{datasets,runs}`.
    """
    from datetime import datetime, timezone
    import json

    from nnunetv2.gui.state.datasets import Dataset, upsert_dataset, get_dataset
    from nnunetv2.gui.state.runs import Run, upsert_run

    now = datetime.now(timezone.utc)
    preprocessed_map = scan_preprocessed(cfg.preprocessed)

    for d in scan_raw_datasets(cfg.raw):
        preprocessed_path = preprocessed_map.get(d.id)
        fingerprint_json = None
        if preprocessed_path:
            fp = read_fingerprint(Path(preprocessed_path))
            if fp is not None:
                fingerprint_json = json.dumps(fp)
        ds = Dataset(
            id=d.id,
            dataset_id_int=d.dataset_id_int,
            name=d.name,
            raw_path=d.raw_path,
            preprocessed_path=preprocessed_path,
            last_scanned_at=now,
            fingerprint_json=fingerprint_json,
            case_count=d.case_count,
            modality_count=d.modality_count,
        )
        upsert_dataset(cfg, ds)

    for r in scan_results_runs(cfg.results):
        # Preserve created_at if the row already exists; otherwise set now.
        # For Phase 1 we treat last_seen_at = now for any rediscovered run.
        from nnunetv2.gui.state.runs import get_run
        existing = get_run(cfg, r.id)
        created = existing.created_at if existing else now
        run = Run(
            id=r.id,
            dataset_id=r.dataset_id,
            plans_name=r.plans_name,
            trainer_name=r.trainer_name,
            configuration=r.configuration,
            fold=r.fold,
            output_folder=r.output_folder,
            status=r.status,
            source=existing.source if existing else "unknown",
            created_at=created,
            last_seen_at=now,
            tags_json=existing.tags_json if existing else None,
            notes=existing.notes if existing else None,
        )
        upsert_run(cfg, run)
