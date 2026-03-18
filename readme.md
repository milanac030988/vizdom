# Visual DOM + Robot Framework GUI Automation (CV + Small LLM)

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd MasterProject

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install base dependencies
pip install -e .

# Install with OCR support
pip install -e ".[ocr]"

# Install all dependencies (for development)
pip install -e ".[ocr,training,cv-training,annotation,desktop,dev]"
```

### Run CV Pipeline Test

```bash
# Generate synthetic test UI screenshots
python tests/samples/generate_test_ui.py

# Run UIED detection test (no OCR required)
python -c "
import sys; sys.path.insert(0, 'src')
import cv2
from visual_dom.cv import UIEDDetector

image = cv2.imread('tests/samples/login_screen.png')
detector = UIEDDetector()
elements = detector.detect(image)

for e in elements:
    print(f'{e.id}: {e.element_type.value} at {e.bounds}')
"

# Run full pipeline with OCR (requires easyocr)
python -m src.visual_dom.cv.pipeline tests/samples/login_screen.png \
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
from visual_dom.cv import TextDetector
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
│   ├── visual_dom/              # Visual DOM Generator
│   │   ├── cv/                  # Computer Vision (UIED + OCR)
│   │   ├── hierarchy/           # Hierarchy building (coarse + LLM refiner)
│   │   ├── compiler/            # DOM compiler
│   │   ├── schema/              # JSON schema
│   │   └── evaluation/          # Evaluation framework (metrics, reports)
│   └── visual_gui_library/      # Robot Framework Library
│       ├── keywords/            # RF keywords (actions, assertions, capture)
│       ├── locators/            # Locator strategies
│       └── adapters/            # Platform adapters (desktop/android)
├── models/
│   ├── configs/                 # Model configurations
│   ├── pretrained/              # Downloaded models
│   └── finetuned/               # Your trained models
├── scripts/                     # Processing & visualization scripts
├── research/                    # VLM/LLM research experiments
├── tests/
│   ├── samples/                 # Test screenshots & ground truth
│   └── unit/                    # Unit tests
├── tools/
│   ├── annotator/               # Simple web annotation tool
│   └── visual_dom_viewer/       # Interactive DOM viewer (PyQt5)
│       ├── core/                # Data model, tree, state
│       ├── ui/                  # Main window, dialogs
│       ├── plugins/             # Platform handlers (Android, Windows, Visual DOM)
│       └── export/              # Robot Framework resource exporter
├── output/                      # Generated output files (JSON, PNG)
├── examples/                    # Usage examples
└── docs/                        # Documentation
```

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
| 10. Integration & E2E | ⏳ Pending | End-to-end testing, production hardening |
