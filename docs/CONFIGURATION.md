# Client Configuration & Sessions

VizDOM is configured with a single JSON file that a client provides **once** at
the start of a session. That one file drives every pipeline stage — which
detector and OCR engine to use and their parameters, the Stage 2.5 merge/dedup
tunables, the Stage 3 hierarchy tunables, size filters, the optional refiner, and
how screens are captured and input delivered. Both the Python API (`connect`) and the Robot Framework
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

Call `Connect` with no argument for all-defaults. The config's `capture` and
`actuator` sections are applied to the library's ports too, so **one file
configures all three**: DOM generation (detector), screen acquisition, and input
— each independently local or a remote gRPC service:

```json
{
  "detector": { "backend": "grpc",  "grpc_target": "gpu-host:50051" },
  "capture":  { "strategy": "grpc", "target":      "sut-host:50053" },
  "actuator": { "strategy": "grpc", "target":      "sut-host:50054" }
}
```

The test file is byte-identical between a local and a fully distributed run — only
this file changes. A runnable example is in
`examples/windows_calculator_demo/`.

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
| `symbols` | Stage 4c — glyph/operator reading (`+ − = × ÷ …`) | `enabled`, `min_score` (structure decides; the threshold only vetoes low template agreement) |
| `filter` | size / count filters | `min_element_area`, `min_element_size`, `max_elements` |
| `capture` | acquisition (ADR-018) | `strategy`, `target`, `camera_mode`, `window_title` + `focus_before_capture` + `window_scope` (app targeting, ADR-021) |
| `actuator` | input delivery (ADR-019) | `strategy` (`desktop`/`android`/`grpc`/plugin), `target` (host:port when `grpc`), `window_title` (ADR-021) |
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

**Name the application under test, and capture only it (ADR-021):**

```json
{
  "capture":  { "strategy": "windows", "window_title": "Calculator",
                "window_scope": true },
  "actuator": { "strategy": "desktop" }
}
```

`window_scope` captures the window's client area instead of the whole screen, so the
DOM contains just that application — no desktop, no other windows. It works
identically with `"strategy": "grpc"`: the crop is performed on the machine that owns
the screen and its geometry travels back with the pixels, so clicks stay correct even
for a window on a second monitor (which can start at a *negative* screen coordinate).

Use `focus_before_capture` instead when you want the whole screen but need the app in
front. `window_scope` already implies focusing, since a crop of an occluded window
would show whatever covers it:

```json
{
  "capture":  { "strategy": "windows", "window_title": "Calculator",
                "focus_before_capture": true }
}
```

`window_title` is the window to raise (on Android a package or
`package/.Activity`); `actuator.window_title` inherits it when omitted, since both
ports normally drive the same app. With `focus_before_capture` the SUT is raised
before every grab — including the ADR-023 element recap — so the DOM is built from
the application under test instead of whatever window happens to be on top.

!!! note "Focus is verified, and can legitimately fail"
    Raising a window is an *action*: it can dismiss tooltips or transient popups,
    and Windows may refuse it outright (foreground lock). VizDOM therefore checks
    that the window really became foreground rather than assuming success. A
    failure during `focus_before_capture` only **warns** (the grab may still be
    fine); use the explicit `Bring App To Front` keyword where it must be fatal.
    An ambiguous title (two windows matching) fails instead of guessing. With
    `window_scope`, a strategy that cannot scope to a window (a camera, an older
    service) falls back to a full-screen grab **with a warning** — element
    coordinates stay correct, but the DOM will include other windows.

<!-- BEGIN GENERATED CONFIG REFERENCE (scripts/gen_config_reference.py) -->

## 5. Full parameter reference

