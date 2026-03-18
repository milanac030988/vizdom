# Visual DOM Pipeline - Technical Documentation

## Overview

The Visual DOM Pipeline is a Computer Vision-based system that extracts UI element information from screenshots and generates structured DOM (Document Object Model) representations. This enables UI automation without requiring access to platform-specific accessibility APIs.

**Goal**: Convert a screenshot image into a hierarchical JSON structure containing all UI elements with their properties and locators.

```
┌──────────────┐      ┌──────────────────────────────────────┐      ┌──────────────┐
│  Screenshot  │  →   │       Visual DOM Pipeline            │  →   │   DOM JSON   │
│    (PNG)     │      │  (CV + OCR + Hierarchy + Compiler)   │      │   (Output)   │
└──────────────┘      └──────────────────────────────────────┘      └──────────────┘
```

---

## Pipeline Stages

The pipeline consists of **4 main stages** plus an **optional LLM refinement stage**:

| Stage | Name | Technique | Purpose |
|-------|------|-----------|---------|
| 1 | Text Detection | EasyOCR (Deep Learning) | Extract text elements |
| 2 | Non-text Detection | UIED Algorithm (Classical CV) | Detect buttons, icons, inputs |
| 3 | Hierarchy Building | Rule-based Heuristics | Build parent-child tree |
| 3.5 | LLM Refinement | Small Language Models (Optional) | Refine and fix errors |
| 4 | DOM Compilation | Deterministic Processing | Generate final JSON with locators |

---

## Stage 1: Text Detection (OCR)

### Purpose
Detect and recognize all text elements in the screenshot.

### Model/Technique
**EasyOCR** - A deep learning-based OCR engine

| Property | Value |
|----------|-------|
| Model Architecture | CRAFT (Character Region Awareness) + CRNN |
| Text Detection | CRAFT neural network |
| Text Recognition | CRNN (CNN + LSTM + CTC) |
| Languages Supported | 80+ languages |
| GPU Acceleration | Yes (CUDA) |

### Input
```
Image: numpy.ndarray (BGR format)
       Shape: (height, width, 3)
       Example: 1920x1080 screenshot
```

### Output
```python
List[TextElement]:
  - bounds: (x1, y1, x2, y2)  # Bounding box coordinates
  - text: str                  # Recognized text content
  - confidence: float          # Recognition confidence (0.0-1.0)
```

### Example Output
```json
[
  {"bounds": [100, 50, 200, 80], "text": "Submit", "confidence": 0.95},
  {"bounds": [100, 100, 250, 130], "text": "Username", "confidence": 0.92},
  {"bounds": [300, 100, 500, 130], "text": "Enter your name", "confidence": 0.88}
]
```

### Configuration
```python
TextDetector(
    ocr_engine="easyocr",      # OCR backend
    languages=["en"],          # Detection languages
    confidence_threshold=0.3,  # Minimum confidence
    gpu=True                   # Use GPU acceleration
)
```

---

## Stage 2: Non-text Element Detection (UIED)

### Purpose
Detect non-text UI elements: buttons, input fields, icons, checkboxes, containers.

### Model/Technique
**UIED (UI Element Detection)** - Classical Computer Vision algorithms

| Step | Technique | Purpose |
|------|-----------|---------|
| 2.1 | Edge Detection (Canny) | Find element boundaries |
| 2.2 | Contour Detection | Extract closed shapes |
| 2.3 | Morphological Operations | Clean up noise |
| 2.4 | Block Segmentation | Find container regions |
| 2.5 | Element Classification | Classify by shape/size |

### Algorithm Flow
```
Image
  │
  ├─→ Grayscale Conversion
  │
  ├─→ Adaptive Thresholding
  │
  ├─→ Edge Detection (Canny)
  │       Parameters: low=50, high=150
  │
  ├─→ Morphological Closing
  │       Kernel: 3x3, iterations=2
  │
  ├─→ Contour Detection
  │       Mode: RETR_TREE
  │       Method: CHAIN_APPROX_SIMPLE
  │
  ├─→ Bounding Box Extraction
  │
  ├─→ Element Classification
  │       Rules based on:
  │       - Aspect ratio
  │       - Area
  │       - Position
  │       - Color analysis
  │
  └─→ Non-Maximum Suppression (NMS)
          IoU threshold: 0.5
```

