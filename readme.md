# Visual DOM + Robot Framework GUI Automation (CV + Small LLM)

Turn a GUI **screenshot** into a UI-Automator-like **DOM** (bounds, roles, text,
labels, locators, hierarchy) using computer vision plus a small LLM/VLM — so GUI test
automation works even when **no accessibility tree exists** (custom-rendered Qt/OpenGL
UIs, embedded/industrial HMIs, or screens seen through a camera).

![System overview](report/figures/System_Overview.png)

**Docs site:** https://milanac030988.github.io/vizdom/ &nbsp;·&nbsp;
**Report:** [`report/`](report/) (general + arc42, each EN + VI) &nbsp;·&nbsp;
**ADRs:** [`docs/adr/`](docs/adr/)

## Benchmark (synthetic set, 44 test images)

Methodology and full per-type results in [`docs/EVALUATION.md`](docs/EVALUATION.md).

**Overall**

| Detector | F1 | mIoU | Actionable center-hit |
|---|---|---|---|
| UIED (CPU) | 0.51 | 0.68 | 0.89 |
| OmniParser | **0.58** | 0.67 | **0.97** |

**Recall by element type** — two lenses, IoU≥0.5 / center-hit (click-targetability):

| type | UIED (IoU / hit) | OmniParser (IoU / hit) |
|---|---|---|
| button | 0.82 / 0.96 | **1.00 / 1.00** |
| input_field | 0.95 / 0.99 | **0.99** / 0.99 |
| icon | 0.08 / 0.28 | **0.67 / 1.00** |
| checkbox | **0.68** / 0.82 | 0.20 / **0.87** |
| text | **0.79 / 0.99** | 0.59 / 0.98 |
| actionable (pooled) | 0.77 / 0.89 | **0.83 / 0.97** |

OmniParser leads on the actionable controls a test drives (button/input/icon), UIED
on checkbox and text. Both are click-targetable; OmniParser is essentially perfect on
actionable (0.97).

**Improvement — OmniParser element-type classification** (accuracy on actionable
controls), across the two stages it took: **before** (text/icon only) → **first fix**
(interactivity + geometry) → **now** (+ caption disambiguation + re-tuned width/aspect):

| type | before | first fix | now |
|---|---|---|---|
| button | 0.00 | 0.91 | 0.89 |
| input_field | 0.00 | 0.99 | 0.99 |
| checkbox | 0.00 | 0.12 | 0.55 |
| icon | 1.00\* | 0.00 | **0.89** |
| actionable | 0.09 | 0.73 | **0.87** |

\*old mapping labelled all non-text `icon`, so only icons scored correct. The first
fix (geometry) lifted actionable to 0.73 but regressed icons (→0.00) and barely moved
checkbox (0.12); the caption signal + width re-tune produced the current mapping.

## Documentation

📖 **Full user documentation is published at
<https://milanac030988.github.io/vizdom/>** — start there for installation,
configuration, and how to drive VizDOM from your own code or tests. Key pages:

| Page | What it covers |
|---|---|
| [Setup](https://milanac030988.github.io/vizdom/uv-setup/) | Install with `uv` / pip; environment and model weights |
| [Configuration & Sessions](https://milanac030988.github.io/vizdom/CONFIGURATION/) | The one JSON config that drives every stage (detector, OCR, merge, hierarchy, …) |
| [Using as a Client](https://milanac030988.github.io/vizdom/USAGE/) | Call VizDOM from **Python** (in-process or over **gRPC**) or the **Robot Framework** library |
| [Architecture](https://milanac030988.github.io/vizdom/architecture/) | Hexagonal ports, microservice-oriented gRPC services, diagrams |
| [CV Pipeline](https://milanac030988.github.io/vizdom/PIPELINE/) | The screenshot → DOM stages in detail |
| [Evaluation](https://milanac030988.github.io/vizdom/EVALUATION/) | Benchmark, metrics, dataset construction, before/after improvements |
| [Architecture Decisions](https://milanac030988.github.io/vizdom/adr/) | ADRs 001–023 |

The same content lives under [`docs/`](docs/) if you prefer to read it in the repo.

## Quick Start

### Installation

Installed with [**uv**](https://docs.astral.sh/uv/) — it fetches its own Python,
so no pre-existing local interpreter is required:

```bat
git clone <repo-url>
cd MasterProject

pip install uv                     :: once per machine
uv python install 3.12             :: managed CPython (~21 MB)
uv venv --python 3.12              :: creates .venv in the repo root

uv pip install -e ".[ocr]"         :: pipeline + Robot Framework library (CPU)
uv pip install -e ".[ocr,grpc]"    :: + detector / capture / actuator services
uv pip install -e ".[all]"         :: everything (incl. OmniParser: torch, ~2.5 GB)
```

The `start_*.bat` / `run_demo.bat` launchers detect `.venv` automatically. Full
guide — dependency groups, GPU notes, interpreter resolution order, and how to
install into an existing interpreter instead — in
**[Setup with uv](docs/uv-setup.md)**.

Verify with `start_capture.bat --list`, then
`uv run python -m pytest tests/unit tests/architecture -q`.

### Configure a session (recommended)

One JSON file configures every stage — detector/OCR choice, Stage 2.5 merge/dedup,
Stage 3 hierarchy, filters, refiner, capture. Generate a template, then use it from
Python or Robot Framework (see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)):

```bash
python -m visual_dom.config --init vizdom.config.json   # annotated template
```

```python
from visual_dom import connect
session = connect("vizdom.config.json")     # or connect() for defaults
dom = session.analyze("screenshot.png")     # -> Visual DOM dict
```

```robotframework
Connect              vizdom.config.json     # first step; drives all stages
Dump Visual DOM
Click Visual         text=Login
```

### Running the services (only for distributed setups)

For a **local, single-machine** run you don't need to start anything — `connect()`
and the Robot Framework library run the detector, capture, and actuator **in
process**. Start a service only when you want to split work across machines or share
one warm model:

| Service | When you need it | Start it (Windows launcher · any-OS command) |
|---|---|---|
| **Detector** `:50051` | Share one warm GPU model across clients / detect on a GPU box | `start_detector.bat --backend omniparser` · `python -m visual_dom.adapters.inbound.grpc.detector_server --backend omniparser --port 50051` |
| **Capture** `:50053` | Grab the screen on the device under test | `start_capture.bat --strategy windows` · `python -m visual_dom.adapters.inbound.grpc.capture_server --strategy windows --port 50053` |
| **Actuator** `:50054` | Click/type on the device or drive a robot arm | `start_actuator.bat --strategy desktop` · `python -m visual_dom.adapters.inbound.grpc.actuator_server --strategy desktop --port 50054` |

Prerequisite once: `pip install grpcio grpcio-tools`. The detector host also needs the
OmniParser weights (auto-detected under `models/omniparser/`). Then point the client
at the service(s) **through the config file**:

```json
{ "detector": { "backend": "grpc", "grpc_target": "gpu-host:50051" } }
```

…or via Robot Framework library arguments:

```robotframework
Library    VisualGuiLibrary    capture=grpc  capture_target=sut:50053
...                            actuator=grpc  actuator_target=sut:50054
```

**Other launchers:** `start_viewer.bat` (interactive PyQt DOM viewer for manual
checks) · `start_dashboard.bat` (Streamlit dashboard at `http://localhost:8501`).
Full walkthrough in the [Using as a Client](https://milanac030988.github.io/vizdom/USAGE/) guide.

### Run CV Pipeline Test

```bash
# Generate synthetic test UI screenshots
python tests/samples/generate_test_ui.py

# Run UIED detection test (no OCR required)
python -c "
import sys; sys.path.insert(0, 'src')
import cv2
from visual_dom.adapters.outbound.detectors.uied_detection import UIEDDetector

image = cv2.imread('tests/samples/login_screen.png')
detector = UIEDDetector()
elements = detector.detect(image)

for e in elements:
    print(f'{e.id}: {e.element_type.value} at {e.bounds}')
"

# Run full pipeline with OCR (requires easyocr)
python -m visual_dom.core.domain.pipeline tests/samples/login_screen.png \
    --output output/result.json \
    --visualize output/result.png
```

### OCR Setup

The pipeline supports multiple OCR backends:

**Option 1: EasyOCR (Recommended)**
```bash
# Requires PyTorch - best accuracy
pip install easyocr

# Test OCR
python tests/test_ocr_simple.py
```

**Option 2: Tesseract (Lightweight)**
```bash
# Install Tesseract OCR engine
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
# Linux: sudo apt install tesseract-ocr
# Mac: brew install tesseract

# Install Python bindings
pip install pytesseract

# Use in pipeline
python -c "
import sys; sys.path.insert(0, 'src')
from visual_dom.adapters.outbound.ocr.text_detector import TextDetector
import cv2

image = cv2.imread('tests/samples/login_screen.png')
detector = TextDetector(ocr_engine='tesseract', confidence_threshold=0.3)
texts = detector.detect(image)
for t in texts:
    print(f'{t.id}: \"{t.text}\" conf={t.confidence:.2f}')
"
```

**Option 3: PaddleOCR (Fast, Multi-language)**
```bash
pip install paddlepaddle paddleocr
```

**Troubleshooting OCR:**
- If you get PIL/Pillow import errors, reinstall: `pip install --force-reinstall Pillow`
- For EasyOCR on CPU: Set `gpu=False` in TextDetector
- First EasyOCR run downloads ~100MB of models

### Project Structure

```
MasterProject/
├── src/
│   ├── visual_dom/              # Core engine — hexagonal (ports & adapters)
│   │   ├── core/                # the hexagon interior (no I/O, no models)
│   │   │   ├── domain/          #   pipeline, hierarchy, compiler, schema, reading-order, cvops
│   │   │   └── ports/outbound/  #   port interfaces: detector_port, capture_port, actuator_port
│   │   ├── adapters/            # concrete implementations of the ports
│   │   │   ├── inbound/grpc/    #   driving: detector/capture/actuator gRPC servers
│   │   │   └── outbound/        #   driven: detectors/, ocr/, refiner/, capture/, actuator/
│   │   ├── context.py           # composition root (connect() / Session wiring)
│   │   ├── config.py            # one JSON session config (VizDomConfig)
│   │   ├── generated/           # protobuf stubs (gitignored; regenerated from protos/)
│   │   └── evaluation/          # evaluation harness (tooling, outside the hexagon)
│   └── visual_gui_library/      # Robot Framework library (thin client over capture + actuator)
│       ├── keywords/            # RF keywords (actions, assertions, capture)
│       └── locators/            # Locator strategies (id/text/hint/role/spatial)
├── plugins/                     # User plugins, auto-discovered
│   ├── capture/                 # e.g. example_static_image.py
│   └── actuator/                # e.g. example_robot_arm.py
├── protos/                      # gRPC contracts: detector/capture/actuator .proto
├── models/configs/              # Model registry code (weights fetched by setup script, not in git)
├── data/synthetic/              # Labelled evaluation benchmark
├── scripts/                     # setup_omniparser.py, process_gui_image.py, ...
├── report/                      # LaTeX reports (vizdom_report_en/vi, vizdom_architecture_en/vi) + figures/
├── docs/ + properdocs.yml       # ProperDocs site (+ docs/diagrams/*.puml, docs/adr/)
├── tools/                       # visual_dom_viewer (PyQt5), dashboard, annotator
├── start_*.bat                  # launchers: viewer, detector, capture, actuator, dashboard
└── output/                      # Generated sessions (JSON, PNG) — gitignored
```

### Architecture at a glance
Hexagonal (ports & adapters): a pure core depends on abstract ports — **Detector,
Ocr, Refiner, Capture, Actuator**. Each is a *strategy* selected by name, running
**in-process or as a remote gRPC service**, so you can capture on the device, detect
on a GPU box, and actuate on the SUT / a robot-arm controller. See
[`docs/architecture.md`](docs/architecture.md) and ADR-015/017/018/019.

---

## 1) Big Picture
This project has two tightly connected deliverables:

1) **Visual DOM Generator**  
Convert a **single GUI screenshot** into an **Android UIAutomator-like DOM JSON** (a visible view hierarchy), reconstructed from pixels using **Computer Vision (CV)** + a **small language model (LLM)**.

2) **Robot Framework Visual Automation Library**  
A Robot Framework library that consumes the generated DOM (and/or runs CV online) to provide **image-based GUI testing keywords** (click/type/verify/wait/scroll) without requiring runtime accessibility APIs or injected agents.

The goal is to make GUI testing feasible and maintainable in environments where object-based automation is hard or impossible (custom-rendered UI, weak accessibility, cross-platform desktop apps, etc.).

---

## 2) Why this matters
Traditional GUI automation is often **object-based** (DOM/accessibility tree/IDs). It breaks down when:
- The UI is custom rendered (e.g., Qt/OpenGL) and lacks a reliable accessibility tree
- Dumping UI structure requires platform-specific hooks or agent injection
- IDs/classnames are unstable or unavailable

A **visual-first** approach (like a human tester) can be more portable:
- Observe screen → locate target → interact
- Add structure (DOM) to reduce flakiness compared to raw coordinate clicking

---

## 3) Visual DOM Generator (Screenshot → UIAutomator-like JSON)

### Key idea: split responsibilities
- **CV handles geometry and evidence**: bounding boxes, OCR, coarse visual type
- **Small LLM handles structure/semantics**: parent–child relations, grouping, roles/flags  
  The LLM is **forbidden from generating coordinates**, to avoid hallucinated bounds.

### Pipeline overview
1) **Evidence extraction (CV)**
   - Text detection + OCR
   - Non-text proposals (icons/buttons/containers)
   - Merge & deduplicate candidates (NMS/IoU)
   - Output: `elements[]` with `id`, `bounds`, `ocr`, `visual_type`, `confidence`

2) **Coarse hierarchy (rules)**
   - Containment-based parent inference
   - Alignment grouping (rows/columns/list items)
   - Label association (nearest text to input/checkbox)

3) **Hierarchy refinement (small LLM)**
   - Input: `elements[]` + `tree_draft` + neighbor/layout hints
   - Output: constrained **tree-edits** (no numbers), e.g.:
     - `set_parent(E7 -> C2)`
     - `create_container(C2 type=LinearLayout children=[...])`
     - `set_role(E12=EditText hint="Email")`
     - `set_flags(E12 clickable=true editable=true)`

4) **DOM compiler**
   - Apply edits, validate, inject bounds from CV evidence
   - Export a stable, automation-friendly DOM JSON

### Output schema (v1)
- `elements[]`: raw evidence (debuggable)
- `hierarchy`: DOM tree for automation

---

## 4) Robot Framework Visual Automation Library

### What the library provides
A Robot Framework library exposing **visual keywords**, driven by:
- the **Visual DOM JSON**, plus
- optional online CV (for live re-detection and robustness)

#### Core keywords (minimal viable set)
- `Capture Screen` → returns screenshot reference
- `Dump Visual DOM` → produces DOM JSON from screenshot
- `Visual Should Exist` / `Visual Should Not Exist`
- `Wait Until Visual Appears` / `Wait Until Visual Disappears`
- `Click Visual`
- `Type Text Visual`
- `Clear Text Visual`
- `Scroll Visual` (container-aware)
- `Get Visual Element` (returns element metadata for debugging)
- `Bring App To Front` (raise the app under test so the grab and the clicks reach it)

### Locator strategies (robust by design)
Instead of relying on fragile coordinates, locators use the DOM:
- **By text**: `text="Login"`, `hint="Email"`
- **By role/type**: `role=Button`, `role=EditText`
- **By structure**: `within="LoginForm"`, `near text="Password"`
- **By relative position**: `right_of="Username"`, `below="Title"`
- **Fallback**: template/feature matching for icons if text is absent

> The DOM enables structure-aware locators, which is the key to reducing flakiness.

### How interaction works
For each action keyword:
1) Find target node(s) in DOM by locator query
2) Compute a safe **click point** (center or “clickable region” heuristic)
3) Perform the action via platform adapter:
   - Android: `adb input tap/text` (or instrumentation if available)
   - Desktop: `pyautogui`/Win32/X11 backend (configurable)
