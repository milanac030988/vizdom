# Research: Vision-Language Models for GUI Element Detection

## Overview

This document describes the research experiments evaluating Vision-Language Models (VLMs) for GUI element detection. The goal is to assess whether VLMs can be used as an alternative or complement to the traditional CV pipeline (EasyOCR + UIED).

**Research Question**: Can Vision-Language Models accurately detect and localize UI elements in screenshots?

---

## Models Under Evaluation

### Tested VLM Models

| Model | Provider | Size | VRAM | Grounding | Strengths |
|-------|----------|------|------|-----------|-----------|
| **Qwen2-VL-2B** | Alibaba | 2B | ~5GB | Yes | Balanced size/performance |
| **Qwen2-VL-7B** | Alibaba | 7B | ~15GB | Yes | Higher accuracy |
| **Florence-2-base** | Microsoft | 0.2B | ~2GB | Excellent | Best for visual grounding |
| **Florence-2-large** | Microsoft | 0.7B | ~4GB | Excellent | Better accuracy than base |
| **Phi-3.5-Vision** | Microsoft | 4B | ~8GB | Limited | Good general understanding |
| **MiniCPM-V-2.6** | OpenBMB | 2.6B | ~8GB | Limited | Efficient multimodal |
| **InternVL2-2B** | Shanghai AI | 2B | ~5GB | Limited | Strong visual understanding |
| **InternVL2-8B** | Shanghai AI | 8B | ~16GB | Limited | High accuracy |

### Model Capabilities

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VLM CAPABILITY COMPARISON                            │
└─────────────────────────────────────────────────────────────────────────┘

                    │ Object    │ OCR with  │ Precise   │ UI Element │
      Model         │ Detection │ Regions   │ Grounding │ Classification │
────────────────────┼───────────┼───────────┼───────────┼────────────────┤
Qwen2-VL-2B/7B      │    ★★★    │    ★★★    │    ★★☆    │      ★★☆       │
Florence-2          │    ★★★    │    ★★★    │    ★★★    │      ★★☆       │
Phi-3.5-Vision      │    ★★☆    │    ★★☆    │    ★☆☆    │      ★★★       │
MiniCPM-V           │    ★★☆    │    ★★☆    │    ★☆☆    │      ★★☆       │
InternVL2           │    ★★★    │    ★★☆    │    ★☆☆    │      ★★★       │

★★★ = Excellent   ★★☆ = Good   ★☆☆ = Limited
```

---

## Evaluation Methodology

### Test Protocol

1. **Input**: GUI screenshot (PNG/JPG)
2. **Task**: Detect all UI elements with bounding boxes
3. **Output**: JSON array of detected elements

### Evaluation Metrics

#### 1. Detection Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| **Precision** | TP / (TP + FP) | Of predictions, how many are correct |
| **Recall** | TP / (TP + FN) | Of ground truth, how many found |
| **F1 Score** | 2 × P × R / (P + R) | Harmonic mean of P and R |
| **mAP@50** | Mean AP at IoU=0.5 | Standard object detection metric |
| **mAP@75** | Mean AP at IoU=0.75 | Stricter overlap requirement |

#### 2. Localization Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| **Mean IoU** | Σ IoU(pred, gt) / N | Average bounding box overlap |
| **Center Error** | Σ dist(pred_center, gt_center) / N | Average center point distance |
| **Size Error** | Σ |pred_area - gt_area| / gt_area / N | Relative area error |

#### 3. Classification Metrics

| Metric | Description |
|--------|-------------|
| **Type Accuracy** | Correct element type classification |
| **Text Accuracy** | OCR text recognition accuracy (CER/WER) |

#### 4. Efficiency Metrics

| Metric | Description |
|--------|-------------|
| **Inference Time** | Seconds per image |
| **VRAM Usage** | GPU memory required |
| **Throughput** | Images per second |

### IoU (Intersection over Union) Calculation

```
        ┌─────────────────┐
        │   Ground Truth  │
        │   ┌─────────┐   │
        │   │ Overlap │   │
        └───┴─────────┴───┘
            └─────────┘
            Prediction

