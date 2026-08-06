# Client Configuration & Sessions

VizDOM is configured with a single JSON file that a client provides **once** at
the start of a session. That one file drives every pipeline stage — which
detector and OCR engine to use and their parameters, the Stage 2.5 merge/dedup
tunables, the Stage 3 hierarchy tunables, size filters, the optional refiner, and
how screens are captured. Both the Python API (`connect`) and the Robot Framework
`Connect` keyword read the same file.

## 1. Get a template

Emit an annotated template with every field at its default value:

```bash
python -m visual_dom.config --init vizdom.config.json
```

Copy it, then delete or change only the keys you care about — anything omitted
keeps its default. Validate a hand-edited file at any time:

```bash
python -m visual_dom.config --check vizdom.config.json
```

Unknown keys are rejected (so a typo like `backendd` fails loudly instead of being
silently ignored). Keys beginning with `_` (e.g. the `_help` block in the
template) are treated as comments and ignored.

A configured OCR engine that isn't installed also **fails fast** at
`connect()` with an install hint — e.g. `ocr.engine: "paddleocr"` without the
package raises rather than silently falling back to the detector's own OCR, which
previously caused a quiet drop in text quality.

## 2. Use it from Python

```python
from visual_dom import connect

session = connect("vizdom.config.json")   # or connect() for all-defaults
dom = session.analyze("screenshot.png")   # -> compiled Visual DOM dict
dom = session.analyze(bgr_numpy_array, save_path="out.json")
```

The detector/OCR/refiner models load **once** when the session is created and are
reused for every `analyze` call, so a batch or a test suite pays that cost only
once.

## 3. Use it from Robot Framework

`Connect` is the recommended first keyword. After it, `Dump Visual DOM` uses the
configured session for all stages:

```robotframework
*** Settings ***
Library    VisualGuiLibrary

*** Test Cases ***
Login Works
    Connect              vizdom.config.json     # configure the whole session
    Dump Visual DOM                             # uses the config above
    Click Visual         text=Login
    Visual Should Exist  text=Welcome
```

Call `Connect` with no argument for all-defaults. The config's `capture` section
(`strategy` / `target` / `camera_mode`) is applied to the library's capture port
too, so one file configures both DOM generation **and** screen acquisition — e.g.
capture from a remote device over gRPC:

```json
"capture": { "strategy": "grpc", "target": "sut-device:50053" }
```

When a session is connected, the per-call arguments of `Dump Visual DOM`
(`ocr_engine`, `use_llm`, `llm_model`) are ignored — the config wins. They only
apply to the ad-hoc path used when `Connect` was never called.

## 4. What each section controls

The template groups options by pipeline stage:

| Section | Stage | Key options |
|---|---|---|
| `detector` | Stage 2 — element detection | `backend` (`uied`/`yolo`/`omniparser`/`hybrid`), `use_gpu`, `confidence_threshold`, OmniParser weight paths + `omniparser_text_ensemble` |
| `ocr` | Stage 1 — text detection | `engine` (`easyocr`/`paddleocr`/`tesseract`/`none`), `languages` |
| `refiner` | Stage 8 — SLM/VLM review | `enabled`, `backend`, `model`, `host` |
| `merge` | **Stage 2.5 — Merge & Deduplicate** | `nms_iou_threshold`, `cross_type_iou`, `duplicate_tolerance_px`, `merge_oversegmented`, `group_fill_ratio_min` |
| `hierarchy` | **Stage 3 — Hierarchy Building** | `containment_threshold`, `min_containment_margin`, `use_llm`, `llm_model` |
| `symbols` | Stage 4c — glyph/operator reading (`+ − = × ÷ …`) | `enabled`, `min_score` (null = calibrated ~0.70; raise = stricter, lower = recover faint glyphs) |
| `filter` | size / count filters | `min_element_area`, `min_element_size`, `max_elements` |
| `capture` | acquisition (ADR-018) | `strategy`, `target`, `camera_mode` |
| `grounding` | `desc=` locator resolution (ADR-022) | `tiers` (`lexical`/`slm`/`vlm`, escalation order), `backend`, `model`, `vision_model`, `host` |
| `output` | DOM compilation | `generate_locators` |

Filters and thresholds expressed in pixels are **resolution-aware**: they are
defined at 1080p and scaled up automatically for higher-resolution screens.

### Common recipes

**Best actionable-control accuracy (GPU), OmniParser with text ensemble:**

```json
{
  "detector": { "backend": "omniparser", "use_gpu": true },
  "ocr": { "engine": "easyocr" }
}
```

**CPU-only, no GPU, classical baseline:**

```json
{
  "detector": { "backend": "uied", "use_gpu": false },
  "ocr": { "engine": "tesseract" }
}
```

**Denser detection (recover small/adjacent elements) — loosen filters and NMS:**

```json
{
  "detector": { "confidence_threshold": 0.2 },
  "merge": { "nms_iou_threshold": 0.6, "cross_type_iou": 0.5 },
  "filter": { "min_element_area": 60, "max_elements": 400 }
}
```

**Recover faint small controls with OmniParser (e.g. a minimize "–" button):**
A tiny low-contrast glyph can sit just under OmniParser's YOLO confidence cutoff
(default 0.05) and be missed — sometimes only on certain captures, since YOLO runs
at a fixed input size and is sensitive to the exact screenshot resolution. Lower the
cutoff to recover it (0.03 is usually clean; below ~0.02 starts adding noise):

```json
{
  "detector": { "backend": "omniparser", "omniparser_box_threshold": 0.03 }
}
```

**Add a small-LM review pass (needs a running Ollama):**

```json
{
  "refiner": { "enabled": true, "backend": "ollama", "model": "qwen2.5:3b" }
}
```
