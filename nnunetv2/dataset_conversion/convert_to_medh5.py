#    Copyright 2024 HIP Applied Computer Vision Lab, Division of Medical Image Computing, German Cancer Research Center
#    (DKFZ), Heidelberg, Germany
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""
Convert an existing nnU-Net v2 raw dataset to the bundled `.medh5` layout.

The resulting dataset has a single `data/` folder where each case is a single
`.medh5` file containing all modalities + segmentation. The emitted
`dataset.json` uses the explicit `"dataset"` schema so nnU-Net's standard
pipeline (fingerprinting, planning, preprocessing, training, prediction) can
consume it without needing `imagesTr/` or `labelsTr/` subfolders.

Usage:
    nnUNetv2_convert_to_medh5 -d 4 -o 504 [-name HippocampusMEDH5] \
        [--compression balanced] [-np 8]
"""

import argparse
import multiprocessing
import os
from copy import deepcopy
from typing import Optional

import numpy as np
from batchgenerators.utilities.file_and_folder_operations import (
    isdir,
    isfile,
    join,
    load_json,
    maybe_mkdir_p,
    save_json,
    subfiles,
)

from nnunetv2.configuration import default_num_processes
from nnunetv2.imageio.medh5_reader_writer import RESERVED_INT_SEG_KEY
from nnunetv2.imageio.reader_writer_registry import determine_reader_writer_from_dataset_json
from nnunetv2.paths import nnUNet_raw
from nnunetv2.utilities.dataset_name_id_conversion import (
    find_candidate_datasets,
    maybe_convert_to_dataset_name,
)
from nnunetv2.utilities.utils import get_filenames_of_train_images_and_targets


def _normalize_labels(labels: dict) -> dict:
    """Return a JSON-serialisable copy of ``dataset.json['labels']``."""
    normalised = {}
    for name, value in labels.items():
        if isinstance(value, (list, tuple)):
            normalised[name] = [int(v) for v in value]
        else:
            normalised[name] = int(value)
    return normalised


def _split_int_seg_to_masks(seg_int: np.ndarray, labels: dict) -> dict:
    """Split an integer-labelled volume into per-class boolean masks."""
    masks = {}
    for name, value in labels.items():
        if isinstance(value, (list, tuple)):
            values = [int(v) for v in value]
            if not values or (len(values) == 1 and values[0] == 0):
                continue
            mask = np.isin(seg_int, values)
        else:
            int_value = int(value)
            if int_value == 0:
                continue  # background is the absence of any foreground mask
            mask = seg_int == int_value
        masks[name] = mask
    return masks


def _convert_case(case_id: str,
                  image_files,
                  label_file: Optional[str],
                  out_path: str,
                  source_dataset_json: dict,
                  compression: str) -> str:
    """Read one case via nnU-Net's reader for the source format and write a .medh5 file."""
    from medh5 import MEDH5File

    rw_cls = determine_reader_writer_from_dataset_json(source_dataset_json, image_files[0], verbose=False)
    rw = rw_cls()
    images_arr, props = rw.read_images(image_files)  # (c, x, y, z), spacing key required

    channel_names = source_dataset_json.get('channel_names') or source_dataset_json.get('modality') or {}
    # channel_names keys are stringified integers '0','1',... → canonicalise to ordered names
    ordered_channel_names = [channel_names[str(i)] for i in range(images_arr.shape[0])] if channel_names else \
        [f'channel_{i}' for i in range(images_arr.shape[0])]
    if len(set(ordered_channel_names)) != len(ordered_channel_names):
        # Disambiguate duplicate channel names by appending the channel index
        seen = {}
        deduped = []
        for n in ordered_channel_names:
            seen[n] = seen.get(n, -1) + 1
            deduped.append(f"{n}_{seen[n]}" if seen[n] else n)
        ordered_channel_names = deduped
    images_dict = {ordered_channel_names[c]: np.ascontiguousarray(images_arr[c]) for c in range(images_arr.shape[0])}

    labels = _normalize_labels(source_dataset_json['labels'])

    seg_dict = None
    if label_file is not None:
        seg_int_4d, seg_props = rw.read_seg(label_file)
        seg_int_float = seg_int_4d[0]
        if seg_int_float.shape != images_arr.shape[1:]:
            raise RuntimeError(
                f"Image/seg shape mismatch for case {case_id}: image={images_arr.shape[1:]}, seg={seg_int_float.shape}"
            )
        max_label = int(np.max(seg_int_float)) if seg_int_float.size else 0
        int_dtype = np.uint8 if 0 <= max_label < 256 else np.uint16
        seg_int = np.ascontiguousarray(seg_int_float.astype(int_dtype, copy=False))
        seg_dict = _split_int_seg_to_masks(seg_int, labels) or None
        # Store the original integer seg under the reserved key so round-tripping
        # is bit-exact even for region-based labels (where boolean masks lose info).
        images_dict[RESERVED_INT_SEG_KEY] = seg_int

    spacing = list(props['spacing']) if props.get('spacing') is not None else None

    # Carry over orientation metadata from whatever reader we used. SimpleITK gives us
    # a 'sitk_stuff' dict with origin/direction; Nibabel gives an affine. Translate both.
    origin = None
    direction = None
    sitk_stuff = props.get('sitk_stuff')
    if isinstance(sitk_stuff, dict):
        origin = list(sitk_stuff.get('origin')) if sitk_stuff.get('origin') is not None else None
        d = sitk_stuff.get('direction')
        if d is not None:
            arr = np.asarray(d, dtype=float)
            if arr.size == 9:
                arr = arr.reshape(3, 3)
            elif arr.size == 4:
                arr = arr.reshape(2, 2)
            direction = [list(row) for row in arr]

    nibabel_stuff = props.get('nibabel_stuff')
    if direction is None and isinstance(nibabel_stuff, dict):
        affine = nibabel_stuff.get('original_affine')
        if affine is not None:
            affine = np.asarray(affine, dtype=float)
            if affine.shape == (4, 4):
                origin = list(affine[:3, 3])
                direction = [list(row) for row in affine[:3, :3]]

    extra = {
        'nnunet_labels': labels,
        # Preserve the source dataset.json channel ordering — medh5 sorts
        # image_names alphabetically internally, so without this Medh5IO.read_images
        # would silently permute channels relative to the source dataset.json.
        'nnunet_channel_order': list(ordered_channel_names),
        'source_file_ending': source_dataset_json.get('file_ending'),
        'source_case_id': case_id,
    }

    MEDH5File.write(
        out_path,
        images=images_dict,
        seg=seg_dict,
        spacing=spacing,
        origin=origin,
        direction=direction,
        # Intentionally omit coord_system: SimpleITK reports origin/direction
        # in LPS by convention, Nibabel in RAS — and we don't have enough info
        # here to disambiguate. Origin/direction are preserved verbatim; downstream
        # consumers should not assume a particular handedness without the tag.
        coord_system=None,
        extra=extra,
        compression=compression,
    )
    return out_path


