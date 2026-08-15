#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Prefetch every model the benchmark sweep needs, IN PARALLEL.
#
# Downloads are the single biggest time cost on a rented box (~80 GB total),
# so they all start at once and saturate the pipe while you do something else.
# hf download is resumable: rerunning after an interruption continues.
#
# Sizes (approx):
#   ELAM-7B                 ~15 GB
#   UI-TARS-1.5-7B          ~16 GB
#   Aria-UI-base            ~50 GB   (skipped automatically on < 20 GB GPUs)
#   OmniParser v2 weights   ~1.2 GB  (icon_detect + icon_caption_florence)
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
. .venv/bin/activate

VRAM_GB=$(python -c "import torch;print(int(torch.cuda.get_device_properties(0).total_memory/1e9))")
echo "GPU VRAM: ${VRAM_GB} GB"

pids=()
run_bg() { echo ">> $*"; "$@" & pids+=($!); }

run_bg huggingface-cli download sparks-solutions/ELAM-7B
run_bg huggingface-cli download ByteDance-Seed/UI-TARS-1.5-7B
if [ "$VRAM_GB" -ge 20 ]; then
    run_bg huggingface-cli download Aria-UI/Aria-UI-base
else
    echo "!! skipping Aria-UI (~50 GB): needs a >=20 GB card, this one has ${VRAM_GB} GB"
fi

# OmniParser weights, laid out where the pipeline's standard resolution finds them
run_bg huggingface-cli download microsoft/OmniParser-v2.0 \
    --local-dir models/omniparser_hf
run_bg git clone --depth 1 https://github.com/microsoft/OmniParser third_party/OmniParser

fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=1; done
[ "$fail" -eq 0 ] || { echo "FATAL: a download failed - rerun (resumable)"; exit 1; }

# Map the HF layout onto the paths the backends expect (see docs/omniparser-setup.md)
mkdir -p models/omniparser
[ -e models/omniparser/icon_detect ] || \
    ln -s "$(pwd)/models/omniparser_hf/icon_detect" models/omniparser/icon_detect
[ -e models/omniparser/icon_caption_florence ] || \
    ln -s "$(pwd)/models/omniparser_hf/icon_caption" models/omniparser/icon_caption_florence

# Optional: Ollama for the Qwen2-VL captioner combo (ADR-027). Never fatal.
if command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh; then
    (ollama serve >/dev/null 2>&1 &) ; sleep 3
    ollama pull qwen2.5vl:3b || echo "!! qwen2.5vl pull failed - captioner combo will be skipped"
fi

echo "prefetch done. Next: bash deploy/gpu/preflight.sh"