### Input
```
Image: numpy.ndarray (BGR format)
       Shape: (height, width, 3)
```

### Output
```python
List[DetectedElement]:
  - bounds: (x1, y1, x2, y2)    # Bounding box
  - element_type: ElementType   # button, input_field, icon, etc.
  - confidence: float           # Detection confidence
  - parent_id: Optional[str]    # Parent element (if nested)
```

### Element Types
| Type | Classification Criteria |
|------|------------------------|
| `button` | Rectangular, small-medium size, may have text |
| `input_field` | Wide rectangle, height < 50px, aspect ratio > 3 |
| `icon` | Square-ish, small (< 64x64), no text |
| `checkbox` | Small square (< 30x30) |
| `container` | Large area, contains other elements |
| `block` | Medium-large rectangle, grouping element |

### Example Output
```json
[
  {"bounds": [100, 200, 250, 240], "element_type": "button", "confidence": 0.85},
  {"bounds": [100, 150, 400, 180], "element_type": "input_field", "confidence": 0.90},
  {"bounds": [50, 50, 82, 82], "element_type": "icon", "confidence": 0.75}
]
```

### Configuration
```python
UIEDDetector(
    min_element_area=100,      # Minimum area in pixels
    nms_threshold=0.5,         # IoU threshold for NMS
    min_block_area=500,        # Minimum block/container area
    merge_distance=5           # Distance to merge nearby elements
)
```

---

## Stage 2.5: Merge & Deduplication

### Purpose
Combine text and non-text detections, remove duplicates, associate text with elements.

### Technique
Rule-based merging with IoU (Intersection over Union) calculations

### Operations
1. **Text-Element Association**: Attach OCR text to overlapping UI elements
2. **Cross-type NMS**: Remove highly overlapping detections
3. **Containment Filtering**: Handle nested elements
4. **Re-scanning**: Fine-grained detection for merged regions

### Algorithm
```python
for each UIED_element:
    overlapping_texts = find_texts_with_IoU > 0.3
    if overlapping_texts:
        element.text = combine(overlapping_texts)
        mark texts as used

apply_NMS(all_elements, iou_threshold=0.5)
filter_by_size(min_area=100, min_dimension=10)
```

### Input
```
- text_elements: List[TextElement]      # From Stage 1
- uied_elements: List[DetectedElement]  # From Stage 2
```

### Output
```python
List[UIElement]:
  - id: str                    # Unique identifier (E1, E2, ...)
  - bounds: (x1, y1, x2, y2)   # Bounding box
  - visual_type: str           # Element type
  - confidence: float          # Combined confidence
  - ocr_text: Optional[str]    # Associated text
  - source: str                # "text", "uied", or "merged"
```

---

## Stage 3: Hierarchy Building (Rule-based)

### Purpose
Build parent-child relationships to create a DOM tree structure.

### Technique
**Rule-based Heuristics** using spatial relationships

| Rule | Description |
|------|-------------|
| Containment | Element A contains B if B's bounds are 85%+ inside A |
| Smallest Parent | Each element's parent is the smallest valid container |
| Alignment Groups | Elements with same Y-center form rows |
| Label Association | Text near input fields becomes labels |

### Algorithm
```
1. CONTAINMENT HIERARCHY
   Sort elements by area (largest first)
   For each element:
       Find smallest container that contains it
       Set as parent
       Add to parent's children list

2. LABEL ASSOCIATION
   For each input_field/checkbox:
       Find nearest text element (within 50px)
       If above or left: associate as label

3. GROUP DETECTION
   Find horizontal rows (same Y ± 15px)
   Find vertical columns (same X ± 15px)

4. ROOT CREATION
   If multiple top-level nodes:
       Create synthetic ROOT node
       Set all orphans as ROOT's children
```

