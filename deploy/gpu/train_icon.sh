#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fine-tune the icon model (OmniParser icon_detect, YOLO11m) on a rented card.
#
# Why: the stock model misses dimmed, inactive icons on automotive HMI screens
# (2026-11-23: a fan icon at 0.004 against the 0.05 cut-off). The work is done
# by scripts/training/cv/finetune_icon_detect.py; this script is the rental
# wrapper around it: environment, stock weights, the steps in order, one
# tarball to download.
#
# THE DATA IS NOT IN THE REPOSITORY. Build the pack on the machine that holds
# the labelled screens and copy it here:
#
#   (your machine)
#   python scripts/training/cv/finetune_icon_detect.py pack \
#       --source data/da3/benchmark --out data/da3/icon_pack
#   tar -czf da3_icon_pack.tar.gz -C data/da3 icon_pack
#   scp -P <port> da3_icon_pack.tar.gz root@<host>:/root/vizdom/
#
#   (rental)
#   git clone <repo> && cd <repo> && git checkout develop
#   tmux new -s train
#   TRAIN_ONLY="prepare smoke" bash deploy/gpu/train_icon.sh     # 3-minute check
#   OUT_DIR=benchmarks/results/icon-finetune bash deploy/gpu/train_icon.sh
#
# The pack holds screenshots and boxes only (no annotator, no e-mail, no
# storage path), but the screenshots themselves are internal: check that you
# may put them on a rented machine before you copy them, and destroy the
# instance when the tarball is downloaded.
#
# Steps (TRAIN_ONLY names): prepare smoke train eval
#   prepare  dimmed copies of the training screens + replay screens (synthetic
#            train, labelled by the stock model) so desktop screens are kept
#   smoke    one epoch on a tenth of the data: does training start at all
#   train    the fine-tune (EPOCHS, BATCH, LR0, FREEZE)
#   eval     stock against fine-tuned: test split, dimmed icons, guard sets
#
# Needs no setup.sh / prefetch.sh: it builds .venv-train (torch + ultralytics)
# and downloads the 40 MB stock weights. Any card of 16 GB or more; 20 GB disk.
# ---------------------------------------------------------------------------
set -uo pipefail   # NOT -e: a failed step is reported at the end, not fatal
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:$PATH"

OUT="${OUT_DIR:-benchmarks/results/icon-finetune-$(date +%Y%m%d_%H%M%S)}"
OUT="${OUT%/}"
STEPS="${TRAIN_ONLY:-}"
PACK="${DATA_PACK:-da3_icon_pack.tar.gz}"
DATA="${DATA_DIR:-data/da3/icon_pack}"          # under data/da3: ignored by git
EPOCHS="${EPOCHS:-60}"
BATCH="${BATCH:-8}"
LR0="${LR0:-0.0003}"
FREEZE="${FREEZE:-0}"
DIM_COPIES="${DIM_COPIES:-2}"
REPLAY="${REPLAY_IMAGES-data/synthetic/train/images}"   # REPLAY_IMAGES= (empty) turns it off
ULTRALYTICS_VERSION="${ULTRALYTICS_VERSION:-8.4.104}"   # the version on the laptop that will load the result
STOCK="models/omniparser/icon_detect/model.pt"
STOCK_SHA="dab3d4351ad00b035db829909a4db98354d5a90f6990e4ac00222a9a95d4bf57"
TOOL="scripts/training/cv/finetune_icon_detect.py"

mkdir -p "$OUT"
exec > >(tee -a "$OUT/train.log") 2>&1
echo "icon fine-tune -> $OUT   (steps: ${STEPS:-all})"

nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > "$OUT/gpu.txt" || {
    echo "FATAL: no NVIDIA driver visible"; exit 1; }
{ echo "commit: $(git rev-parse --short HEAD 2>/dev/null)"; date -u
  echo "epochs $EPOCHS, batch $BATCH, lr0 $LR0, freeze $FREEZE, dim copies $DIM_COPIES, replay ${REPLAY:-off}"
} >> "$OUT/gpu.txt"

