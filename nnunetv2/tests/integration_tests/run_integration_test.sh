#!/usr/bin/env bash
set -e
export nnUNet_tb_image_every_n_epochs=1

nnUNetv2_train $1 3d_fullres 0 -tr nnUNetTrainer_5epochs --npz

TB_DIR=$(find "$nnUNet_results" -type d -name "tensorboard" | head -n 1)
if [ -z "$TB_DIR" ]; then
    echo "FAIL: no tensorboard/ directory found under \$nnUNet_results"
    exit 1
fi
EVENT_FILE=$(find "$TB_DIR" -maxdepth 1 -name "events.out.tfevents.*" | head -n 1)
if [ -z "$EVENT_FILE" ] || [ ! -s "$EVENT_FILE" ]; then
    echo "FAIL: no non-empty TB event file under $TB_DIR"
    exit 1
fi
echo "OK: TB event file present at $EVENT_FILE"

nnUNetv2_train $1 3d_fullres 1 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_fullres 2 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_fullres 3 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_fullres 4 -tr nnUNetTrainer_5epochs --npz

nnUNetv2_train $1 2d 0 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 2d 1 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 2d 2 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 2d 3 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 2d 4 -tr nnUNetTrainer_5epochs --npz

nnUNetv2_train $1 3d_lowres 0 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_lowres 1 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_lowres 2 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_lowres 3 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_lowres 4 -tr nnUNetTrainer_5epochs --npz

nnUNetv2_train $1 3d_cascade_fullres 0 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_cascade_fullres 1 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_cascade_fullres 2 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_cascade_fullres 3 -tr nnUNetTrainer_5epochs --npz
nnUNetv2_train $1 3d_cascade_fullres 4 -tr nnUNetTrainer_5epochs --npz

python nnunetv2/tests/integration_tests/run_integration_test_bestconfig_inference.py -d $1