IoU = Area of Overlap / Area of Union

Matching Threshold:
- IoU ≥ 0.5 → True Positive (standard)
- IoU ≥ 0.75 → True Positive (strict)
```

---

## Research Scripts

### 1. LLM Refinement Testing (`research/test_llm_refinement.py`)

Tests LLM as a post-processing step to refine CV pipeline results.

```bash
# Test with Ollama (recommended for local testing)
python research/test_llm_refinement.py screenshot.png --backend ollama

# Test with OpenAI API
python research/test_llm_refinement.py screenshot.png --backend openai

# Test with local HuggingFace model
python research/test_llm_refinement.py screenshot.png --backend hf --model qwen2.5-3b

# Generate before/after visualization
python research/test_llm_refinement.py screenshot.png --backend ollama -o results/

# Batch evaluation on multiple images
python research/test_llm_refinement.py test_images/ --backend ollama --batch

# Save results to JSON
python research/test_llm_refinement.py screenshot.png --backend ollama --json results.json
```

**Research Questions**:
1. Can LLMs fix common CV detection errors (split text, merged buttons)?
2. Does LLM refinement improve element classification accuracy?
3. What is the trade-off between accuracy improvement and inference time?
4. Which LLM backend works best for this task?

**Supported Backends**:
| Backend | Model | Local/Cloud | Notes |
|---------|-------|-------------|-------|
| `ollama` | qwen2.5:3b | Local | Recommended for testing |
| `openai` | gpt-4o-mini | Cloud | Best quality, API costs |
| `hf` | Qwen2.5-3B | Local | Needs GPU (4-8GB VRAM) |
| `qwen` | Qwen2.5-3B | Local | Same as hf |
| `phi` | Phi-3.5-mini | Local | Alternative local model |

**Output Metrics**:
```json
{
  "cv_pipeline": {
    "element_count": 45,
    "time_sec": 2.1
  },
  "llm_refinement": {
    "element_count": 42,
    "time_sec": 1.8,
    "backend": "ollama"
  },
  "edits": {
    "total": 5,
    "merge": 2,
    "split": 0,
    "retype": 1,
    "delete": 2,
    "role": 0
  }
}
```

---

### 2. Qwen2-VL Testing (`research/test_qwen_vl.py`)

Tests Qwen2-VL models with different detection modes.

```bash
# Simple description mode
python research/test_qwen_vl.py screenshot.png --model 2b --mode simple

# JSON detection mode
python research/test_qwen_vl.py screenshot.png --model 2b --mode json -o viz.png

# Grounding mode (precise bboxes)
python research/test_qwen_vl.py screenshot.png --model 7b --mode grounding -o viz.png

# CPU inference
python research/test_qwen_vl.py screenshot.png --model 2b --no-gpu
```

**Detection Modes**:
| Mode | Description | Output |
|------|-------------|--------|
| `simple` | Natural language description | Text description |
| `json` | Structured JSON detection | JSON array with bboxes |
| `grounding` | Special grounding tokens | Precise coordinates |

**Grounding Token Format**:
```
<|object_ref_start|>button: OK<|object_ref_end|><|box_start|>(100,200),(150,230)<|box_end|>
```

### 3. Multi-Model VLM Testing (`research/test_vlm_models.py`)

Tests multiple VLM models with unified interface.

```bash
# List available models
python research/test_vlm_models.py --list-models

# Test Florence-2 (recommended for grounding)
python research/test_vlm_models.py screenshot.png --model florence-2-base -o viz.png

# Test Qwen2-VL
python research/test_vlm_models.py screenshot.png --model qwen2-vl-2b -o viz.png

# Test Phi-3.5-Vision
python research/test_vlm_models.py screenshot.png --model phi-3.5-vision -o viz.png

# Test InternVL2
python research/test_vlm_models.py screenshot.png --model internvl2-2b -o viz.png