def convert_to_medh5(source_dataset_name_or_id,
                     target_id: int,
                     target_name_suffix: Optional[str] = None,
                     compression: str = 'balanced',
                     num_processes: int = default_num_processes) -> str:
    source_name = maybe_convert_to_dataset_name(source_dataset_name_or_id)
    source_folder = join(nnUNet_raw, source_name)
    source_json_path = join(source_folder, 'dataset.json')
    assert isfile(source_json_path), f"Source dataset.json not found at {source_json_path}"
    source_dataset_json = load_json(source_json_path)

    existing = find_candidate_datasets(target_id)
    assert len(existing) == 0, (
        f"Target dataset id {target_id} is already taken (existing: {existing}). "
        f"Use a different id or remove the existing dataset."
    )

    base_name = source_name.split('_', 1)[1] if '_' in source_name else source_name
    target_name = f"Dataset{target_id:03d}_{target_name_suffix or (base_name + 'MEDH5')}"
    target_folder = join(nnUNet_raw, target_name)
    target_data = join(target_folder, 'data')
    target_data_test = join(target_folder, 'data_test')
    maybe_mkdir_p(target_data)

    dataset = get_filenames_of_train_images_and_targets(source_folder, source_dataset_json)

    case_args = []
    for case_id, entry in dataset.items():
        out_path = join(target_data, f"{case_id}.medh5")
        case_args.append((
            case_id,
            list(entry['images']),
            entry.get('label'),
            out_path,
            source_dataset_json,
            compression,
        ))

    print(f"Converting {len(case_args)} training cases from {source_name} to {target_name}...")
    with multiprocessing.get_context("spawn").Pool(num_processes) as pool:
        for _ in pool.starmap(_convert_case, case_args):
            pass

    # Optional: test images (no labels). Standard imagesTs/ folder lookup.
    imagesTs = join(source_folder, 'imagesTs')
    if isdir(imagesTs):
        source_file_ending = source_dataset_json['file_ending']
        test_files = subfiles(imagesTs, suffix=source_file_ending, join=False, sort=True)
        # Identify case ids by stripping `_XXXX.<ext>` (standard nnU-Net convention)
        ts_case_ids = sorted({f[:-(len(source_file_ending) + 5)] for f in test_files})
        if ts_case_ids:
            maybe_mkdir_p(target_data_test)
            ts_case_args = []
            import re
            channel_re = re.compile(r"_\d{4}" + re.escape(source_file_ending) + r"$")
            for case_id in ts_case_ids:
                imgs = sorted(
                    join(imagesTs, f) for f in test_files
                    if f.startswith(case_id + '_') and channel_re.search(f) is not None
                )
                if not imgs:
                    continue
                ts_case_args.append((
                    case_id,
                    imgs,
                    None,
                    join(target_data_test, f"{case_id}.medh5"),
                    source_dataset_json,
                    compression,
                ))
            print(f"Converting {len(ts_case_args)} test cases (no labels)...")
            with multiprocessing.get_context("spawn").Pool(num_processes) as pool:
                for _ in pool.starmap(_convert_case, ts_case_args):
                    pass

    # Build the destination dataset.json using the explicit "dataset" schema so we
    # don't need imagesTr/labelsTr folders.
    new_dataset_json = deepcopy(source_dataset_json)
    new_dataset_json['file_ending'] = '.medh5'
    new_dataset_json['overwrite_image_reader_writer'] = 'Medh5IO'
    new_dataset_json['labels'] = _normalize_labels(source_dataset_json['labels'])
    new_dataset_json['numTraining'] = len(case_args)
    new_dataset_json['dataset'] = {
        case_id: {
            'images': [join('data', f"{case_id}.medh5")],
            'label': join('data', f"{case_id}.medh5"),
        }
        for case_id, _, _, _, _, _ in case_args
    }
    new_dataset_json.pop('training', None)
    new_dataset_json.pop('test', None)

    save_json(new_dataset_json, join(target_folder, 'dataset.json'), sort_keys=False)
    print(f"Done. New dataset at {target_folder}")
    return target_folder


def main():
    parser = argparse.ArgumentParser(
        description="Convert an existing nnU-Net v2 raw dataset to the bundled .medh5 layout."
    )
    parser.add_argument('-d', '--source_dataset', type=str, required=True,
                        help='Source dataset id (int) or full name (e.g. Dataset004_Hippocampus).')
    parser.add_argument('-o', '--target_id', type=int, required=True,
                        help='Numeric id for the new medh5 dataset. Must not already exist.')
    parser.add_argument('-name', '--target_name_suffix', type=str, default=None,
                        help="Override the name suffix. Default: '<SourceName>MEDH5'.")
    parser.add_argument('--compression', type=str, default='balanced',
                        choices=['fast', 'balanced', 'max'],
                        help="medh5 compression preset (default: balanced).")
    parser.add_argument('-np', '--num_processes', type=int, default=default_num_processes,
                        help=f"Worker processes for conversion (default: {default_num_processes}).")
    args = parser.parse_args()

    convert_to_medh5(
        source_dataset_name_or_id=args.source_dataset,
        target_id=args.target_id,
        target_name_suffix=args.target_name_suffix,
        compression=args.compression,
        num_processes=args.num_processes,
    )


if __name__ == '__main__':
    main()
