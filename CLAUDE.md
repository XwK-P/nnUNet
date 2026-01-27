# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

nnU-Net is a self-configuring semantic segmentation framework for biomedical images. It automatically adapts U-Net architectures to given datasets through dataset fingerprinting and rule-based configuration. This is **version 2** - a complete rewrite of the original nnU-Net with improved code structure.

**Important:** PyTorch 2.9.0 has a severe performance regression with 3D convolutions. Use PyTorch 2.8.0 or lower.

## Environment Setup

nnU-Net requires three environment variables to be set:

- `nnUNet_raw`: Location for raw datasets (DatasetXXX_Name format)
- `nnUNet_preprocessed`: Location for preprocessed data (should be on fast storage like NVMe SSD)
- `nnUNet_results`: Location for trained models and results

These must be set before running any nnU-Net commands. See `documentation/setting_up_paths.md` for details.

## Installation

1. **Install PyTorch first** (version ≤2.8.0): `pip install torch` (with appropriate CUDA/CPU variant)
2. Install nnU-Net:
   - For use as baseline/inference: `pip install nnunetv2`
   - For development: `pip install -e .` (from repo root)

## Common Commands

All commands have the prefix `nnUNetv2_` and support `-h` for help. The full pipeline is:

### 1. Dataset Preparation
Convert data to nnU-Net format (see `documentation/dataset_format.md`), then:
```bash
nnUNetv2_plan_and_preprocess -d DATASET_ID --verify_dataset_integrity
```

This extracts fingerprints, plans experiments, and preprocesses data. For multiple datasets: `-d 1 2 3`.

### 2. Training
Train a 5-fold cross-validation for a configuration:
```bash
nnUNetv2_train DATASET_ID CONFIGURATION FOLD [--npz]
```

- `CONFIGURATION`: `2d`, `3d_fullres`, `3d_lowres`, `3d_cascade_fullres`
- `FOLD`: 0-4 for cross-validation, or `all` for single model
- `--npz`: Save softmax predictions (required for `find_best_configuration`)

**Multi-GPU training:**
- Recommended: Train separate folds on separate GPUs using `CUDA_VISIBLE_DEVICES`
- DDP: `nnUNetv2_train DATASET_ID CONFIG FOLD -num_gpus N` (only for large batch sizes)

**Important:** First training extracts preprocessed data to numpy arrays. Wait for this to complete before starting additional trainings of the same configuration.

### 3. Find Best Configuration
After training all desired configurations with `--npz`:
```bash
nnUNetv2_find_best_configuration DATASET_ID -c CONFIG1 CONFIG2 ...
```

Outputs inference commands to terminal and creates `inference_instructions.txt`.

### 4. Inference
```bash
nnUNetv2_predict -i INPUT_FOLDER -o OUTPUT_FOLDER -d DATASET_ID -c CONFIGURATION
```

Use `-f all` to predict with single fold, otherwise uses ensemble of all 5 folds (recommended).

### 5. Ensemble Multiple Configurations
```bash
nnUNetv2_ensemble -i FOLDER1 FOLDER2 ... -o OUTPUT_FOLDER
```

### 6. Apply Postprocessing
```bash
nnUNetv2_apply_postprocessing -i PREDICTIONS -o OUTPUT -pp_pkl_file POSTPROCESSING_FILE -plans_json PLANS_FILE -dataset_json DATASET_FILE
```

## Architecture Overview

### Directory Structure

- `experiment_planning/`: Dataset fingerprinting and automatic configuration generation
  - `ExperimentPlanner`: Analyzes datasets and creates `nnUNetPlans.json` files defining network topology, preprocessing, batch size
  - Rule-based heuristics determine patch size, network depth, pooling based on dataset properties
- `preprocessing/`: Resampling, normalization, cropping implementations
  - Preprocessed data cached as `.npy`/`.npz` for fast training
- `training/`: Training orchestration and components
  - `nnUNetTrainer`: Main trainer class (similar to PyTorch Lightning)
  - `variants/`: Subclasses for different losses, architectures, data augmentation, etc.
  - `dataloading/`: Data loaders with background preprocessing
  - `loss/`: Loss functions (default: Dice + CE with deep supervision)
- `inference/`: Prediction pipeline
  - `nnUNetPredictor`: Manages sliding window inference, ensembling, TTA
  - Automatically applies preprocessing on-the-fly
- `utilities/`: Core helpers
  - `PlansManager`: Parses and interprets `plans.json` files
  - `LabelManager`: Handles label mappings and region-based training
- `imageio/`: Registry-based I/O supporting `.nii.gz`, `.png`, `.tif`, etc.
- `evaluation/`: Metrics computation and results analysis
- `postprocessing/`: Connected component removal

### Key Concepts