# CPU inference
python research/test_vlm_models.py screenshot.png --model florence-2-base --no-gpu
```

**Available Models**:
```
qwen2-vl-2b      - Qwen/Qwen2-VL-2B-Instruct      (VRAM: ~5GB)
qwen2-vl-7b      - Qwen/Qwen2-VL-7B-Instruct      (VRAM: ~15GB)
florence-2-base  - microsoft/Florence-2-base      (VRAM: ~2GB)
florence-2-large - microsoft/Florence-2-large     (VRAM: ~4GB)
phi-3.5-vision   - microsoft/Phi-3.5-vision       (VRAM: ~8GB)
minicpm-v-2.6    - openbmb/MiniCPM-V-2_6          (VRAM: ~8GB)
internvl2-2b     - OpenGVLab/InternVL2-2B         (VRAM: ~5GB)
internvl2-8b     - OpenGVLab/InternVL2-8B         (VRAM: ~16GB)
```

---

## Florence-2 Tasks

Florence-2 supports multiple specialized tasks for GUI analysis:

| Task | Description | Use Case |
|------|-------------|----------|
| `<OD>` | Object Detection | Find all objects with labels |
| `<REGION_PROPOSAL>` | Region Proposals | Find clickable/interactive regions |
| `<OCR_WITH_REGION>` | OCR with Regions | Extract text with bounding boxes |
| `<DENSE_REGION_CAPTION>` | Dense Captioning | Caption each region |
| `<CAPTION_TO_PHRASE_GROUNDING>` | Phrase Grounding | Find specific UI elements |

**Example Output (Florence-2)**:
```json
{
  "object_detection": {
    "bboxes": [[100, 50, 200, 90], [300, 100, 450, 140]],
    "labels": ["button", "text field"]
  },
  "region_proposals": {
    "bboxes": [[50, 50, 250, 300], [300, 50, 500, 300]],
    "labels": ["region_0", "region_1"]
  },
  "ocr": {
    "quad_boxes": [[100, 60, 190, 60, 190, 85, 100, 85]],
    "labels": ["Submit"]
  }
}
```

---

## Evaluation Procedure

### Step 1: Prepare Test Dataset

Create a test dataset with ground truth annotations:

```
test_data/
├── images/
│   ├── calculator.png
│   ├── notepad.png
│   └── browser.png
└── annotations/
    ├── calculator.json
    ├── notepad.json
    └── browser.json
```

**Ground Truth Format**:
```json
{
  "image": "calculator.png",
  "image_size": [800, 600],
  "elements": [
    {
      "id": "E1",
      "type": "button",
      "bbox": [100, 200, 150, 240],
      "text": "7"
    },
    {
      "id": "E2",
      "type": "button",
      "bbox": [160, 200, 210, 240],
      "text": "8"
    }
  ]
}
```

### Step 2: Run Model Inference

```bash
# Run VLM detection
python research/test_vlm_models.py test_data/images/calculator.png \
    --model florence-2-base \
    -o results/florence2_calculator.png \
    > results/florence2_calculator.json
```

### Step 3: Compute Evaluation Metrics

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationConfig

config = EvaluationConfig(iou_threshold=0.5)
evaluator = VisualDOMEvaluator(config)

# Compare VLM output to ground truth
result = evaluator.evaluate_from_files(
    predicted="results/florence2_calculator.json",
    ground_truth="test_data/annotations/calculator.json"
)

print(f"Precision: {result.element_metrics.precision:.2%}")
print(f"Recall: {result.element_metrics.recall:.2%}")
print(f"F1 Score: {result.element_metrics.f1_score:.2%}")
print(f"Mean IoU: {result.element_metrics.mean_iou:.2%}")
```

### Step 4: Compare Models

```bash
# Run all models on same test image
for model in florence-2-base qwen2-vl-2b phi-3.5-vision; do
    echo "Testing $model..."
    python research/test_vlm_models.py test_image.png \
        --model $model \
        -o "results/${model}_output.png" \
        > "results/${model}_output.json"
done
```

---

## Expected Results Format

### Model Output Schema

