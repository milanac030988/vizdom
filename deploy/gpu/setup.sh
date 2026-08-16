#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot environment setup for a RENTED GPU box (Ubuntu-family, CUDA driver
# preinstalled - the standard image on RunPod/Lambda/Vast).
#
# The meter is running: everything here is non-interactive and fails fast.
# Target: ready-to-benchmark in ~5 minutes + download bandwidth.
#
#   git clone <repo> && cd <repo>
#   bash deploy/gpu/setup.sh
#   bash deploy/gpu/prefetch.sh      # model downloads, run while reading on
#   bash deploy/gpu/preflight.sh     # 1-minute sanity BEFORE the long sweep
#   bash deploy/gpu/run_benchmarks.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "=== [1/5] system sanity ==="
nvidia-smi --query-gpu=name,memory.total --format=csv || {
    echo "FATAL: no NVIDIA driver visible"; exit 1; }

echo "=== [2/5] uv (standalone) ==="
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

echo "=== [3/5] Python env ==="
uv python install 3.12
uv venv --python 3.12
# shellcheck disable=SC1091
. .venv/bin/activate

echo "=== [4/5] dependencies (CUDA torch first, then the project) ==="
# Pick the torch wheel index from the GPU's actual compute capability:
# Blackwell cards (RTX 50xx, sm_120) need the cu128 wheels - the cu121 build
# installs fine and then dies at runtime with "no kernel image available",
# which on a rented box means paid time lost. Ampere/Ada (3090/4090/A-series)
# are happy on cu121.
COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
CUDA_INDEX="https://download.pytorch.org/whl/cu121"
case "$COMPUTE_CAP" in
    12.*|10.*) CUDA_INDEX="https://download.pytorch.org/whl/cu128" ;;
esac
echo "GPU compute capability $COMPUTE_CAP -> $CUDA_INDEX"
uv pip install torch torchvision --index-url "$CUDA_INDEX"
uv pip install -r requirements.txt -r requirements-training.txt
uv pip install grpcio grpcio-tools easyocr huggingface_hub[cli]
# grounders: UI-TARS needs qwen-vl-utils; 4-bit needs bitsandbytes (in training reqs)
uv pip install qwen-vl-utils

echo "=== [5/5] verify ==="
python - <<'PY'
import torch
assert torch.cuda.is_available(), "torch sees no CUDA - wrong wheel or driver"
p = torch.cuda.get_device_properties(0)
print(f"OK: {p.name}, {p.total_memory/1e9:.0f} GB VRAM, torch {torch.__version__}")
PY
echo "setup done. Next: bash deploy/gpu/prefetch.sh"
