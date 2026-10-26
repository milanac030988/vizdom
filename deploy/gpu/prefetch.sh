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
#   Aria-UI-base            ~50 GB   (skipped automatically on < 46 GB GPUs)
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

# huggingface_hub >= 1.0 ships only `hf`; older releases only `huggingface-cli`.
if command -v hf >/dev/null 2>&1; then HF=hf; else HF=huggingface-cli; fi
command -v "$HF" >/dev/null 2>&1 || { echo "FATAL: no HF CLI in the venv"; exit 1; }

run_bg "$HF" download sparks-solutions/ELAM-7B
run_bg "$HF" download ByteDance-Seed/UI-TARS-1.5-7B
# Aria-UI: bnb 4-bit does not quantize its MoE experts, so a 24 GB card OOMs
# at shard 5/12 (measured 2026-10-26; ~50 GB extrapolated). Only worth 50 GB
# of bandwidth on a 48 GB card; the gate is 46 (same as AriaUiGrounder) so an
# A100 40 GB, which reports 42, is skipped too.
if [ "$VRAM_GB" -ge 46 ]; then
    run_bg "$HF" download Aria-UI/Aria-UI-base
else
    echo "!! skipping Aria-UI (~50 GB): needs a 48 GB card (A6000/L40S), this one has ${VRAM_GB} GB"
fi

# OmniParser weights, laid out where the pipeline's standard resolution finds them
run_bg "$HF" download microsoft/OmniParser-v2.0 \
    --local-dir models/omniparser_hf
if [ -d third_party/OmniParser/.git ]; then
    echo ">> third_party/OmniParser already cloned - skipping"
else
    run_bg git clone --depth 1 https://github.com/microsoft/OmniParser third_party/OmniParser
fi

fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=1; done
[ "$fail" -eq 0 ] || { echo "FATAL: a download failed - rerun (resumable)"; exit 1; }

# OmniParser's util/utils.py imports+instantiates PaddleOCR at module top; we
# drive it with easyocr and never install paddle, so make that lazy (the same
# idempotent patch the laptop setup applies - see docs/omniparser-setup.md).
python scripts/setup_omniparser.py --skip-weights

# Map the HF layout onto the paths the backends expect (see docs/omniparser-setup.md)
mkdir -p models/omniparser
[ -e models/omniparser/icon_detect ] || \
    ln -s "$(pwd)/models/omniparser_hf/icon_detect" models/omniparser/icon_detect
[ -e models/omniparser/icon_caption_florence ] || \
    ln -s "$(pwd)/models/omniparser_hf/icon_caption" models/omniparser/icon_caption_florence

# Optional: Ollama for the Qwen2-VL captioner combo (ADR-027). Opt-in: the
# ollama-backed Captioner is not implemented yet, so by default this would
# only cost a 3 GB pull and paid bandwidth for a combo parity_on_box.py then
# reports as unavailable. Never fatal.
if [ -n "${VIZDOM_PREFETCH_OLLAMA:-}" ]; then
    if command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh; then
        (ollama serve >/dev/null 2>&1 &) ; sleep 3
        ollama pull qwen2.5vl:3b || echo "!! qwen2.5vl pull failed - captioner combo will be skipped"
    fi
fi

echo "free disk after prefetch: $(df -h . | awk 'NR==2{print $4}') (sweep needs ~20 GB more)"
echo "prefetch done. Next: bash deploy/gpu/preflight.sh"