```json
{
  "model": "florence-2-base",
  "image": "screenshot.png",
  "image_size": [1920, 1080],
  "inference_time_sec": 1.5,
  "elements": [
    {
      "type": "button",
      "bbox": [100, 200, 250, 240],
      "text": "Submit",
      "confidence": 0.95
    },
    {
      "type": "input",
      "bbox": [100, 100, 400, 140],
      "text": "",
      "confidence": 0.88
    }
  ]
}
```

### Evaluation Report Schema

```json
{
  "model": "florence-2-base",
  "test_images": 10,
  "metrics": {
    "detection": {
      "precision": 0.85,
      "recall": 0.78,
      "f1_score": 0.81,
      "mAP_50": 0.75,
      "mAP_75": 0.62
    },
    "localization": {
      "mean_iou": 0.72,
      "center_error_px": 8.5,
      "size_error_pct": 0.15
    },
    "classification": {
      "type_accuracy": 0.82,
      "text_cer": 0.05,
      "text_wer": 0.12
    },
    "efficiency": {
      "inference_time_sec": 1.5,
      "vram_gb": 2.1,
      "throughput_fps": 0.67
    }
  }
}
```

---

## Comparison: VLM vs CV Pipeline

| Aspect | CV Pipeline (EasyOCR+UIED) | VLM (Florence-2) |
|--------|---------------------------|------------------|
| **Inference Speed** | 1-3 sec | 1-5 sec |
| **VRAM Usage** | 1-2 GB | 2-15 GB |
| **Text Detection** | Excellent (dedicated OCR) | Good |
| **Element Detection** | Good (rule-based) | Good (learned) |
| **Grounding Accuracy** | High (pixel-level) | Medium-High |
| **Semantic Understanding** | None | Good |
| **Model Size** | ~100MB | 200MB-15GB |
| **Offline Support** | Full | Full |

### When to Use Each

**Use CV Pipeline when**:
- High precision localization required
- Limited GPU memory
- Need fast inference
- Text detection is primary goal

**Use VLM when**:
- Semantic understanding needed
- Complex UI layouts
- Element classification important
- Can accept ~5-10px bbox error

**Hybrid Approach** (Recommended):
```
VLM (element detection) → CV Pipeline (precise localization) → LLM (refinement)
```

---

## Running Experiments

### Hardware Requirements

| Model | Min VRAM | Recommended VRAM | CPU Inference |
|-------|----------|------------------|---------------|
| Florence-2-base | 2GB | 4GB | Yes (slow) |
| Florence-2-large | 4GB | 8GB | Yes (slow) |
| Qwen2-VL-2B | 5GB | 8GB | Possible |
| Qwen2-VL-7B | 15GB | 24GB | Not recommended |
| Phi-3.5-Vision | 8GB | 12GB | Possible |

### Installation

```bash
# Base dependencies
pip install torch torchvision transformers

# For Qwen2-VL
pip install qwen-vl-utils

# For Florence-2
pip install timm einops

# For visualization
pip install opencv-python pillow
```

### Quick Start

```bash
# 1. Test with smallest model first
python research/test_vlm_models.py screenshot.png --model florence-2-base

# 2. If GPU memory available, try larger models
python research/test_vlm_models.py screenshot.png --model qwen2-vl-2b

# 3. Generate visualization
python research/test_vlm_models.py screenshot.png \
    --model florence-2-base \
    -o visualization.png
```

---

## Research Findings (Summary)

### Critical Finding #1: VLM Hallucination Problem

**VLMs generate fake/non-existent UI elements (hallucination).**

During research testing, we observed that Vision-Language Models frequently hallucinate - they generate bounding boxes and element descriptions for UI elements that **do not exist** in the screenshot.

#### Types of Hallucination Observed

| Hallucination Type | Description | Example |
|--------------------|-------------|---------|
| **Ghost Elements** | Elements that don't exist at all | Reports "Settings" button when there is none |
| **Wrong Position** | Element exists but bbox is completely wrong | Button at [100,100] reported at [500,300] |
| **Invented Text** | OCR text that doesn't appear in image | Reports "Submit" when button says "OK" |
| **Duplicate Detection** | Same element reported multiple times | 3 entries for single button |
| **Type Confusion** | Misclassifies element type | Text label reported as button |

