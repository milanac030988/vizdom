# Visual DOM Evaluation Framework

This document describes the evaluation metrics and methodology used to assess the quality of Visual DOM detection, OCR accuracy, hierarchy structure, and locator generation.

## Table of Contents

- [Overview](#overview)
- [Benchmark Results](#benchmark-results)
- [Improvement: OmniParser Type Mapping](#improvement-omniparser-type-mapping-before--first-fix--now)
- [Dataset construction & augmentation](#dataset-construction--augmentation)
- [Quick Start](#quick-start)
- [Element Detection Metrics](#element-detection-metrics)
- [OCR Accuracy Metrics](#ocr-accuracy-metrics)
- [Hierarchy Structure Metrics](#hierarchy-structure-metrics)
- [Locator Quality Metrics](#locator-quality-metrics)
- [Interpreting Results](#interpreting-results)
- [Creating Ground Truth](#creating-ground-truth)
- [API Reference](#api-reference)

## Overview

The Visual DOM Evaluation Framework provides comprehensive metrics for evaluating:

1. **Element Detection** - How well the system detects UI elements (buttons, text, inputs, etc.)
2. **OCR Accuracy** - How accurately text content is recognized
3. **Hierarchy Structure** - How well the parent-child relationships are captured
4. **Locator Quality** - How useful the generated locators are for automation

## Benchmark Results

Results below are computed by this framework on the **synthetic benchmark**
(`data/synthetic`): programmatically generated UI screenshots at 1920x1080 with
exact ground truth (element bounds, `visual_type`, text, containment), split into
167 train / **44 test** images. Matching is greedy by IoU at threshold 0.5, pooled
over all elements. YOLO is not evaluated (no trained weights for these UI classes);
the SLM-refinement variant needs a running Ollama service and is not benchmarked here.

### Overall (44-image test set)

| Detector | Precision | Recall | F1 | mIoU | Char. acc. |
|---|---|---|---|---|---|
| UIED (CPU) | 0.39 | **0.71** | 0.51 | 0.68 | 0.92 |
| OmniParser | **0.56** | 0.59 | **0.58** | **0.67** | **0.95** |

### Recall by element type (two lenses)

Aggregate scores are dominated by *text* (63% of ground-truth elements), so the
per-type breakdown is far more informative for a testing use case. Two lenses:
**IoU>=0.5** (strict overlap) and **center-hit** (does a predicted box contain the
element's centre, i.e. is it click-targetable?).

| GT type (n) | UIED IoU>=0.5 | UIED center-hit | OmniParser IoU>=0.5 | OmniParser center-hit |
|---|---|---|---|---|
| button (183) | 0.82 | 0.96 | **1.00** | **1.00** |
| input_field (135) | 0.95 | 0.99 | **0.99** | 0.99 |
| checkbox (76) | **0.68** | 0.82 | 0.20 | **0.87** |
| icon (36) | 0.08 | 0.28 | **0.67** | **1.00** |
| text (1074) | **0.79** | **0.99** | 0.59 | 0.98 |
| **actionable (pooled, 430)** | 0.77 | 0.89 | **0.83** | **0.97** |

**Key findings.** OmniParser leads on the actionable controls a test drives ---
buttons (recall 1.00), input fields (0.99), icons (0.67) --- with tight boxes,
confirming manual inspection that its bounding is more accurate. UIED leads on
checkboxes and text recall. By click-targetability both are strong, with OmniParser
essentially perfect on actionable elements (0.97). OmniParser's low checkbox IoU
(0.20) vs. high center-hit (0.87) is a box-convention effect (it boxes the check
glyph, not the padded control), so the element is still clickable. A single
IoU-based F1 can therefore *understate* a detector; we report both lenses and treat
per-type recall as the primary, testing-relevant measure.

## Improvement: OmniParser Type Mapping (before / first fix / now)

**Problem.** OmniParser's raw output only tags each element `text` or `icon`. Our
integration originally passed that straight through, so the DOM carried no
`button` / `input_field` / `checkbox` roles --- element-type classification accuracy
on actionable controls was **0.09** (correct only on icons, obtained trivially by
labelling everything `icon`), and role-based test logic could not use the DOM.

**What we did.** Added `_infer_visual_type` in the OmniParser backend, which recovers
the role from three signals: box **geometry** (wide entry-height -> input field),
**width/aspect** (buttons are ~2x wider than icons), and OmniParser's **caption**
(a "Checkmark"/"Toggle"/"Check" caption -> checkbox). We also made the pipeline
auto-resolve OmniParser's model paths (a missing path had silently degraded a run to
OCR-only).

**Result** --- element-type accuracy on matched actionable controls, across the two
improvement stages: **before** (text/icon only), **first fix** (interactivity +
geometry), and **now** (+ caption disambiguation and re-tuned width/aspect):

| GT type | before | first fix | now |
|---|---|---|---|
| button | 0.00 | 0.91 | 0.89 |
| input_field | 0.00 | 0.99 | 0.99 |
| checkbox | 0.00 | 0.12 | 0.55 |
| icon | 1.00* | 0.00 | **0.89** |
| **actionable** | 0.09 | 0.73 | **0.87** |

\*The original mapping labelled all non-text as `icon`, so icons scored correct
trivially while every other role scored 0. The **first fix** (geometry only) lifted
actionable accuracy to 0.73 but *regressed* icons to 0.00 --- the geometry rule
reclassified small square glyphs as buttons/checkboxes --- and barely moved
checkboxes (0.12), which are geometrically indistinguishable from icons. Adding the
**caption** signal to disambiguate checkboxes and re-tuning the button/icon width
boundary produced the current mapping (**actionable 0.09 -> 0.73 -> 0.87**). Checkbox
(0.55) remains the weakest (recovered only when the caption is distinctive) and is
future work. This measures *type* only --- localisation (above) is unchanged.

> Caveat: this is a synthetic, clean benchmark; absolute scores will differ on
> gradient-heavy real-world UIs. A larger real-world labelled set is the next step.

## Dataset construction & augmentation

No public benchmark targets VizDOM's setting — custom-rendered and camera-observed
GUIs with a structured ground truth — so the dataset is generated by the project
itself, in three complementary layers (all under `scripts/data_prep/`):

1. **Programmatic synthesis — the labelled benchmark.**
   `generate_synthetic_dataset.py` renders parameterised UI templates (login,
   dashboard, …) across light/dark themes and resolutions, each producing a
   screenshot **plus exact ground truth** (bounds, `visual_type`, text, containment)
   in the pipeline's own schema. Noise-free labels at scale, no manual annotation —
   this is the reproducible **167 train / 44 test** split all scores above use.

2. **LLM-designed layouts — diversity.** `generate_with_claude.py` uses an LLM
   (Claude) as a *UI designer*: prompted for an application class (e.g. a
   car-infotainment screen), it proposes a concrete layout that a renderer turns into
   a screenshot with matching ground truth. This adds structural variety — unusual
   control groupings, domain-specific widgets — that fixed templates can't cover.

3. **Camera-style augmentation — domain robustness.** `augment_camera.py` transforms
   clean screenshots to imitate a screen seen *through a camera*: a perspective warp
   plus glare, blur, and sensor noise, in one or more variants per image. Labels
   carry over — exact for the photometric effects, and valid for the perspective case
   because the pipeline first **rectifies** the detected screen region back to a
   frontal view before detection (`camera_mode`). This set stresses the
   screen-rectification path — VizDOM's no-accessibility-tree differentiator.

**What is scored:** only the clean synthetic split (layer 1) is the scored benchmark.
Layers 2–3 are development / robustness aids that broaden coverage toward real
deployment; a larger real-world labelled set remains future work.

## Quick Start

### Command Line

```bash
# Evaluate single prediction
python -m visual_dom.evaluation.cli predicted.json ground_truth.json

# Batch evaluation
python -m visual_dom.evaluation.cli --batch predictions/ ground_truths/

# Save as Markdown report
python -m visual_dom.evaluation.cli pred.json gt.json -f markdown -o report.md

# Custom IoU threshold
python -m visual_dom.evaluation.cli pred.json gt.json --iou-threshold 0.75
```

### Python API

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationReport

# Create evaluator
evaluator = VisualDOMEvaluator()

# Evaluate
result = evaluator.evaluate_from_files("predicted.json", "ground_truth.json")

# Print summary
print(result.summary())

# Generate detailed report
report = EvaluationReport(result)
report.save_markdown("evaluation_report.md")
report.save_html("evaluation_report.html")
```

## Element Detection Metrics

Element detection evaluates how well the system finds UI elements by comparing predicted bounding boxes against ground truth annotations.

### Precision

**Formula:** `Precision = TP / (TP + FP)`

- **What it measures:** Of all elements the system detected, how many were correct?
- **Range:** 0.0 to 1.0 (higher is better)
- **Use case:** Important when false positives are costly (e.g., clicking wrong elements)

### Recall

**Formula:** `Recall = TP / (TP + FN)`

- **What it measures:** Of all actual elements, how many did the system find?
- **Range:** 0.0 to 1.0 (higher is better)
- **Use case:** Important when missing elements is costly (e.g., incomplete automation)

### F1 Score

**Formula:** `F1 = 2 × (Precision × Recall) / (Precision + Recall)`

- **What it measures:** Harmonic mean of precision and recall
- **Range:** 0.0 to 1.0 (higher is better)
- **Use case:** Overall detection quality when both precision and recall matter equally

### Mean IoU (Intersection over Union)

**Formula:** `IoU = Area(Intersection) / Area(Union)`

- **What it measures:** How well predicted bounding boxes align with ground truth
- **Range:** 0.0 to 1.0 (higher is better)
- **Threshold:** Typically 0.5 (50%) is used to determine a "match"

```
Ground Truth Box     Predicted Box
┌─────────────┐
│             │    ┌─────────────┐
│     ███████████  │             │
│     █ Inter█    │             │
│     █ sect █    │             │
│     ███████████  │             │
│             │    └─────────────┘
└─────────────┘

IoU = Area of Intersection / Area of Union
```

### Per-Class Metrics

The system also computes precision, recall, and F1 for each element type:
- `button`, `text`, `input_field`, `checkbox`, `icon`, etc.

This helps identify which element types are detected well vs. poorly.

## OCR Accuracy Metrics

OCR metrics evaluate how accurately the system recognizes text content.

### Character Error Rate (CER)

**Formula:** `CER = (Insertions + Deletions + Substitutions) / Total_Characters_GT`

- **What it measures:** Percentage of character-level errors
- **Range:** 0.0 to ∞ (lower is better, 0 = perfect)
- **Example:** GT="Hello", Pred="Helo" → CER = 1/5 = 0.2

### Word Error Rate (WER)

**Formula:** `WER = (Insertions + Deletions + Substitutions) / Total_Words_GT`

- **What it measures:** Percentage of word-level errors
- **Range:** 0.0 to ∞ (lower is better)
- **Example:** GT="Hello World", Pred="Hello Word" → WER = 1/2 = 0.5

### Character Accuracy

**Formula:** `Char_Accuracy = max(0, 1 - CER)`

- **What it measures:** Percentage of correct characters
- **Range:** 0.0 to 1.0 (higher is better)

### Word Accuracy

**Formula:** `Word_Accuracy = max(0, 1 - WER)`

- **What it measures:** Percentage of correct words
- **Range:** 0.0 to 1.0 (higher is better)

### Exact Match Rate

**Formula:** `Exact_Match = Count(Pred == GT) / Total_Comparisons`

- **What it measures:** Percentage of texts that match exactly (case-insensitive)
- **Range:** 0.0 to 1.0 (higher is better)
- **Use case:** Strict matching for critical text elements

### Mean Similarity

**Formula:** Uses `difflib.SequenceMatcher.ratio()`

- **What it measures:** Average text similarity score
- **Range:** 0.0 to 1.0 (higher is better)
- **Note:** More forgiving than exact match, accounts for partial matches

## Hierarchy Structure Metrics

Hierarchy metrics evaluate how well the predicted DOM tree structure matches the ground truth.

### Parent Accuracy

**Formula:** `Parent_Accuracy = Correct_Parents / Total_Elements`

- **What it measures:** Percentage of elements with correct parent assignment
- **Range:** 0.0 to 1.0 (higher is better)

```
Ground Truth:          Predicted:
    Root                  Root
    ├── Group1            ├── Group1
    │   ├── Button        │   ├── Button ✓
    │   └── Text          │   └── Icon   ✗ (wrong parent)
    └── Group2            └── Group2
        └── Input             └── Input ✓
```

### Depth Accuracy

**Formula:** `Depth_Accuracy = Correct_Depths / Total_Elements`

- **What it measures:** Percentage of elements at correct tree depth
- **Range:** 0.0 to 1.0 (higher is better)
- **Note:** Depth 0 = root, Depth 1 = direct children, etc.

### Sibling Order Accuracy

**Formula:** `Sibling_Order_Accuracy = Correct_Orders / Total_Sibling_Pairs`

- **What it measures:** Whether sibling elements are in correct order
- **Range:** 0.0 to 1.0 (higher is better)
- **Use case:** Important for forms, lists, navigation

### Structure Similarity

**Formula:** `Structure_Similarity = 1 - (Tree_Edit_Distance / Tree_Size)`

- **What it measures:** Overall structural similarity
- **Range:** 0.0 to 1.0 (higher is better)
- **Note:** Based on tree edit distance (minimum operations to transform)

## Locator Quality Metrics

Locator metrics evaluate how useful the generated locators are for UI automation.

### Coverage

**Formula:** `Coverage = Elements_With_Locators / Total_Elements`

- **What it measures:** Percentage of elements with at least one locator
- **Range:** 0.0 to 1.0 (higher is better)
- **Target:** 100% coverage is ideal

### Text Locator Rate

**Formula:** `Text_Rate = Text_Locatable / Total_Elements`

- **What it measures:** Percentage of elements locatable by text
- **Range:** 0.0 to 1.0 (higher is better)
- **Why important:** Text locators are most readable and maintainable

### Uniqueness Rate

**Formula:** `Uniqueness = Unique_Locators / Total_Locators`

- **What it measures:** Percentage of locators that uniquely identify elements
- **Range:** 0.0 to 1.0 (higher is better)
- **Why important:** Non-unique locators may select wrong elements

### Duplicate Rate

**Formula:** `Duplicate_Rate = Duplicate_Locators / Total_Elements`

- **What it measures:** Percentage of elements with ambiguous locators
- **Range:** 0.0 to 1.0 (lower is better)
- **Why important:** Duplicates cause automation failures

### Locator Type Distribution

Shows the count of each locator type:
- `id` - Element ID
- `text` - Text content
- `type_index` - Type with index (e.g., `button[0]`)
- `bounds` - Bounding box coordinates
- `center` - Center point coordinates

## Full-lifecycle benchmark (unified, cross-model)

> The complete methodology — mechanism, test plan, flow diagram, and metric
> definitions — is in
> [`benchmarks/README.md`](https://github.com/milanac030988/vizdom/blob/main/benchmarks/README.md);
> this section is the summary.

Per-stage metrics grade a component; a test suite lives or dies on the **whole
lifecycle** — locate → act → verify. The lifecycle benchmark
(`visual_dom.evaluation.lifecycle`) runs every system under comparison over **one
unified step set** and scores the same outcomes, so parser-based systems and
per-step grounding models become directly comparable.

**Steps carry a dual representation** derived automatically from the element
ground truth (only captions *unique* in their state are used):

- a **locator** (`text="Save"`) for DOM-based executors, and
- a **natural-language instruction** ("click the 'Save' button") for grounders,
- plus GT target bounds and, for verification steps, an expected verdict —
  including **negative oracle steps** on deliberately absent targets, because a
  *testing* system's worst failure is a **false pass**, a metric agent
  benchmarks do not measure.

**Executors:**

| Executor | Paradigm | Cost model |
|---|---|---|
| `vizdom-uied`, `vizdom-omniparser` | parse once per state, resolve each step in the cached DOM | N parses + cheap lookups |
| `elam-7b` (Apache-2.0, Molmo-7B-D) | per-step grounding **with a native PASSED/FAILED verdict mode** | 1 inference per step |
| `ui-tars-1.5-7b` (Apache-2.0, Qwen2.5-VL) | per-step grounding; verdicts proxied via grounding success | 1 inference per step |
| `aria-ui` | 25.3 B MoE — **not runnable on workstation hardware**; column cited from published numbers | — |

```bash
python -m visual_dom.evaluation.lifecycle.generate            # (re)build steps.json
python -m visual_dom.evaluation.lifecycle.runner     --executors vizdom-uied,vizdom-omniparser                 # runnable today
# grounder columns (7-8 B VLMs; needs torch+transformers+accelerate+bitsandbytes,
# ~15 GB weight download each; on a 6 GB GPU they run 4-bit + CPU-offload, slowly):
python -m visual_dom.evaluation.lifecycle.runner --executors elam-7b
```

**First baseline** — `lifecycle-synthetic-v1`: 44 states, 514 steps
(213 action / 213 positive verify / 88 negative verify):

| executor | action-hit | verify acc | false-pass | resolution / step | one-time load | parse / state |
|---|---|---|---|---|---|---|
| vizdom-uied | **0.803** | 0.957 | **0.000** | < 1 ms | 7.2 s | 2.11 s (44 states, 92.9 s) |
| vizdom-omniparser | **0.916** | 0.957 | **0.000** | < 1 ms | 26.9 s | 4.81 s (44 states, 211.8 s) |

Model load is reported **separately** from parsing (a dummy-frame warm-up at
connect time flushes lazy first-use initializations such as the EasyOCR
reader): warm-model amortization is itself a claim under test (NFR3), so it
must not be smeared into one arbitrary state's parse time.

Reading the numbers: OmniParser converts its detection edge into an 11-point
action-hit lead at ~2.3× the parse cost; both stacks share the identical
verify accuracy (the same 13 captions are misread by OCR upstream of both) —
and both hold a **zero false-pass rate**, which the exactly-one resolution
contract guarantees by construction. Every result file is stamped with dataset id + git commit;
per-step outcomes are kept so failures remain attributable to a stage.

Planned extensions: the grounder columns above, real-application states in the
same schema, `desc=` per-tier accuracy as an additional locator column, and
defect injection (mutate a state, measure whether the suite catches it).

## Interpreting Results

### Quality Levels

| Metric | Excellent | Good | Fair | Poor |
|--------|-----------|------|------|------|
| F1 Score | > 0.90 | 0.75-0.90 | 0.50-0.75 | < 0.50 |
| Mean IoU | > 0.80 | 0.60-0.80 | 0.40-0.60 | < 0.40 |
| Char Accuracy | > 0.95 | 0.85-0.95 | 0.70-0.85 | < 0.70 |
| Parent Accuracy | > 0.90 | 0.75-0.90 | 0.50-0.75 | < 0.50 |
| Locator Coverage | 100% | 90-100% | 70-90% | < 70% |

### Common Issues and Solutions

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| Low Precision | Over-detection, noise | Increase confidence threshold |
| Low Recall | Under-detection | Decrease confidence threshold |
| Low IoU | Bounding box misalignment | Improve CV detection |
| High CER | OCR model issues | Use different OCR engine, better image |
| Low Parent Accuracy | Hierarchy builder issues | Adjust containment thresholds |
| Low Text Locator Rate | Missing OCR text | Improve OCR, lower confidence |

## Creating Ground Truth

Ground truth files should follow the same JSON format as Visual DOM output:

```json
{
  "image_size": {"width": 1920, "height": 1080},
  "dom": {
    "hierarchy": {
      "id": "ROOT",
      "bounds": [0, 0, 1920, 1080],
      "visual_type": "container",
      "children": [
        {
          "id": "E1",
          "bounds": [100, 200, 300, 250],
          "visual_type": "button",
          "text": "Submit",
          "children": []
        }
      ]
    }
  }
}
```

### Annotation Guidelines

1. **Bounds Format:** `[x1, y1, x2, y2]` (top-left to bottom-right)
2. **Visual Types:** Use standard types: `button`, `text`, `input_field`, `checkbox`, `icon`, `container`, `block`
3. **Text:** Include exact text content as displayed
4. **Hierarchy:** Nest elements that visually contain other elements

### Tools for Annotation

- **Visual DOM Viewer** - Load screenshot, manually annotate elements
- **LabelImg** - General-purpose bounding box annotation
- **CVAT** - Computer Vision Annotation Tool

## API Reference

### VisualDOMEvaluator

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationConfig

# Configure evaluation
config = EvaluationConfig(
    iou_threshold=0.5,          # IoU threshold for matching
    iou_good_threshold=0.75,    # Threshold for "good" match
    strict_text_matching=False, # Exact text match required
    min_text_similarity=0.8,    # Minimum similarity for OCR
    evaluate_hierarchy=True,    # Evaluate hierarchy metrics
    evaluate_locators=True,     # Evaluate locator metrics
)

evaluator = VisualDOMEvaluator(config)

# Single evaluation
result = evaluator.evaluate(predicted_dict, ground_truth_dict)
result = evaluator.evaluate_from_files("pred.json", "gt.json")

# Batch evaluation
batch_result = evaluator.evaluate_batch(predictions_list, ground_truths_list)
```

### EvaluationResult

```python
result = evaluator.evaluate(pred, gt)

# Access metrics
result.element_metrics.precision
result.element_metrics.recall
result.element_metrics.f1_score
result.element_metrics.mean_iou

result.ocr_metrics.cer
result.ocr_metrics.wer
result.ocr_metrics.char_accuracy

result.hierarchy_metrics.parent_accuracy
result.hierarchy_metrics.depth_accuracy

result.locator_metrics.coverage
result.locator_metrics.text_locator_rate

# Generate output
print(result.summary())           # Text summary
result.to_dict()                  # Dictionary
```

### EvaluationReport

```python
from visual_dom.evaluation import EvaluationReport

report = EvaluationReport(result)

# Generate reports
report.to_text()                  # Plain text
report.to_markdown()              # Markdown
report.to_html()                  # HTML with styling
report.to_json()                  # JSON

# Save to file
report.save_json("report.json")
report.save_markdown("report.md")
report.save_html("report.html")
```

## Examples

### Example 1: Basic Evaluation

```python
from visual_dom.evaluation import VisualDOMEvaluator

evaluator = VisualDOMEvaluator()
result = evaluator.evaluate_from_files(
    "output/calculator_dom.json",
    "ground_truth/calculator_gt.json"
)

print(f"F1 Score: {result.element_metrics.f1_score:.2%}")
print(f"OCR Accuracy: {result.ocr_metrics.char_accuracy:.2%}")
```

### Example 2: Batch Evaluation with Report

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationConfig
from visual_dom.evaluation.report import BatchEvaluationReport
from pathlib import Path
import json

# Load all test cases
predictions = []
ground_truths = []

for pred_file in Path("test_outputs/").glob("*.json"):
    gt_file = Path("ground_truths/") / pred_file.name
    if gt_file.exists():
        with open(pred_file) as f:
            predictions.append(json.load(f))
        with open(gt_file) as f:
            ground_truths.append(json.load(f))

# Evaluate
config = EvaluationConfig(iou_threshold=0.5)
evaluator = VisualDOMEvaluator(config)
batch_result = evaluator.evaluate_batch(predictions, ground_truths)

# Report
print(batch_result.summary())
print(f"Mean F1: {batch_result.mean_f1:.2%}")

report = BatchEvaluationReport(batch_result)
report.save_markdown("batch_evaluation.md")
```

### Example 3: Custom Thresholds

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationConfig

# Strict evaluation
strict_config = EvaluationConfig(
    iou_threshold=0.75,           # Higher IoU required
    strict_text_matching=True,    # Exact text match
    min_text_similarity=0.95,
)

# Lenient evaluation
lenient_config = EvaluationConfig(
    iou_threshold=0.25,           # Lower IoU accepted
    strict_text_matching=False,
    min_text_similarity=0.5,
)

strict_evaluator = VisualDOMEvaluator(strict_config)
lenient_evaluator = VisualDOMEvaluator(lenient_config)

strict_result = strict_evaluator.evaluate(pred, gt)
lenient_result = lenient_evaluator.evaluate(pred, gt)

print(f"Strict F1:  {strict_result.element_metrics.f1_score:.2%}")
print(f"Lenient F1: {lenient_result.element_metrics.f1_score:.2%}")
```
