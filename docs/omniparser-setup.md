# OmniParser Detector Backend — Setup

This project can use **Microsoft OmniParser** as an alternative element-detection
backend (alongside the default `uied` and `yolo`). See
[ADR-015](adr/015-pluggable-detector-backends.md) for the design and
[the landscape comparison](discussion/landscape-comparison-en.md) for why.

> **Licensing.** OmniParser's `icon_detect` is **AGPL-3.0** (via Ultralytics/YOLO);
> `icon_caption` is MIT; the repo is CC-BY-4.0. This project is **already** on AGPL
> through its existing Ultralytics dependency, so this adds no new licence class —
> but shipping or network-serving the project with this backend active carries AGPL
> obligations. For permissive reuse, prefer an Apache-licensed detector instead.

## Quick start

Run the setup script with the **same interpreter the app uses** (the Viewer and
dashboard run on Python 3.9 at `%VIZDOM_PY%`):

```bat
"%VIZDOM_PY%" scripts\setup_omniparser.py --install-deps
```

Then launch `start_viewer.bat` and choose **`omniparser`** in the **Det** dropdown.
No environment variables are needed — the app auto-detects the default paths.

## What the environment already has (Python 3.9)

Checked on this machine:

| Dependency | Status |
|---|---|
| torch 2.4.1 + CUDA 12.4 | ✅ present (GPU works) |
| transformers 4.46 | ✅ present |
| opencv, numpy, einops, timm, easyocr, Pillow | ✅ present |
| **ultralytics** | ❌ missing — needed for icon_detect |
| **supervision** | ❌ missing — needed by OmniParser utils |

So only two packages need installing. `--install-deps` handles them.

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
REM 1. deps (into the 3.9 env)
"%VIZDOM_PY%" -m pip install ultralytics supervision huggingface_hub

REM 2. clone the repo (provides util.utils)
git clone --depth 1 https://github.com/microsoft/OmniParser.git third_party\OmniParser

REM 3. weights
"%VIZDOM_PY%" -c "from huggingface_hub import snapshot_download; snapshot_download('microsoft/OmniParser-v2.0', local_dir='models/omniparser', allow_patterns=['icon_detect/*','icon_caption/*'])"
move models\omniparser\icon_caption models\omniparser\icon_caption_florence
```

## Running it

**Viewer:** `start_viewer.bat` → set **Det** to `omniparser`. If weights/repo are
missing it prints a warning and falls back to `uied` (never crashes).

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

3. **protobuf pin:** this project uses `protobuf==4.25.5` (satisfies streamlit
   `>=3.20,<6`). TensorFlow 2.10 is consequently unusable, but it was already in
   conflict with streamlit before and is not used by this project.

4. **Broken `psutil` in the Roaming user-site** (`%1 is not a valid Win32
   application`, a 32-bit/64-bit mismatch) shadows a good psutil in the main
   site-packages. It does not block OmniParser (ultralytics imports fine without
   it), but if something later needs psutil, remove
   the per-user copy (`%APPDATA%\Python\Python39\site-packages\psutil`) so the
   correct build in the interpreter's own `Lib\site-packages` is used.
   *(Paths in this note are from the author's workstation; adjust to yours.)*

## Version caveat

OmniParser's `util.utils` API and weight layout have drifted across releases
(e.g. a newer `icon_detect_v3` / YOLOv9-E variant exists on an unmerged PR
branch; the stable `main` uses `icon_detect`). If the caption/detector call
signatures differ from what this integration expects, adjust
`_parse_content_list` and the `detect()` call in
`src/visual_dom/cv/detectors/omniparser_backend.py` — the version-sensitive
parts are isolated there on purpose.
