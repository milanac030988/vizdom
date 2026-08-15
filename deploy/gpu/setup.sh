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
# Explicit CUDA wheel index: the PyPI default torch on Linux is CUDA-enabled,
# but pin the index anyway so a resolver change cannot hand us a CPU wheel.
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
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