# --- data: the pack you copied here ------------------------------------------
if [ ! -f "$DATA/data.yaml" ]; then
    [ -f "$PACK" ] || {
        echo "FATAL: no dataset. Expected $DATA/ or the tarball $PACK"
        echo "       (build it with '$TOOL pack' on the machine that holds the screens,"
        echo "        see the head of this script; DATA_PACK=<file> names another tarball)"
        exit 1; }
    mkdir -p "$(dirname "$DATA")"
    tar -xzf "$PACK" -C "$(dirname "$DATA")" || { echo "FATAL: could not unpack $PACK"; exit 1; }
    [ -f "$DATA/data.yaml" ] || {
        echo "FATAL: $PACK did not unpack to $DATA (it must contain icon_pack/data.yaml)"; exit 1; }
fi
for split in train val test; do
    n=$(find "$DATA/images/$split" -name '*.png' 2>/dev/null | wc -l)
    echo "  $split: $n screens"
    [ "$n" -gt 0 ] || { echo "FATAL: the $split split is empty"; exit 1; }
done

# --- environment: .venv-train (built once, about 2 minutes) ------------------
PY="${TRAIN_PY:-.venv-train/bin/python}"     # TRAIN_PY: an environment that is already there
if [ ! -x "$PY" ]; then
    echo "=== building .venv-train ==="
    command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
    # opencv needs these two on a bare image; never fatal
    (apt-get install -y -qq libgl1 libglib2.0-0 >/dev/null 2>&1 || true)
    # the same wheel choice as setup.sh: Blackwell cards need cu128
    COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
    CUDA_INDEX="https://download.pytorch.org/whl/cu126"
    case "$COMPUTE_CAP" in 12.*|10.*) CUDA_INDEX="https://download.pytorch.org/whl/cu128" ;; esac
    uv python install 3.12 && uv venv --python 3.12 .venv-train \
        && VIRTUAL_ENV="$(pwd)/.venv-train" uv pip install torch torchvision --index-url "$CUDA_INDEX" \
        && VIRTUAL_ENV="$(pwd)/.venv-train" uv pip install "ultralytics==$ULTRALYTICS_VERSION" \
               "huggingface_hub[cli]" pyyaml \
        || { echo "FATAL: could not build .venv-train"; exit 1; }
fi
"$PY" - <<'PYCHECK' | tee -a "$OUT/gpu.txt" || { echo "FATAL: .venv-train is not usable"; exit 1; }
import torch, ultralytics, cv2
assert torch.cuda.is_available(), "torch sees no CUDA - wrong wheel or driver"
print(f"train env: torch {torch.__version__}, ultralytics {ultralytics.__version__}, opencv {cv2.__version__}")
PYCHECK

# --- stock weights (40 MB) ----------------------------------------------------
if [ ! -f "$STOCK" ]; then
    echo "=== stock icon_detect weights ==="
    mkdir -p "$(dirname "$STOCK")"
    "$PY" - "$STOCK" <<'PYGET' || { echo "FATAL: could not download the stock weights"; exit 1; }
import shutil, sys
from huggingface_hub import hf_hub_download
shutil.copyfile(hf_hub_download("microsoft/OmniParser-v2.0", "icon_detect/model.pt"), sys.argv[1])
PYGET
fi
GOT_SHA=$(sha256sum "$STOCK" | cut -d' ' -f1)
if [ "$GOT_SHA" = "$STOCK_SHA" ]; then
    echo "stock weights: the same file as on the laptop" | tee -a "$OUT/gpu.txt"
else
    echo "WARNING: stock weights differ from the laptop's ($GOT_SHA) - the 'stock' rows are" \
         "then not the model VizDOM runs today" | tee -a "$OUT/gpu.txt"
fi

wanted() { [ -z "$STEPS" ] || [[ " $STEPS " == *" $1 "* ]]; }
FAILED_STEPS=""
step() {   # step <name> <command...>
    local name="$1"; shift
    echo; echo "=============== $name ==============="
    local t0=$SECONDS
    if "$@" > "$OUT/$name.log" 2>&1; then
        echo "$name: OK ($((SECONDS - t0))s)"
        tail -n "${STEP_TAIL:-6}" "$OUT/$name.log"
    else
        echo "$name: FAILED ($((SECONDS - t0))s) - see $OUT/$name.log"
        FAILED_STEPS="$FAILED_STEPS $name"
        tail -n 15 "$OUT/$name.log"
    fi
}

