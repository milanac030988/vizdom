#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot environment setup for a RENTED GPU box (Ubuntu-family, CUDA driver
# preinstalled - the standard PyTorch image on RunPod/Lambda/Vast).
#
# The meter is running: everything here is non-interactive and fails fast.
# Target: ready-to-benchmark in ~5 minutes + download bandwidth.
#
#   git clone <repo> && cd <repo>
#   bash deploy/gpu/setup.sh
#   bash deploy/gpu/prefetch.sh      # model downloads, run while reading on
#   bash deploy/gpu/preflight.sh     # 2-minute sanity BEFORE the long sweep
#   bash deploy/gpu/run_benchmarks.sh
#
# Builds TWO venvs, because the grounders' own Hub code disagrees on the
# transformers version (details at step 4):
#   .venv          transformers 4.49  - VizDOM/OmniParser/Florence-2, UI-TARS
#   .venv-legacy   transformers 4.47  - ELAM-7B (Molmo code), Aria-UI
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "=== [1/6] system sanity ==="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || {
    echo "FATAL: no NVIDIA driver visible"; exit 1; }
# Disk is fixed at rent time and cannot grow later. Models ~80 GB + the
# xet download cache + two venvs (~12 GB): a 16 GB default disk dies half-way
# through prefetch, after paid minutes. Fail NOW, before anything downloads.
AVAIL_GB=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
echo "free disk here: ${AVAIL_GB} GB"
if [ "${AVAIL_GB:-0}" -lt 120 ] && [ -z "${VIZDOM_SKIP_DISK_CHECK:-}" ]; then
    echo "FATAL: ${AVAIL_GB} GB free, need >= 120 GB (150+ recommended)."
    echo "       Destroy this instance and re-rent with the disk slider set."
    echo "       (VIZDOM_SKIP_DISK_CHECK=1 overrides, e.g. for a 7B-only run on ~70 GB.)"
    exit 1
fi
# tmux so the sweep survives a dropped SSH session; never fatal.
command -v tmux >/dev/null 2>&1 || (apt-get install -y -qq tmux >/dev/null 2>&1 || true)

echo "=== [2/6] uv (standalone) ==="
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "=== [3/6] Python env (main) ==="
uv python install 3.12
uv venv --python 3.12
# shellcheck disable=SC1091
. .venv/bin/activate

echo "=== [4/6] dependencies (CUDA torch first, then the project) ==="
# Pick the torch wheel index from the GPU's actual compute capability:
# Blackwell cards (RTX 50xx, sm_120) need the cu128 wheels - an older build
# installs fine and then dies at runtime with "no kernel image available",
# which on a rented box means paid time lost. Ampere/Ada (3090/4090/A-series)
# take cu126. NOT cu121: that index stops at torch 2.5.1, and current
# transformers refuses torch < 2.6 (it then disables PyTorch entirely and
# every grounder fails with "name 'torch' is not defined").
COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
CUDA_INDEX="https://download.pytorch.org/whl/cu126"
case "$COMPUTE_CAP" in
    12.*|10.*) CUDA_INDEX="https://download.pytorch.org/whl/cu128" ;;
esac
echo "GPU compute capability $COMPUTE_CAP -> $CUDA_INDEX"
uv pip install torch torchvision --index-url "$CUDA_INDEX"
uv pip install -r requirements.txt -r requirements-training.txt
# openai: imported unconditionally by OmniParser's util/utils.py (its GPT-4
# captioning path); without it the backend fails to import and the pipeline
# silently degrades to UIED. supervision/timm/einops: OmniParser + Florence-2.
# qwen-vl-utils: UI-TARS. bitsandbytes (4-bit) comes from the training reqs.
uv pip install grpcio grpcio-tools easyocr "huggingface_hub[cli]" openai \
    supervision timm einops qwen-vl-utils
# transformers is pinned, not floated: the models' own Hub code disagrees.
#   Florence-2 (OmniParser captions)  4.49 ok, 4.50+ "_supports_sdpa" error
#   UI-TARS-1.5 (Qwen2.5-VL)          >= 4.49
#   ELAM-7B (Molmo code)              <= 4.48 (_extract_past_from_model_output)
#   Aria-UI (old Llama attention)     <= 4.47 (LLAMA_ATTENTION_CLASSES)
#   -> the last two run from the legacy env built below
uv pip install "transformers==4.49.0"

echo "=== [5/6] legacy env for ELAM-7B + Aria-UI (transformers 4.47) ==="
deactivate
uv venv --python 3.12 .venv-legacy
# shellcheck disable=SC1091
. .venv-legacy/bin/activate
uv pip install torch torchvision --index-url "$CUDA_INDEX"
uv pip install -r requirements.txt -r requirements-training.txt
# sentencepiece: Aria's LlamaTokenizer. einops + tensorflow-cpu: ELAM's
# modeling file imports both at module top, so transformers' import check
# needs them present - the TF CPU wheel is enough, it is never used (USE_TF=0).
uv pip install "transformers==4.47.1" sentencepiece einops tensorflow-cpu
deactivate
# shellcheck disable=SC1091
. .venv/bin/activate

echo "=== [6/6] verify both envs ==="
for py in .venv/bin/python .venv-legacy/bin/python; do
    USE_TF=0 "$py" - <<'PY'
import sys, torch, transformers
assert torch.cuda.is_available(), "torch sees no CUDA - wrong wheel or driver"
assert transformers.utils.is_torch_available(), \
    f"transformers {transformers.__version__} rejects torch {torch.__version__}"
p = torch.cuda.get_device_properties(0)
print(f"OK {sys.prefix}: {p.name}, {p.total_memory/1e9:.0f} GB VRAM, "
      f"torch {torch.__version__}, transformers {transformers.__version__}")
PY
done
echo "setup done. Next: bash deploy/gpu/prefetch.sh"