4) Post-check:
   - optional re-capture + verify state change (visual assertion)

---

## 5) Example usage (Robot Framework)
```robot
*** Settings ***
Library    VisualGuiLibrary

*** Test Cases ***
Login With Visual DOM
    ${img}=    Capture Screen
    ${dom}=    Dump Visual DOM    ${img}

    Wait Until Visual Appears    text=Email    timeout=10s
    Click Visual                 hint=Email
    Type Text Visual             hint=Email    user@example.com

    Click Visual                 hint=Password
    Type Text Visual             hint=Password    P@ssw0rd

    Click Visual                 text=Login
    Visual Should Exist          text=Welcome
```

---

## 6) Training Models

### Data Annotation

```bash
# Option 1: Simple web annotator
pip install flask
python tools/annotator/app.py --images data/raw/screenshots --output data/annotations
# Open http://localhost:5000

# Option 2: Label Studio (for team collaboration)
pip install label-studio
python scripts/annotation/setup_label_studio.py --project "UI Detection"
label-studio start
```

### Train CV Model (YOLOv8)

```bash
# Install training dependencies
pip install -e ".[cv-training]"

# Prepare dataset (after annotation)
python scripts/data_prep/convert_to_yolo.py --format labelstudio --input export.json --output data/ui_dataset

# Train
python scripts/training/cv/train_yolo.py --model yolov8s --data data/ui_detection.yaml --epochs 100

# Test inference
python scripts/training/cv/inference_yolo.py --model models/cv_detection/best.pt --image screenshot.png
```