# --- prepare: dimmed copies + replay (safe to repeat: existing files are kept)
if wanted prepare; then
    REPLAY_ARGS=()
    if [ -n "$REPLAY" ] && [ -d "$REPLAY" ]; then
        REPLAY_ARGS=(--replay-images "$REPLAY")
    else
        echo "replay: off (${REPLAY:-no folder given})"
    fi
    step prepare "$PY" "$TOOL" prepare --data "$DATA" --dim-copies "$DIM_COPIES" \
        --weights "$STOCK" "${REPLAY_ARGS[@]+"${REPLAY_ARGS[@]}"}"
    echo "  train now: $(find "$DATA/images/train" -name '*.png' | wc -l) screens"
fi

# --- smoke: one epoch on a tenth, before the real run -------------------------
if wanted smoke; then
    step smoke "$PY" "$TOOL" train --data "$DATA" --weights "$STOCK" --out "$OUT/smoke_run" \
        --epochs 1 --fraction 0.1 --batch "$BATCH"
    echo "want: 'smoke: OK' and a line 'best weights: ...'. CUDA out of memory -> BATCH=4"
fi

# --- train ---------------------------------------------------------------------
if wanted train; then
    step train "$PY" "$TOOL" train --data "$DATA" --weights "$STOCK" --out "$OUT/run" \
        --epochs "$EPOCHS" --batch "$BATCH" --lr0 "$LR0" --freeze "$FREEZE"
fi

# --- eval: stock against fine-tuned --------------------------------------------
BEST="$OUT/run/weights/best.pt"
if wanted eval; then
    if [ -f "$BEST" ]; then
        GUARDS=()
        [ -d data/synthetic/test/images ]      && GUARDS+=("synthetic-test=data/synthetic/test")
        [ -d data/realworld/images ]           && GUARDS+=("real-world=data/realworld")
        [ -d data/realworld-heldout/images ]   && GUARDS+=("held-out=data/realworld-heldout")
        STEP_TAIL=40 step eval "$PY" "$TOOL" eval --data "$DATA" \
            --weights "stock=$STOCK" "fine-tuned=$BEST" \
            --guard "${GUARDS[@]+"${GUARDS[@]}"}" --out "$OUT/eval"
    else
        echo "eval: SKIPPED - no $BEST (the train step did not finish)"
        FAILED_STEPS="$FAILED_STEPS eval"
    fi
fi

# --- one summary and one tarball -----------------------------------------------
{
    echo "# $(basename "$OUT") - icon model fine-tune"
    echo; cat "$OUT/gpu.txt"; echo
    if [ -f "$DATA/pack_info.json" ]; then echo '```'; cat "$DATA/pack_info.json"; echo; echo '```'; echo; fi
    [ -f "$OUT/eval.md" ] && cat "$OUT/eval.md"
    echo
    echo "How to read it: the fine-tune is worth keeping when recall on the test split and"
    echo "on the dimmed icons goes up AND recall on the guard sets does not go down by more"
    echo "than a point or two with a similar number of boxes per screen."
} > "$OUT/summary.md"
echo; cat "$OUT/summary.md"

if [ -n "$FAILED_STEPS" ]; then
    echo; echo "!! FAILED steps:$FAILED_STEPS - rerun them with TRAIN_ONLY before destroying the rental"
fi

# weights of the smoke run and intermediate epochs stay on the box; no screenshot goes in
TARBALL="$OUT.tar.gz"
if tar -czf "$TARBALL" --exclude='smoke_run' --exclude='last.pt' --exclude='epoch*.pt' \
        -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null; then
    echo; echo "done: $TARBALL ($(du -h "$TARBALL" | cut -f1))"
    echo "  the fine-tuned weights are inside: $(basename "$OUT")/run/weights/best.pt"
    echo "  download it, then destroy the instance (the screens are on its disk)"
fi