**Plans Files (`nnUNetPlans.json`):**
- Central configuration files controlling the entire pipeline
- Define multiple configurations (2d, 3d_fullres, 3d_lowres, cascade) per dataset
- Can be manually edited to override automatic decisions (see `documentation/explanation_plans_files.md`)
- Support configuration inheritance for easy variants

**Deep Supervision:**
- Loss computed at multiple decoder resolutions
- Weights decrease exponentially at lower resolutions
- All nnU-Net architectures must support this (or use `nnUNetTrainerNoDeepSupervision`)

**Sliding Window Inference:**
- For large 3D volumes exceeding GPU memory
- Overlapping patches with Gaussian importance weighting for smooth blending

**Cascade Training:**
- For very large 3D images: first train `3d_lowres`, then `3d_cascade_fullres` refines predictions
- `3d_cascade_fullres` requires all 5 folds of `3d_lowres` to be completed first

**Self-Configuration Philosophy:**
- Fixed parameters: Loss function, most data augmentation, learning rate schedule
- Rule-based parameters: Network topology, patch size, batch size (computed from dataset fingerprint + GPU memory)
- Empirical parameters: Best configuration selection, postprocessing (determined by cross-validation)

## Extending nnU-Net

The codebase is designed to be extended through inheritance:

**Custom Trainer:**
Subclass `nnUNetTrainer` and override methods:
```python
from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer

class MyTrainer(nnUNetTrainer):
    def configure_optimizers(self):
        # Custom optimizer
        pass
```

See `training/nnUNetTrainer/variants/` for many examples (different losses, architectures, schedulers, etc.).

**Custom Architecture:**
- Quick: Override `build_network_architecture()` in custom trainer
- Proper: Create new `ExperimentPlanner` with memory estimation, generate custom plans

**Custom Normalization:**
See `preprocessing/normalization/` and `documentation/explanation_normalization.md`.

**Manual Plans Editing:**
Directly edit `plans.json` files to change preprocessing, topology, batch size (see `documentation/explanation_plans_files.md`).

## Residual Encoder Presets (Recommended)

New recommended configurations using residual encoder U-Nets:

- **ResEnc M**: ~9-11GB VRAM (similar to original nnU-Net)
- **ResEnc L**: ~24GB VRAM (new recommended default)
- **ResEnc XL**: ~40GB VRAM

Usage:
```bash
nnUNetv2_plan_and_preprocess -d DATASET -pl nnUNetPlannerResEncL
nnUNetv2_train DATASET 3d_fullres FOLD -p nnUNetResEncUNetLPlans
```

See `documentation/resenc_presets.md` for details.

## Testing

Integration tests in `nnunetv2/tests/integration_tests/`:
- Tests entire pipeline from fingerprinting through postprocessing
- Uses Dataset004_Hippocampus with modified configurations
- Run with `bash nnunetv2/tests/integration_tests/run_integration_test.sh DATASET_ID`

**Note:** "Aint nobody got time for unittests" - tests are integration-focused.

## Code Philosophy

From `nnUNetTrainer.py` comments:
- "Grug-brain" development: Prioritize simplicity and readability
- Avoid "complexity demons" - prefer straightforward implementations
- Multi-GPU, region-based training, ignore labels, cascades all unified in single `nnUNetTrainer` class

## Important File Locations

- Entry points: `pyproject.toml` → `[project.scripts]` section maps CLI commands to Python functions
- CLI commands defined in:
  - Training: `nnunetv2/run/run_training.py`
  - Planning/Preprocessing: `nnunetv2/experiment_planning/plan_and_preprocess_entrypoints.py`
  - Inference: `nnunetv2/inference/predict_from_raw_data.py`
  - Evaluation: `nnunetv2/evaluation/`

## Typical Workflow for Development

1. Set environment variables (`nnUNet_raw`, `nnUNet_preprocessed`, `nnUNet_results`)
2. Create dataset in nnU-Net format under `$nnUNet_raw/DatasetXXX_Name/`
3. Run `nnUNetv2_plan_and_preprocess -d XXX`
4. For custom modifications:
   - Create trainer variant in `nnunetv2/training/nnUNetTrainer/variants/`
   - Train with `-tr MyCustomTrainer`
5. Use `progress.png` and `debug.json` in training output folders for monitoring
6. Validation results in `fold_X/validation/summary.json`

## Dataset Format

- Naming: `DatasetXXX_Name` (XXX = 3-digit number)
- Structure: `imagesTr/`, `labelsTr/`, `imagesTs/`, `dataset.json`
- Images: `{case_id}_{modality}.{ext}` (e.g., `case001_0000.nii.gz`)
- Labels: `{case_id}.{ext}`
- Supported formats: `.nii.gz`, `.npy`, `.npz`, `.tif`, `.png`

See `documentation/dataset_format.md` for complete specification.
