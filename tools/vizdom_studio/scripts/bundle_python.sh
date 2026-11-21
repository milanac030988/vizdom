#!/usr/bin/env bash
# Linux counterpart of bundle_python.ps1: assemble everything the VizDOM Studio
# AppImage and .deb ship beside the Electron app, into tools/vizdom_studio/bundle/
# (electron-builder's extraResources):
#
#   bundle/python/   relocatable CPython (uv-managed, python-build-standalone) with
#                    VizDOM + the Robot Framework library ([robot,studio] extras)
#                    and CPU-only torch for EasyOCR
#   bundle/vizdom/   tools/vizdom_bridge, tools/visual_dom_viewer, plugins/, example config
#   bundle/easyocr/  EasyOCR's English models, fetched once so Studio works offline
#
# Tesseract is not bundled on Linux: the .deb recommends the distribution's
# tesseract-ocr package, and EasyOCR works without it.
#
# Usage (after: python scripts/gen_protos.py ; uv build --wheel):
#   bash tools/vizdom_studio/scripts/bundle_python.sh dist/vizdom-0.2.2-py3-none-any.whl
#   SKIP_EASYOCR_MODELS=1 PYTHON_VERSION=3.12 bash ... (optional)
#
# Needs uv on PATH (https://docs.astral.sh/uv/) and internet access (PyPI, the
# PyTorch CPU index, EasyOCR's model download). The smoke test imports pyautogui,
# which needs an X display: run under `xvfb-run -a` on a headless machine.
set -euo pipefail

wheel="${1:?usage: bundle_python.sh <path to the vizdom wheel>}"
python_version="${PYTHON_VERSION:-3.12}"

studio="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="$(cd "$studio/../.." && pwd)"
bundle="$studio/bundle"
wheel="$(cd "$(dirname "$wheel")" && pwd)/$(basename "$wheel")"

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }

command -v uv >/dev/null || { echo "uv is not on PATH: https://docs.astral.sh/uv/" >&2; exit 1; }
[[ -f "$wheel" ]] || { echo "no wheel at $wheel" >&2; exit 1; }

step "Clean $bundle"
rm -rf "$bundle"
mkdir -p "$bundle"

# --- 1. a relocatable interpreter ------------------------------------------------
step "Python $python_version (uv-managed, relocatable)"
pyhome="$bundle/_pyhome"
# --no-bin: no python3.x shim in ~/.local/bin, the build machine stays untouched
UV_PYTHON_INSTALL_DIR="$pyhome" uv python install --no-bin "$python_version"
# uv also creates a minor-version link (cpython-3.12-...) beside the real folder
# (cpython-3.12.16-...); take the real one, never the link
installed=""
for d in "$pyhome"/cpython-*; do
  if [[ -d "$d" && ! -L "$d" && -x "$d/bin/python3" ]]; then installed="$d"; break; fi
done
[[ -n "$installed" ]] || { echo "uv did not install a CPython under $pyhome" >&2; exit 1; }
echo "    using $(basename "$installed")"
# -L: plain files instead of symlinks (bin/python3 -> python3.12, ...), so the copy
# electron-builder makes into the AppImage and the .deb cannot lose a link
cp -rL "$installed" "$bundle/python"
rm -rf "$pyhome"
py="$bundle/python/bin/python3"
# uv marks its interpreters externally managed; this one is ours to fill
find "$bundle/python" -name EXTERNALLY-MANAGED -delete
"$py" --version

# --- 2. packages -----------------------------------------------------------------
step "CPU-only torch (EasyOCR's engine)"
uv pip install --python "$py" --break-system-packages --compile-bytecode \
  --index-url https://download.pytorch.org/whl/cpu torch torchvision

step "VizDOM + Robot Framework library from $(basename "$wheel")"
uv pip install --python "$py" --break-system-packages --compile-bytecode "vizdom[robot,studio] @ file://$wheel"

# --- 3. the code Studio runs that is not in the wheel ----------------------------
step "Bridge, Viewer exporters, plugins"
code="$bundle/vizdom"
mkdir -p "$code/tools"
for dir in tools/vizdom_bridge tools/visual_dom_viewer plugins; do
  if [[ -d "$repo/$dir" ]]; then
    mkdir -p "$code/$(dirname "$dir")"
    cp -r "$repo/$dir" "$code/$dir"
  fi
done
cp "$repo/vizdom.config.example.json" "$code/"
find "$code" -type d -name __pycache__ -prune -exec rm -rf {} +

# --- 4. OCR models ---------------------------------------------------------------
easy="$bundle/easyocr"
mkdir -p "$easy"
if [[ -z "${SKIP_EASYOCR_MODELS:-}" ]]; then
  step "EasyOCR English models"
  EASYOCR_MODULE_PATH="$easy" "$py" -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False); print('easyocr models ready')"
fi

# --- 5. smoke test: the bundle imports what Studio and a Robot suite need -------
step "Smoke test"
imports="import VisualGuiLibrary, visual_dom, visual_gui_library, vizdom_bridge.server, easyocr, mss, grpc, robot"
if [[ -n "${DISPLAY:-}" ]]; then
  imports="$imports, pyautogui"
else
  echo "    no DISPLAY: pyautogui not imported (run under xvfb-run -a to include it)"
fi
PYTHONPATH="$code/tools" VIZDOM_REPO="$code" VIZDOM_HOME="$bundle/_home" \
  "$py" -c "$imports; from visual_dom.generated import detector_pb2_grpc; print('imports ok, Robot Framework', robot.__version__)"
rm -rf "$bundle/_home"
find "$code" -type d -name __pycache__ -prune -exec rm -rf {} +

step "Bundle ready: $(du -sh "$bundle" | cut -f1) in $bundle"