#### Hallucination Examples

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    HALLUCINATION EXAMPLES                                │
└─────────────────────────────────────────────────────────────────────────┘

Actual Screenshot:              VLM Output (Hallucinated):
┌─────────────────────┐         [
│  ┌─────┐  ┌─────┐   │           {"type": "button", "text": "OK"},      ✓ Real
│  │ OK  │  │Cancel│  │           {"type": "button", "text": "Cancel"},  ✓ Real
│  └─────┘  └─────┘   │           {"type": "button", "text": "Help"},    ✗ FAKE
│                     │           {"type": "button", "text": "Settings"},✗ FAKE
│  Status: Ready      │           {"type": "input", "text": "Search"},   ✗ FAKE
└─────────────────────┘         ]

Problem: VLM invented 3 elements that don't exist!
```

#### Hallucination Rate by Model

| Model | Hallucination Rate | Notes |
|-------|-------------------|-------|
| Florence-2-base | Low (~5-10%) | Most reliable |
| Florence-2-large | Low (~5-10%) | Most reliable |
| Qwen2-VL-2B | Medium (~15-25%) | More hallucination with complex prompts |
| Qwen2-VL-7B | Medium (~10-20%) | Better than 2B but still hallucinates |
| Phi-3.5-Vision | High (~20-30%) | Tends to invent elements |
| MiniCPM-V | Medium (~15-25%) | Variable quality |
| InternVL2 | Medium (~15-20%) | Depends on prompt |

#### Impact on Evaluation

```python
# Without hallucination filtering:
Precision: 0.45  # Low because many false positives (hallucinated)
Recall: 0.80     # High because real elements are found
F1: 0.58

# With hallucination filtering (post-processing):
Precision: 0.75  # Improved after removing invalid bboxes
Recall: 0.78     # Slightly lower (some valid removed)
F1: 0.76
```

#### Hallucination Detection Strategies

```python
def filter_hallucinated_elements(elements, image_size):
    """Filter out likely hallucinated elements."""
    valid = []
    w, h = image_size

    for elem in elements:
        bbox = elem.get("bbox", [])
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox

        # 1. Check bounds within image
        if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            continue  # Outside image = hallucinated

        # 2. Check valid dimensions
        if x2 <= x1 or y2 <= y1:
            continue  # Invalid bbox = hallucinated

        # 3. Check reasonable size
        area = (x2 - x1) * (y2 - y1)
        if area < 25 or area > w * h * 0.9:
            continue  # Too small or too large

        # 4. Check aspect ratio
        aspect = max(x2-x1, y2-y1) / max(min(x2-x1, y2-y1), 1)
        if aspect > 50:
            continue  # Extreme aspect ratio = likely noise

        valid.append(elem)

    return valid
