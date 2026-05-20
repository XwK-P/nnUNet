#!/usr/bin/env bash
set -e
export nnUNet_tb_image_every_n_epochs=1

# Strip out the optional --gui flag from positional arguments so $1 still
# refers to the dataset id whether or not --gui was passed.
GUI_ENABLED=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --gui) GUI_ENABLED=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]}"

GUI_PID=""
if [ "$GUI_ENABLED" = "1" ]; then
  echo "[integration] booting nnUNetv2_gui on port 8765"
  nnUNetv2_gui --host 127.0.0.1 --port 8765 >/tmp/nnunet_gui.log 2>&1 &
  GUI_PID=$!
  # Wait until /api/system/healthz returns 200 (up to 15s). The whole point
  # of the --gui mode is to exercise the GUI stack — silently continuing
  # when the probe never goes green would turn a broken boot (missing dep,
  # port collision, crash-on-start) into a passing run.
  GUI_READY=0
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8765/api/system/healthz >/dev/null; then
      GUI_READY=1
      break
    fi
    sleep 0.5
  done
  if [ "$GUI_READY" != "1" ]; then
    echo "FAIL: nnUNetv2_gui never became healthy on http://127.0.0.1:8765/api/system/healthz"
    echo "----- /tmp/nnunet_gui.log (tail) -----"
    tail -n 200 /tmp/nnunet_gui.log || true
    echo "--------------------------------------"
    kill "$GUI_PID" 2>/dev/null || true
    wait "$GUI_PID" 2>/dev/null || true
    exit 1
  fi
fi

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

if [ -n "$GUI_PID" ]; then
  echo "[integration] snapshotting dashboard"
  curl -s http://127.0.0.1:8765/api/dashboard > /tmp/nnunet_gui_dashboard.json || true
  kill "$GUI_PID" || true
  wait "$GUI_PID" 2>/dev/null || true
fi
