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

from typing import List, Tuple, Union

import numpy as np

from nnunetv2.imageio.base_reader_writer import BaseReaderWriter


_MEDH5_IMPORT_HINT = (
    "Reading or writing .medh5 files requires the 'medh5' package. "
    "Install it with: pip install nnunetv2[medh5]  (or: pip install medh5)"
)

# Reserved channel name used by the converter and write_seg to store the original
# integer-labelled segmentation alongside the per-class boolean masks. read_images
# filters this entry out so it never appears as a modality; read_seg prefers it
# over reconstructing the seg from boolean masks (which would be lossy for
# region-based labels).
RESERVED_INT_SEG_KEY = '_nnunet_int_seg_v1'


def _import_medh5():
    try:
        from medh5 import MEDH5File  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - exercised only when extra not installed
        raise ImportError(_MEDH5_IMPORT_HINT) from exc
    return MEDH5File


class Medh5IO(BaseReaderWriter):
    """
    Reader/writer for the .medh5 file format (https://github.com/XwK-P/medh5).

    A .medh5 file bundles one or more co-registered modalities, optional per-class
    boolean segmentation masks, and rich spatial metadata (spacing / origin /
    direction / coord_system) in a single HDF5+Blosc2 container.

    Two layouts are supported transparently:

    1. **Bundled** (one file per case): ``read_images(["case.medh5"])`` reads all
       modalities from a single file and stacks them as channels in the order of
       ``sample.meta.image_names``. ``read_seg("case.medh5")`` reads the per-class
       boolean masks from the same file and rebuilds an integer-labelled volume
       using the mapping stored in ``sample.meta.extra["nnunet_labels"]``.
    2. **Split** (one file per channel, classic nnU-Net layout): pass multiple
       file paths to ``read_images``; each is treated as a one-modality medh5
       and the channels are concatenated.

    Properties dict contract (see ``BaseReaderWriter``):

    * Mandatory ``'spacing'`` key with a length-3 tuple matching the spatial
      axes of the returned array.
    * ``'medh5_stuff'`` mirrors the per-file metadata so ``write_seg`` can round
      trip it: ``origin``, ``direction``, ``axis_labels``, ``coord_system``,
      ``image_names``, ``label_mapping`` (the ``nnunet_labels`` dict written by
      ``nnUNetv2_convert_to_medh5``).
    """

    supported_file_endings = ['.medh5']
    write_compression = 'balanced'

    def _read_one(self, fname: str):
        medh5file = _import_medh5()
        sample = medh5file.read(fname)
        extras = sample.meta.extra or {}
        # Prefer the original index ordering recorded by the converter, since
        # medh5 sorts image_names alphabetically internally — falling back to
        # that sort would silently permute channels vs. the source dataset.json.
        preferred_order = None
        if isinstance(extras, dict):
            preferred_order = extras.get('nnunet_channel_order')
        if preferred_order:
            names = [n for n in preferred_order if n in sample.images]
        else:
            names = list(sample.meta.image_names) if sample.meta.image_names else sorted(sample.images.keys())
        # Filter reserved entries that are not real modalities (e.g. the
        # integer-labelled seg stored for lossless round-trip).
        modality_names = [n for n in names if n != RESERVED_INT_SEG_KEY]
        if not modality_names:
            # File contains only the reserved seg entry (e.g. a write_seg output with no
            # other modalities). Fall back to it so the seg shape is still discoverable.
            if RESERVED_INT_SEG_KEY in sample.images:
                modality_names = [RESERVED_INT_SEG_KEY]
            else:
                raise RuntimeError(f"medh5 file has no images: {fname}")
        arrays = [np.asarray(sample.images[n]) for n in modality_names]
        ref_shape = arrays[0].shape
        for n, a in zip(modality_names, arrays):
            if a.shape != ref_shape:
                raise RuntimeError(
                    f"Inconsistent modality shapes in {fname}: '{modality_names[0]}'={ref_shape}, '{n}'={a.shape}"
                )
        if len(ref_shape) != 3:
            raise RuntimeError(
                f"Medh5IO currently supports 3D volumes only; got array of shape {ref_shape} in {fname}. "
                f"2D support can be added by subclassing and reshaping to (1, H, W) with a 999 spacing sentinel."
            )
        stacked = np.stack(arrays, axis=0).astype(np.float32, copy=False)
        spatial = sample.meta.spatial
        # Spacing must match the spatial dimensions of the array (length 3 for 3D).
        spacing = list(spatial.spacing) if spatial.spacing is not None else [1.0] * (stacked.ndim - 1)
        label_mapping = extras.get('nnunet_labels') if isinstance(extras, dict) else None
        info = {
            'origin': list(spatial.origin) if spatial.origin is not None else None,
            'direction': [list(r) for r in spatial.direction] if spatial.direction is not None else None,
            'axis_labels': list(spatial.axis_labels) if spatial.axis_labels is not None else None,
            'coord_system': spatial.coord_system,
            'image_names': modality_names,
            'label_mapping': label_mapping,
            'patch_size': list(sample.meta.patch_size) if sample.meta.patch_size is not None else None,
            'seg_names': list(sample.meta.seg_names) if sample.meta.seg_names else None,
        }
        return stacked, spacing, info, sample

    def read_images(self, image_fnames: Union[List[str], Tuple[str, ...]]) -> Tuple[np.ndarray, dict]:
        per_file_arrays = []
        spacings = []
        infos = []
        for f in image_fnames:
            arr, spacing, info, _ = self._read_one(f)
            per_file_arrays.append(arr)
            spacings.append(spacing)
            infos.append(info)

        if not self._check_all_same([a.shape for a in per_file_arrays]):
            print('ERROR! Not all input images have the same shape!')
            print('Shapes:')
            print([a.shape for a in per_file_arrays])
            print('Image files:')
            print(image_fnames)
            raise RuntimeError()
        if not self._check_all_same(spacings):
            print('ERROR! Not all input images have the same spacing!')
            print('Spacings:')
            print(spacings)
            print('Image files:')
            print(image_fnames)
            raise RuntimeError()

        stacked = np.vstack(per_file_arrays, dtype=np.float32, casting='unsafe')
        info = infos[0]
        # When multiple files were given, merge image_names in order
        if len(infos) > 1:
            merged_names = []
            for i in infos:
                merged_names.extend(i.get('image_names') or [])
            info = {**info, 'image_names': merged_names}

        properties = {
            'spacing': spacings[0],
            'medh5_stuff': info,
        }
        return stacked, properties

    def read_seg(self, seg_fname: str) -> Tuple[np.ndarray, dict]:
        arr, spacing, info, sample = self._read_one(seg_fname)

        # Preferred path: the converter / write_seg stores the original
        # integer-labelled volume under RESERVED_INT_SEG_KEY so round-tripping
        # is bit-exact even for region-based labels (where the per-class
        # boolean masks would be lossy).
        if RESERVED_INT_SEG_KEY in sample.images:
            int_seg = np.asarray(sample.images[RESERVED_INT_SEG_KEY])
            ref_shape = arr.shape[1:]  # strip channel axis added by _read_one
            if int_seg.shape != ref_shape:
                raise RuntimeError(
                    f"Reserved seg '{RESERVED_INT_SEG_KEY}' has shape {int_seg.shape}, "
                    f"expected {ref_shape} (matching the modality channels) in {seg_fname}"
                )
            properties = {
                'spacing': spacing,
                'medh5_stuff': info,
            }
            return int_seg.astype(np.float32, copy=False)[None], properties

        # Reconstruct an integer-labelled (1, x, y, z) volume from the per-class boolean masks
        seg_masks = sample.seg or {}
        if seg_masks:
            ref_shape = arr.shape[1:]  # strip channel axis added by _read_one
            label_mapping = info.get('label_mapping')
            if label_mapping is None:
                # No explicit mapping; assign integer labels in insertion order, background=0.
                sorted_names = sorted(seg_masks.keys())
                label_mapping = {'background': 0}
                for idx, n in enumerate(sorted_names, start=1):
                    label_mapping[n] = idx
                info = {**info, 'label_mapping': label_mapping}
                print(
                    f"WARNING: {seg_fname} does not declare 'nnunet_labels' in extra; "
                    f"falling back to alphabetical mapping: {label_mapping}"
                )

            # float32 to match SimpleITKIO/NibabelIO and allow downstream sentinels (e.g. -1
            # written by crop_to_nonzero) to fit in the same array.
            seg = np.zeros(ref_shape, dtype=np.float32)
            for class_name, label_value in label_mapping.items():
                if class_name not in seg_masks:
                    continue  # background or missing class
                mask = np.asarray(seg_masks[class_name], dtype=bool)
                if mask.shape != ref_shape:
                    raise RuntimeError(
                        f"Seg mask '{class_name}' has shape {mask.shape}, expected {ref_shape} in {seg_fname}"
                    )
                if isinstance(label_value, (list, tuple)):
                    # Region-based label: assign the first int in the list (preserves region membership)
                    if not label_value:
                        continue
                    seg[mask] = float(label_value[0])
                else:
                    seg[mask] = float(label_value)
            seg = seg[None]
        else:
            # No per-class boolean masks; treat the (single) image as the integer labelling.
            # This is the path used by Medh5IO.write_seg outputs that lack a mapping.
            if arr.shape[0] != 1:
                raise RuntimeError(
                    f"Cannot interpret {seg_fname} as a segmentation: it has {arr.shape[0]} image channels "
                    f"and no 'seg' group."
                )
            seg = arr.astype(np.float32, copy=False)

        properties = {
            'spacing': spacing,
            'medh5_stuff': info,
        }
        return seg, properties

    def write_seg(self, seg: np.ndarray, output_fname: str, properties: dict) -> None:
        assert seg.ndim == 3, 'segmentation must be 3d. If you are exporting a 2d segmentation, please provide it as shape 1,x,y'
        medh5file = _import_medh5()
        info = properties.get('medh5_stuff', {}) or {}
        spacing = properties.get('spacing')

        max_val = int(seg.max()) if seg.size else 0
        int_dtype = np.uint8 if max_val < 256 else np.uint16
        seg_int = seg.astype(int_dtype, copy=False)

        # Always emit the integer prediction under the reserved key so the file
        # is valid (medh5 requires at least one image) and so read_seg can
        # round-trip the integer labels bit-exactly. When label_mapping is also
        # available, additionally split into per-class boolean masks for native
        # medh5 consumers.
        images = {RESERVED_INT_SEG_KEY: seg_int}
        seg_masks = None
        label_mapping = info.get('label_mapping')
        if isinstance(label_mapping, dict) and label_mapping:
            seg_masks = {}
            for class_name, label_value in label_mapping.items():
                if isinstance(label_value, (list, tuple)):
                    values = [int(v) for v in label_value]
                    if not values or 0 in values and len(values) == 1:
                        continue
                    mask = np.isin(seg_int, values)
                else:
                    int_value = int(label_value)
                    if int_value == 0:
                        continue  # background = absence of foreground masks
                    mask = seg_int == int_value
                if mask.any():
                    seg_masks[class_name] = mask
            if not seg_masks:
                seg_masks = None

        extra = {'nnunet_labels': label_mapping} if isinstance(label_mapping, dict) else None
        write_kwargs = {
            'spacing': list(spacing) if spacing is not None else None,
            'origin': list(info['origin']) if info.get('origin') is not None else None,
            'direction': [list(r) for r in info['direction']] if info.get('direction') is not None else None,
            'axis_labels': list(info['axis_labels']) if info.get('axis_labels') is not None else None,
            'coord_system': info.get('coord_system'),
            'extra': extra,
            'compression': self.write_compression,
        }

        medh5file.write(
            output_fname,
            images=images,
            seg=seg_masks,
            **write_kwargs,
        )


if __name__ == '__main__':  # pragma: no cover
    import sys

    if len(sys.argv) >= 2:
        io = Medh5IO()
        a, p = io.read_images([sys.argv[1]])
        print('images:', a.shape, a.dtype, '| spacing:', p['spacing'])
        s, sp = io.read_seg(sys.argv[1])
        print('seg:', s.shape, s.dtype, '| spacing:', sp['spacing'])