### Input
```python
List[UIElement]:
  - id, bounds, visual_type, confidence, ocr_text
```

### Output
```python
{
  "root": TreeNode,              # Root of hierarchy tree
  "nodes": List[TreeNode],       # Flat list of all nodes
  "label_associations": Dict,    # element_id → label_id
  "groups": List[Group]          # Detected rows/columns
}

TreeNode:
  - id: str
  - bounds: (x1, y1, x2, y2)
  - visual_type: str
  - role: str                    # Accessibility role
  - text: Optional[str]
  - children: List[TreeNode]
  - parent_id: Optional[str]
```

### Example Hierarchy
```
ROOT
├── E1 (container)
│   ├── E2 (text: "Username")
│   ├── E3 (input_field, label=E2)
│   ├── E4 (text: "Password")
│   └── E5 (input_field, label=E4)
├── E6 (button: "Login")
└── E7 (text: "Forgot password?")
```

### Configuration
```python
CoarseHierarchyBuilder(
    containment_threshold=0.85,  # % of child inside parent
    alignment_tolerance=15,      # Pixels for alignment grouping
    label_max_distance=50,       # Max distance for label association
    min_containment_margin=5     # Min margin for containment
)
```

---

## Stage 3.5: LLM Hierarchy Refinement (Optional)

### Purpose
Use a language model to refine and fix common detection errors.

### Model/Technique
**Small Language Models (SLMs)** for structured output generation

| Model | Size | Type | Speed |
|-------|------|------|-------|
| Qwen2.5-3B-Instruct | 3B params | Local (HuggingFace) | ~2-3 sec |
| Phi-3.5-mini | 3.8B params | Local (HuggingFace) | ~2-3 sec |
| Gemma-2-2B-it | 2B params | Local (HuggingFace) | ~1-2 sec |
| Ollama (qwen2.5:3b) | 3B params | Local Server | ~1-2 sec |
| GPT-4o-mini | Cloud | OpenAI API | ~1-2 sec |

### Operations
| Operation | Purpose | Example |
|-----------|---------|---------|
| **MERGE** | Combine split text | "Sub" + "mit" → "Submit" |
| **SPLIT** | Separate merged elements | "1 2 3 4" → 4 buttons |
| **RETYPE** | Fix element type | text → button |
| **DELETE** | Remove noise | Remove artifacts |
| **SET_ROLE** | Add semantic role | "submit_button" |

### Prompt Template
```
## DETECTED ELEMENTS:
E1: button "Submit" [center, medium]
E2: text "Username" [left-top, small]
...

## YOUR TASK:
Output JSON array of edits:
- {"op": "merge", "ids": ["E1", "E2"], "text": "combined"}
- {"op": "retype", "id": "E5", "type": "button"}
- {"op": "delete", "id": "E10"}

## OUTPUT:
[{"op": "retype", "id": "E5", "type": "button"}]
```

### Input
```python
{
  "elements": List[UIElement],   # From Stage 2.5
  "hierarchy": TreeNode,         # From Stage 3
  "image_size": (width, height)
}
```

### Output
```python
{
  "edits": List[TreeEdit],           # Applied operations
  "refined_elements": List[UIElement], # Elements after edits
  "llm_response": str                # Raw LLM output
}
```

### Configuration
```python
LLMHierarchyRefiner(
    model_name="ollama",        # Model backend
    use_gpu=True,               # GPU acceleration
    max_tokens=2048,            # Max response length
    temperature=0.1,            # Low = deterministic
    ollama_host="http://localhost:11434"
)
```

### Current Status
| Feature | Status |
|---------|--------|
| Implementation | ✅ Complete |
| Viewer Integration | ❌ Not integrated |
| CLI Support | ✅ Available |

---