```

#### Why VLMs Hallucinate

1. **Training Data Bias**: Models trained on diverse images expect common UI patterns
2. **Pattern Completion**: VLMs try to "complete" UIs with expected elements
3. **Prompt Sensitivity**: Asking for "all buttons" encourages over-detection
4. **Confidence Miscalibration**: High confidence on non-existent elements
5. **Context Confusion**: Similar-looking areas trigger false detections

#### Mitigation Strategies

| Strategy | Implementation | Effectiveness |
|----------|----------------|---------------|
| **Bbox Validation** | Filter bboxes outside image bounds | High |
| **Size Filtering** | Remove too-small or too-large elements | Medium |
| **Confidence Threshold** | Only keep high-confidence detections | Medium |
| **Cross-Validation** | Compare with CV pipeline results | High |
| **Prompt Engineering** | Use conservative prompts | Medium |
| **Post-Processing NMS** | Remove overlapping duplicates | Medium |

---

### Critical Finding #2: Button Detection Problem

**VLMs cannot reliably detect button boundaries directly.**

The research revealed that Vision-Language Models have significant limitations in detecting UI button elements:

#### Problem Analysis

| Detection Task | VLM Performance | Notes |
|----------------|-----------------|-------|
| Text Detection (OCR) | **Good** | VLMs find text content reliably |
| Text Bounding Box | **Good** | Precise text region localization |
| Button Boundary Detection | **Poor** | Cannot detect button edges |
| Button Classification | **Poor** | Often misses buttons entirely |

#### Evidence from Code

The `test_vlm_models.py` contains a **workaround** (lines 570-586) that demonstrates this limitation:

```python
# Create expanded button estimate from text bbox
# Expand by ~50% of text height to approximate button area
text_h = text_bbox[3] - text_bbox[1]
padding_x = max(text_h // 2, 5)  # Use text height as guide
padding_y = max(text_h // 2, 3)
button_bbox = [
    max(0, text_bbox[0] - padding_x),
    max(0, text_bbox[1] - padding_y),
    text_bbox[2] + padding_x,
    text_bbox[3] + padding_y
]
```

**This workaround**:
1. Detects text using OCR capabilities
2. Expands the text bounding box by ~50% of text height
3. Assumes the expanded area is the button boundary

#### Why VLMs Fail at Button Detection

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BUTTON DETECTION CHALLENGE                           │
└─────────────────────────────────────────────────────────────────────────┘

What VLM sees:          What we need:
┌─────────────────┐     ┌─────────────────┐
│                 │     │ ┌─────────────┐ │
│    "Submit"     │     │ │   Submit    │ │  ← Button boundary
│                 │     │ └─────────────┘ │
└─────────────────┘     └─────────────────┘
   ↑ Text only            ↑ Full button bbox

Problems:
1. Buttons often have same background as surrounding area
2. Button borders may be subtle (1px) or non-existent (flat design)
3. VLMs trained on natural images, not UI screenshots
4. No clear visual boundary for "clickable" regions
```

#### Impact on Accuracy

| Scenario | Text BBox | Estimated Button BBox | Actual Button BBox |
|----------|-----------|----------------------|-------------------|
| Standard button | [100, 50, 160, 70] | [90, 40, 170, 80] | [80, 35, 180, 85] |
| Error | - | ~10-20px off | Ground truth |
| IoU with GT | N/A | ~0.5-0.7 | 1.0 |

**Result**: Button localization accuracy is degraded because we're estimating, not detecting.

#### Workaround Limitations

1. **Fixed expansion ratio** - 50% doesn't work for all button styles
2. **Icon buttons** - Buttons without text are completely missed
3. **Grouped buttons** - Adjacent buttons may overlap after expansion
4. **Variable padding** - Different apps use different button padding

### Preliminary Observations

1. **Florence-2** provides the best grounding accuracy among tested models
2. **Qwen2-VL** offers good balance of detection and understanding
3. **Phi-3.5-Vision** excels at element classification but lacks precise grounding
4. **All VLMs** struggle with small elements (< 20x20 pixels)
5. **CV Pipeline** remains superior for precise text localization
6. **Button detection is a critical weakness** - requires workarounds or CV pipeline

### Comparison: Button Detection Methods

| Method | Approach | Accuracy | Speed | Notes |
|--------|----------|----------|-------|-------|
| **VLM (Florence-2)** | OCR + bbox expansion | Low (~50-70% IoU) | Fast | Workaround, not detection |
| **VLM (Qwen2-VL)** | Grounding tokens | Medium (~60-75% IoU) | Medium | Better but still imprecise |
| **CV Pipeline (UIED)** | Edge + contour detection | High (~80-90% IoU) | Fast | Detects actual boundaries |
| **Combined** | CV detect + VLM classify | High | Medium | Recommended approach |

### Recommendations

1. **For production**: Use CV Pipeline (EasyOCR + UIED) for reliability
2. **For research**: Explore Florence-2 for visual grounding tasks
3. **Hybrid approach**: Use VLM for semantic understanding, CV for precise coords
4. **Future work**: Fine-tune VLMs on UI-specific datasets
5. **Button detection**: Rely on UIED (CV) rather than VLMs for button boundaries

### Open Issues

| Issue | Status | Priority |
|-------|--------|----------|
| **VLM Hallucination** | Documented, needs filtering | High |
| Button boundary detection in VLMs | Unresolved | High |
| Text segmentation improvements | Pending | Medium |
| Small element detection (< 20px) | Unresolved | Medium |
| Icon button detection (no text) | Unresolved | High |

### Research Area #3: LLM Post-Processing Refinement

**Hypothesis**: Small Language Models (SLMs) can improve CV pipeline output quality by fixing common detection errors.

#### Research Objective

Test whether LLM refinement as a post-processing step can:
1. Fix over-segmented text (split words → merged text)
2. Correct element type misclassification
3. Remove duplicate/noise detections
4. Add semantic roles to elements

#### Expected Benefits

| Improvement | Description | Example |
|-------------|-------------|---------|
| **Text Merging** | Combine split OCR text | "Sub" + "mit" → "Submit" |
| **Type Correction** | Fix misclassified elements | text → button |
| **Noise Removal** | Delete artifacts/duplicates | Remove false positives |
| **Role Assignment** | Add semantic meaning | "submit_button", "cancel_button" |

#### Trade-offs

| Aspect | Without LLM | With LLM |
|--------|-------------|----------|
| **Inference Time** | 1-3 sec | 2-6 sec (+1-3 sec) |
| **Accuracy** | Baseline | +5-15% improvement (expected) |
| **Cost** | Free | API costs (cloud) or GPU (local) |
| **Reliability** | Deterministic | Non-deterministic |

#### Test Protocol

```
1. Run CV Pipeline on test image
   └── Get baseline element list

2. Run LLM Refinement
   └── Get refined element list + edits

3. Compare Results
   ├── Element count change
   ├── Edit types (merge/split/retype/delete)
   ├── Processing time overhead
   └── (If ground truth available) Accuracy improvement
```

#### Running the Test

```bash
# Basic test with Ollama
python research/test_llm_refinement.py screenshot.png --backend ollama

# With visualization
python research/test_llm_refinement.py screenshot.png -b ollama -o results/

# Batch evaluation
python research/test_llm_refinement.py test_images/ --batch --json report.json
```

---

### Summary: VLM Limitations for UI Detection

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VLM LIMITATIONS SUMMARY                               │
└─────────────────────────────────────────────────────────────────────────┘

Critical Issue #1: HALLUCINATION
├── VLMs invent non-existent UI elements
├── Hallucination rate: 5-30% depending on model
├── Impact: Low precision, many false positives
└── Mitigation: Post-processing filters required

Critical Issue #2: BUTTON DETECTION
├── VLMs cannot detect button boundaries
├── Only detect text inside buttons
├── Impact: ~50-70% IoU (vs 80-90% for CV)
└── Mitigation: Use CV pipeline (UIED) instead

Recommendation:
┌─────────────────────────────────────────────────────────────────────────┐
│  USE CV PIPELINE (EasyOCR + UIED) FOR PRODUCTION                        │
│  VLMs are NOT reliable enough for UI automation                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
research/
├── test_llm_refinement.py  # LLM post-processing refinement tests
├── test_qwen_vl.py         # Qwen2-VL specific tests
├── test_vlm_models.py      # Multi-model VLM testing framework
└── README.md               # This documentation (symlink)

docs/
├── RESEARCH.md           # This file
├── PIPELINE.md           # CV Pipeline documentation
└── EVALUATION.md         # Evaluation framework documentation
```

---

## References

- [Qwen2-VL Paper](https://arxiv.org/abs/2409.12191)
- [Florence-2 Paper](https://arxiv.org/abs/2311.06242)
- [Phi-3 Technical Report](https://arxiv.org/abs/2404.14219)
- [InternVL2 Paper](https://arxiv.org/abs/2404.16821)
- [UIED Paper](https://arxiv.org/abs/2103.04829)