Every field, generated from the config dataclasses and their in-code help
(the same text `--init` embeds as the template's `_help` block) — a unit test
keeps this section in sync with the code. `null` means "use the default
described here".

### `detector` — Stage 2 - element detection backend and its parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `backend` | str | `"uied"` | uied (CPU baseline) \| yolo \| omniparser (best actionable) \| hybrid |
| `use_gpu` | bool | `true` | run the detector on CUDA when available (OmniParser/YOLO); UIED is CPU-only |
| `confidence_threshold` | float | `0.3` | 0..1; lower = more detections (higher recall) |
| `yolo_model_path` | str | `null` | path to trained YOLO weights (required for backend=yolo/hybrid) |
| `omniparser_icon_detect_path` | str | `null` | null = auto-resolve from models/omniparser/ |
| `omniparser_icon_caption_path` | str | `null` | null = auto-resolve from models/omniparser/icon_caption_florence |
| `omniparser_text_ensemble` | bool | `true` | feed VizDOM OCR into OmniParser to recover text (ADR-016) |
| `omniparser_box_threshold` | float | `0.05` | YOLO icon confidence cutoff (default 0.05); lower to ~0.03 to recover faint glyphs like a minimize button |
| `grpc_target` | str | `"localhost:50051"` | host:port of a running detector gRPC service (used only when backend == 'grpc', ADR-017) |

### `ocr` — Stage 1 - text detection engine

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `engine` | str | `"easyocr"` | easyocr \| paddleocr \| tesseract \| none |
| `languages` | list of str | `['en']` | OCR language codes passed to the engine, e.g. ["en"] |
| `confidence_threshold` | float | `0.3` | drop OCR detections below this confidence (0..1) |

### `refiner` — Stage 8 - optional small-LM/VLM element review (needs a running backend)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `false` | run the optional small-LM/VLM element review stage (needs a running backend) |
| `backend` | str | `"ollama"` | ollama \| openai |
| `model` | str | `"qwen2.5:3b"` | model for the review pass, e.g. qwen2.5:3b |
| `host` | str | `"http://localhost:11434"` | backend endpoint, e.g. http://localhost:11434 |

### `merge` — Stage 2.5 - Merge & Deduplicate

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `nms_iou_threshold` | float | `0.5` | per-type non-max-suppression IoU |
| `cross_type_iou` | float | `0.4` | suppress overlapping boxes of different types above this IoU |
| `duplicate_tolerance_px` | int | `5` | boxes whose corners differ by <= this many px (at 1080p) are duplicates |
| `merge_oversegmented` | bool | `true` | fuse split multi-line labels/buttons back together |
| `group_fill_ratio_min` | float | `0.5` | apply a merge only when members fill >= this fraction of the merged box (guards against fusing distinct controls) |

### `hierarchy` — Stage 3 - Hierarchy Building (containment tree)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `containment_threshold` | float | `0.85` | fraction of a child's area that must sit inside its parent |
| `min_containment_margin` | int | `5` | minimum px margin between child and parent edges for nesting |
| `use_llm` | bool | `false` | let the refiner LLM adjust the built hierarchy (needs refiner.enabled) |
| `llm_model` | str | `"ollama"` | model used for LLM hierarchy refinement |

### `symbols` — Stage 4c - glyph/operator reading (+ - = x / etc.) via template matching

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | run the glyph/operator reader (stage 4c) on textless elements |
| `min_score` | float | `null` | null = structure decides (default); a value adds a template-agreement veto (raise = stricter) |

### `filter` — resolution-aware size/count filters (referenced to 1080p)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `min_element_area` | int | `100` | drop elements smaller than this area in px^2 (referenced to 1080p) |
| `min_element_size` | int | `10` | drop elements narrower or shorter than this many px (referenced to 1080p) |
| `max_elements` | int | `200` | cap on elements kept per screen |

### `capture` — how screens are acquired (RF client layer, ADR-018)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `strategy` | str | `null` | null=auto \| windows \| linux \| android \| camera \| grpc \| <plugin> |
| `target` | str | `null` | host:port of a running capture gRPC service (when strategy == grpc) |
| `camera_mode` | bool | `false` | rectify a physical screen photographed by a camera before analysis |
| `window_title` | str | `null` | app under test to raise: window title, or package[/.Activity] on Android (ADR-021) |
| `focus_before_capture` | bool | `false` | raise window_title before every grab, so the DOM is built from the app under test and not from whatever window is on top |
| `window_scope` | bool | `false` | capture ONLY window_title's client area instead of the whole screen, so the DOM contains just that app (implies focusing; falls back to full screen with a warning if the strategy cannot) |

### `actuator` — how input is delivered (RF client layer, ADR-019)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `strategy` | str | `null` | null=platform default \| desktop \| android \| grpc \| <plugin> |
| `target` | str | `null` | host:port of a running actuator gRPC service (when strategy == grpc) |
| `window_title` | str | `null` | app to raise for input; null = inherit capture.window_title (ADR-021) |

### `grounding` — desc= locator resolution (ADR-022): tiered natural-language grounding

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `tiers` | list of str | `['lexical', 'slm']` | escalation order; lexical (no model) \| slm (text LM over DOM) \| vlm (Set-of-Mark over image, opt-in) |
| `backend` | str | `"ollama"` | ollama \| openai (for the slm/vlm tiers) |
| `model` | str | `"qwen2.5:3b"` | text model for the slm tier |
| `vision_model` | str | `"qwen2.5-vl:3b"` | vision model for the vlm (Set-of-Mark) tier |
| `host` | str | `"http://localhost:11434"` | backend endpoint for the grounding tiers |

### `output` — DOM compilation options

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `generate_locators` | bool | `true` | emit ready-made locator suggestions per element into the DOM |

<!-- END GENERATED CONFIG REFERENCE -->