## Stage 4: DOM Compilation

### Purpose
Generate final JSON output with locators for UI automation.

### Technique
**Deterministic Processing** - No ML models

### Operations
1. Generate unique element IDs
2. Calculate center points for clicking
3. Map visual types to accessibility roles
4. Set interaction flags (clickable, editable, scrollable)
5. Generate multiple locator strategies

### Role Mapping
| Visual Type | Accessibility Role |
|-------------|-------------------|
| button | Button |
| input_field | EditText |
| checkbox | CheckBox |
| text | TextView |
| icon | ImageView |
| container | ViewGroup |

### Locator Strategies
| Locator Type | Format | Example |
|--------------|--------|---------|
| id | Element ID | `"E42"` |
| text | Text content | `"Submit"` or `"Submit[0]"` |
| type_index | Type + index | `"button[3]"` |
| bounds | Bounding box | `"bounds(100,200,250,240)"` |
| center | Click point | `"point(175,220)"` |

### Input
```python
{
  "elements": List[UIElement],
  "hierarchy": TreeNode,
  "image_size": (width, height)
}
```

### Output
```json
{
  "image_path": "screenshot.png",
  "image_size": {"width": 1920, "height": 1080},
  "cv_stats": {
    "text_detected": 45,
    "uied_detected": 120,
    "final_count": 89
  },
  "dom": {
    "version": "1.0",
    "element_count": 89,
    "hierarchy": {
      "id": "ROOT",
      "bounds": [0, 0, 1920, 1080],
      "center": [960, 540],
      "role": "root",
      "visual_type": "container",
      "clickable": false,
      "editable": false,
      "scrollable": false,
      "children": [
        {
          "id": "E1",
          "bounds": [100, 200, 250, 240],
          "center": [175, 220],
          "role": "Button",
          "visual_type": "button",
          "text": "Submit",
          "clickable": true,
          "editable": false,
          "scrollable": false,
          "confidence": 0.85,
          "locators": {
            "id": "E1",
            "text": "Submit",
            "type_index": "button[0]",
            "bounds": "bounds(100,200,250,240)",
            "center": "point(175,220)"
          },
          "children": []
        }
      ]
    }
  }
}
```

### Configuration
```python
DOMCompiler(
    generate_locators=True,    # Generate locator strategies
    include_confidence=True,   # Include confidence scores
    min_confidence=0.3         # Filter low-confidence elements
)
```

---

## Complete Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VISUAL DOM PIPELINE                                │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │ Screenshot  │
                              │   (PNG)     │
                              └──────┬──────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: TEXT DETECTION                                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Model: EasyOCR (CRAFT + CRNN)                                           │ │
│ │ Input: BGR Image (H×W×3)                                                │ │
│ │ Output: List[{bounds, text, confidence}]                                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: NON-TEXT DETECTION                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Technique: UIED (Edge Detection + Contours + Classification)            │ │
│ │ Input: BGR Image (H×W×3)                                                │ │
│ │ Output: List[{bounds, element_type, confidence}]                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2.5: MERGE & DEDUPLICATE                                               │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Technique: IoU Matching + NMS + Containment Filtering                   │ │
│ │ Input: text_elements + uied_elements                                    │ │
│ │ Output: List[UIElement] (merged, deduplicated)                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: HIERARCHY BUILDING                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Technique: Rule-based (Containment + Alignment + Label Association)     │ │
│ │ Input: List[UIElement]                                                  │ │
│ │ Output: TreeNode (root of hierarchy tree)                               │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                          ▼                     ▼
┌─────────────────────────────────────┐   ┌─────────────────────────────────┐
│ STAGE 3.5: LLM REFINEMENT           │   │       (Skip if no LLM)          │
│ ┌─────────────────────────────────┐ │   │                                 │
│ │ Model: Qwen2.5-3B / Ollama /    │ │   │                                 │
│ │        GPT-4o-mini              │ │   │                                 │
│ │ Operations: merge, split,       │ │   │                                 │
│ │             retype, delete      │ │   │                                 │
│ └─────────────────────────────────┘ │   │                                 │
│ [OPTIONAL - Currently not in viewer]│   │                                 │
└─────────────────────────────────────┘   └─────────────────────────────────┘
                          │                     │
                          └──────────┬──────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: DOM COMPILATION                                                     │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Technique: Deterministic Processing                                     │ │
