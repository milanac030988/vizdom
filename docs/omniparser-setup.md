# OmniParser Detector Backend — Setup

VizDOM can use **Microsoft OmniParser** as its element-detection backend
(`omniparser`), alone or as stage 1 of the `modular` detector, beside the CPU
`uied` and `yolo` backends. See
[ADR-015](adr/015-pluggable-detector-backends.md) for the design and
[the landscape comparison](discussion/landscape-comparison-en.md) for why.
It needs a GPU to be fast, so it usually runs on one GPU host as the detector
service (`vizdom-detector --backend omniparser`).

> **Licensing.** VizDOM itself is MIT. OmniParser's `icon_detect` is **AGPL-3.0**
> (via Ultralytics/YOLO), `icon_caption` is MIT, and the OmniParser repository is
> CC-BY-4.0. None of it is distributed with VizDOM: the `omniparser` extra installs
> Ultralytics and the setup script below fetches OmniParser onto your machine, so
> the AGPL applies to that installation. Shipping or network-serving it carries
> AGPL obligations; the `uied` backend avoids them.

## Quick start

OmniParser needs a **source checkout** (the setup script and the `third_party/`
and `models/` folders live in the repository; see [Setup](uv-setup.md)). Install
the `omniparser` extra, then run the setup script with the **same interpreter the
detector will use**:

```bat
uv pip install -e ".[robot,omniparser]"
uv run python scripts\setup_omniparser.py --install-deps
```

Then select it: `"detector": { "backend": "omniparser" }` in `vizdom.config.json`,
the detector setting in the Viewer (*Settings*, `Ctrl+,`), or
`vizdom-detector --backend omniparser` for the service. No environment variables
are needed; the default paths are found automatically.

The `omniparser` extra already brings `ultralytics` (for `icon_detect`),
`supervision` and `huggingface_hub`; `--install-deps` only installs them into an
environment that was set up without the extra.

## What the script does

1. **Deps** — installs `ultralytics` and `supervision` (with `--install-deps`).
2. **Repo** — clones OmniParser to `third_party/OmniParser` (provides `util.utils`).
3. **Weights** — downloads v2 weights from `microsoft/OmniParser-v2.0` into
   `models/omniparser/` and renames `icon_caption` → `icon_caption_florence`.

Resulting layout (all auto-detected by the app):

```
third_party/OmniParser/                 # OMNIPARSER_ROOT
models/omniparser/
  icon_detect/model.pt                  # OMNIPARSER_ICON_DETECT
  icon_caption_florence/                # OMNIPARSER_ICON_CAPTION
    config.json, generation_config.json, model.safetensors
```

## Manual setup (if you prefer, or the script fails)

```bat
REM 1. deps (into the environment the detector runs in)
uv pip install ultralytics supervision huggingface_hub

REM 2. clone the repo (provides util.utils)
git clone --depth 1 https://github.com/microsoft/OmniParser.git third_party\OmniParser

REM 3. weights
uv run python -c "from huggingface_hub import snapshot_download; snapshot_download('microsoft/OmniParser-v2.0', local_dir='models/omniparser', allow_patterns=['icon_detect/*','icon_caption/*'])"
move models\omniparser\icon_caption models\omniparser\icon_caption_florence
```

## Running it

**Service:** `vizdom-detector --backend omniparser --ocr easyocr --port 50051`
on the GPU host; clients use `"detector": { "backend": "grpc", "grpc_target": "gpu-host:50051" }`.

**Viewer:** `start_viewer.bat` → *Settings* → detector `omniparser`. If weights/repo
are missing it prints a warning and falls back to `uied` (never crashes).

**CLI:**

```bat
python scripts\process_gui_image.py <image.png> --detector omniparser
```

Override paths explicitly if you keep weights elsewhere:

```bat
python scripts\process_gui_image.py <image.png> --detector omniparser ^
  --omniparser-root C:\path\to\OmniParser ^
  --omniparser-icon-detect  C:\path\to\icon_detect\model.pt ^
  --omniparser-icon-caption C:\path\to\icon_caption_florence
```

…or set `OMNIPARSER_ROOT`, `OMNIPARSER_ICON_DETECT`, `OMNIPARSER_ICON_CAPTION`.

## Notes & gotchas (encountered during first real setup, 2026-07-24)

Verified end-to-end on `tests/samples/calculator.png` → 53 elements with boxes,
interactability and text, on GPU. Two issues had to be worked around:

1. **PaddleOCR is imported *and instantiated* at the top of OmniParser's
   `util/utils.py`.** Even though we drive it with easyocr (`use_paddleocr=False`),
   the module won't import without paddle. Installing `paddlepaddle`/`paddleocr`
   is a trap: paddle pulls **protobuf 6.x**, which conflicts with the dashboard's
   streamlit (`protobuf<6`). Instead, `setup_omniparser.py` **patches
   `util/utils.py` to make PaddleOCR lazy** (`_ensure_paddle_ocr()`), so paddle is
   never needed. Do **not** install paddlepaddle into this env.

2. **transformers auto-imports TensorFlow 2.10**, whose protobuf-generated code
   breaks under protobuf ≥ 3.20 ("Descriptors cannot be created directly").
   Florence-2 runs on torch, so TF is unwanted. `omniparser_backend.py` sets
   `USE_TF=0` / `USE_FLAX=0` at import (before transformers loads) to prevent this.

3. **protobuf pin:** the project constrains `protobuf<6` (streamlit needs
   `>=3.20,<6`, and the gRPC stubs are generated for it). TensorFlow 2.10 is
   consequently unusable, but it is not used by this project.

4. **A broken `psutil` in the per-user site-packages** (`%1 is not a valid Win32
   application`, a 32-bit/64-bit mismatch) can shadow a good psutil in the
   interpreter's own site-packages. It does not block OmniParser (ultralytics
   imports fine without it), but if something later needs psutil, remove the
   per-user copy under `%APPDATA%\Python\Python3xx\site-packages\psutil`.

## Version caveat

OmniParser's `util.utils` API and weight layout have drifted across releases
(e.g. a newer `icon_detect_v3` / YOLOv9-E variant exists on an unmerged PR
branch; the stable `main` uses `icon_detect`). If the caption/detector call
signatures differ from what this integration expects, adjust
`_parse_content_list` and the `detect()` call in
`src/visual_dom/adapters/outbound/detectors/omniparser_backend.py` — the version-sensitive
parts are isolated there on purpose.
