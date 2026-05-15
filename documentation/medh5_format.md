# Using the `.medh5` file format with nnU-Net v2

[medh5](https://github.com/XwK-P/medh5) is an HDF5+Blosc2 file format that
bundles all modalities of a case, the segmentation (as per-class boolean
masks), and the spatial metadata (spacing / origin / direction / coord
system) into a single file. Compared to nnU-Net's classic
`imagesTr/case_0000.nii.gz` + `labelsTr/case.nii.gz` layout, the bundled
format gives you:

* one file per case (no `_XXXX` channel suffix juggling),
* Blosc2 compression of image data,
* a single source of truth for orientation, label names, and per-class
  masks.

## Install

```bash
pip install nnunetv2[medh5]
```

This adds [`medh5`](https://pypi.org/project/medh5/) (which pulls in `h5py`
and `hdf5plugin`). The base `nnunetv2` install does **not** require it.

## Dataset layout

```
$nnUNet_raw/
└── Dataset504_HippocampusMEDH5/
    ├── data/
    │   ├── hippocampus_001.medh5   ← bundled: CT/T1/... + segmentation
    │   ├── hippocampus_002.medh5
    │   └── ...
    ├── data_test/                  ← optional inference inputs (no seg)
    │   ├── hippocampus_010.medh5
    │   └── ...
    └── dataset.json
```

Each `.medh5` contains:

* `images = {channel_name: ndarray, ...}` — one entry per modality.
* `seg = {class_name: bool_ndarray, ...}` — one entry per *foreground*
  class (background is implicit).
* `meta.spatial.spacing|origin|direction|coord_system` — spatial metadata.
* `meta.extra["nnunet_labels"]` — the `labels` mapping from
  `dataset.json`, so the file is self-describing for the reader.

There is **no** `imagesTr/` or `labelsTr/` subfolder — nnU-Net's
`dataset.json` schema already supports an explicit `dataset` key listing
every case's image and label paths, which is what the converter emits.

## Example `dataset.json`

```json
{
  "channel_names": {"0": "T1"},
  "labels": {"background": 0, "anterior": 1, "posterior": 2},
  "numTraining": 260,
  "file_ending": ".medh5",
  "overwrite_image_reader_writer": "Medh5IO",
  "dataset": {
    "hippocampus_001": {
      "images": ["data/hippocampus_001.medh5"],
      "label":   "data/hippocampus_001.medh5"
    },
    "hippocampus_002": {
      "images": ["data/hippocampus_002.medh5"],
      "label":   "data/hippocampus_002.medh5"
    }
  }
}
```

Note that `images` and `label` point at the *same* file — the bundled
medh5 contains both. nnU-Net's downstream stages
(fingerprinting / planning / preprocessing / training / inference) use the
`dataset` dict directly and never touch `imagesTr/` or the `_XXXX`
channel suffix convention.

## Converting an existing dataset

```bash
nnUNetv2_convert_to_medh5 -d 4 -o 504
# → $nnUNet_raw/Dataset504_HippocampusMEDH5/

nnUNetv2_plan_and_preprocess -d 504 --verify_dataset_integrity
nnUNetv2_train 504 3d_fullres 0
nnUNetv2_predict -i $nnUNet_raw/Dataset504_HippocampusMEDH5/data_test \
                 -o /tmp/pred504 -d 504 -c 3d_fullres -f 0
```

The converter reads each case with whatever reader/writer the source
`dataset.json` requires (NIfTI, NRRD, TIFF, …), translates the integer
label volume into per-class boolean masks via the source `labels`
mapping, and writes a single `.medh5` file per case.

CLI flags:

* `-d` source dataset id or full `DatasetXXX_Name`
* `-o` numeric id for the new medh5 dataset (must be free)
* `-name` override the name suffix (default: `<SourceName>MEDH5`)
* `--compression {fast,balanced,max}` Blosc2 preset (default: `balanced`)
* `-np` worker processes

## Notes and limitations

* Inference outputs are written to `.medh5` files that always contain
  the integer-labelled prediction under `images["prediction"]`. When the
  input file ships a `nnunet_labels` mapping (e.g. when produced by
  `nnUNetv2_convert_to_medh5`), the prediction is additionally split
  into per-class boolean masks under `seg/`.
* `Medh5IO` lazy-imports `medh5`. If you forget the `[medh5]` extra you
  will see a clear `ImportError` directing you to `pip install nnunetv2[medh5]`.
* medh5's bounding-box and image-level label fields are not used by
  nnU-Net; they pass through untouched in `extra` if you add them to your
  files manually.
* Region-based labels (where a `labels` value is a list of ints) are
  supported on read by mapping the boolean mask to the *first* int in
  the list; on write we union all ints in the list to produce the mask.