│ │ Input: elements + hierarchy + image_size                                │ │
│ │ Output: DOM JSON with locators                                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │  DOM JSON   │
                              │  (Output)   │
                              └─────────────┘
```

---

## Summary Table

| Stage | Name | Technique/Model | Input | Output |
|-------|------|-----------------|-------|--------|
| 1 | Text Detection | EasyOCR (CRAFT+CRNN) | Image (BGR) | Text elements with bounds |
| 2 | Non-text Detection | UIED (Canny+Contours) | Image (BGR) | UI elements with types |
| 2.5 | Merge & Dedupe | IoU + NMS | Text + UIED elements | Unified element list |
| 3 | Hierarchy Building | Rule-based heuristics | Element list | Tree structure |
| 3.5 | LLM Refinement | SLM (Qwen/Ollama) | Elements + Tree | Refined elements |
| 4 | DOM Compilation | Deterministic | Elements + Tree | Final JSON with locators |

---

## Performance Characteristics

| Stage | GPU Benefit | Typical Time | Memory |
|-------|-------------|--------------|--------|
| Text Detection | High (10x faster) | 0.5-2s | 1-2 GB VRAM |
| Non-text Detection | None (CPU only) | 0.3-1s | 200 MB RAM |
| Merge & Dedupe | None | <0.1s | Minimal |
| Hierarchy Building | None | <0.1s | Minimal |
| LLM Refinement | High | 1-5s | 4-8 GB VRAM |
| DOM Compilation | None | <0.1s | Minimal |
| **Total (no LLM)** | - | **1-3 seconds** | - |
| **Total (with LLM)** | - | **2-8 seconds** | - |

---

## Source Code References

| Component | Location |
|-----------|----------|
| CV Pipeline | `src/visual_dom/cv/pipeline.py` |
| Text Detector | `src/visual_dom/cv/text_detector.py` |
| UIED Detector | `src/visual_dom/cv/uied_detection.py` |
| Hierarchy Builder | `src/visual_dom/hierarchy/coarse_builder.py` |
| LLM Refiner | `src/visual_dom/hierarchy/llm_refiner.py` |
| DOM Compiler | `src/visual_dom/compiler/dom_compiler.py` |

---

## Usage Example

```python
from visual_dom.cv.pipeline import VisualDOMPipeline
from visual_dom.hierarchy.coarse_builder import CoarseHierarchyBuilder
from visual_dom.compiler.dom_compiler import DOMCompiler

# Initialize pipeline
pipeline = VisualDOMPipeline(
    ocr_engine="easyocr",
    use_gpu=True
)

# Stage 1-2.5: CV Detection
result = pipeline.process("screenshot.png")
elements = result["elements"]
print(f"Detected {len(elements)} elements")

# Stage 3: Hierarchy Building
builder = CoarseHierarchyBuilder()
hierarchy_result = builder.build(elements)
hierarchy = hierarchy_result.get("root")

# Stage 4: DOM Compilation
compiler = DOMCompiler(generate_locators=True)
dom = compiler.compile(
    elements=elements,
    hierarchy=hierarchy,
    image_size=result["image_size"]
)

# Save output
import json
with open("output.json", "w") as f:
    json.dump(dom, f, indent=2)
```

---

## Command Line Usage

```bash
# Run full pipeline
python -m visual_dom.cv.pipeline screenshot.png -o output.json --visualize viz.png

# Run with specific options
python -m visual_dom.cv.pipeline screenshot.png \
    --ocr easyocr \
    --no-gpu \
    -o output.json
```