### Train LLM (Hierarchy Refinement)

```bash
# Install training dependencies
pip install -e ".[training]"

# Prepare training data
python scripts/data_prep/create_training_data.py --annotations data/raw/annotations --output data/processed/train

# Finetune with LoRA
python scripts/training/finetune_lora.py --model qwen2.5-3b --data data/processed/train --epochs 3

# Evaluate
python scripts/evaluation/evaluate_model.py --model models/finetuned/qwen2.5-3b-lora
```

---

## 7) References

- **UIED Paper**: [Object Detection for Graphical User Interface](https://arxiv.org/abs/2008.05132) - Chen et al., 2020
- **UIED GitHub**: https://github.com/MulongXie/UIED

---

## 8) Development Status

| Milestone | Status | Description |
|-----------|--------|-------------|
| 1. Project Setup | ✅ Done | Project structure, dependencies, build config |
| 2. CV Pipeline | ✅ Done | UIED detection + multi-backend OCR (EasyOCR, PaddleOCR, Tesseract) |
| 3. Hierarchy Builder | ✅ Done | Rules-based containment, alignment grouping, label association |
| 4. LLM Refinement | ✅ Done | Tree-edit operations, prompt builder, Ollama/OpenAI backends, response parser |
| 5. DOM Compiler | ✅ Done | Edit application, validation, locator generation, JSON export |
| 6. DOM Schema & Evaluation | ✅ Done | JSON schema definition, IoU/hierarchy/locator metrics, HTML/MD/JSON reports |
| 7. RF Library Core | ✅ Done | Keywords (actions, assertions, capture), locator strategies, platform adapters |
| 8. Visual DOM Viewer | ✅ Done | PyQt5 interactive inspector, plugin system, Robot Framework export |
| 9. Research & Experiments | ✅ Done | VLM model testing (Florence-2, Qwen2-VL), LLM refinement benchmarks |
| 10. Pluggable detectors (ADR-015) | ✅ Done | UIED / YOLO / OmniParser behind one interface, selectable per run |
| 11. Distributed services (ADR-017/018/019) | ✅ Done | Hexagonal ports; gRPC detector/capture/actuator; user plugins (camera, robot-arm) |
| 12. Benchmark & evaluation | ✅ Done | Synthetic 44-img set; UIED vs OmniParser; OmniParser type-mapping 0.09→0.87 |
| 13. Docs site + report | ✅ Done | ProperDocs (GitHub Pages-ready); LaTeX reports (general + arc42, EN + VI) |
| 14. Client robustness (ADR-021/022/023/024) | ✅ Done | App targeting + focus on both ports (incl. `Focus` RPC); `desc=` grounding; post-action recap; <code>&#124;&#124;</code> fallback chains |
| 15. Real-world dataset & hardening | ⏳ Pending | Real-UI labelled benchmark; TLS/auth on gRPC; E2E production hardening |
