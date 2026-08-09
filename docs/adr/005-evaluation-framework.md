# ADR-005: Evaluation Framework and Metrics

## Status

Accepted

## Date

2025-01-26

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2025-01-26 | 1.0 | Initial version |

## Context

To measure and improve the Visual DOM system quality, we need:

1. **Quantitative metrics** to compare detection accuracy
2. **Benchmarking capability** across different configurations
3. **Regression testing** to catch quality degradation
4. **Reporting** for documentation and analysis

The evaluation should cover:
- Element detection quality (did we find the right elements?)
- OCR accuracy (did we read text correctly?)
- Hierarchy correctness (did we build the right tree structure?)
- Locator usefulness (can automation tools use our output?)

## Decision

Implement a comprehensive **Evaluation Framework** with four metric categories:

### 1. Element Detection Metrics

Measure how well we detect UI elements using object detection metrics.

| Metric | Formula | Description |
|--------|---------|-------------|
| **Precision** | TP / (TP + FP) | Of predictions, how many are correct |
| **Recall** | TP / (TP + FN) | Of ground truth, how many found |
| **F1 Score** | 2×P×R / (P+R) | Harmonic mean of P and R |
| **Mean IoU** | avg(IoU scores) | Average bounding box overlap |

```python
@dataclass
class ElementMetrics:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    iou_scores: List[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0
```

### 2. OCR Accuracy Metrics

Measure text recognition quality using standard OCR metrics.

| Metric | Formula | Description |
|--------|---------|-------------|
| **CER** | (I+D+S) / total_chars | Character Error Rate |
| **WER** | (I+D+S) / total_words | Word Error Rate |
| **Char Accuracy** | 1 - CER | Character-level accuracy |
| **Exact Match** | exact_matches / total | Perfect text match rate |

```python
@dataclass
class OCRMetrics:
    char_insertions: int = 0
    char_deletions: int = 0
    char_substitutions: int = 0
    total_chars_gt: int = 0

    @property
    def cer(self) -> float:
        errors = self.char_insertions + self.char_deletions + self.char_substitutions
        return errors / self.total_chars_gt if self.total_chars_gt > 0 else 0

    @property
    def char_accuracy(self) -> float:
        return max(0, 1 - self.cer)
```

### 3. Hierarchy Structure Metrics

Measure how well we build the DOM tree structure.

| Metric | Description |
|--------|-------------|
| **Parent Accuracy** | Elements with correct parent assignment |
| **Depth Accuracy** | Elements at correct tree depth |
| **Sibling Order Accuracy** | Sibling pairs in correct order |
| **Structure Similarity** | 1 - normalized tree edit distance |

```python
@dataclass
class HierarchyMetrics:
    correct_parents: int = 0
    total_elements: int = 0
    tree_edit_distance: int = 0

    @property
    def parent_accuracy(self) -> float:
        return self.correct_parents / self.total_elements

    @property
    def structure_similarity(self) -> float:
        return max(0, 1 - self.tree_edit_distance / self.tree_size)
```

### 4. Locator Quality Metrics

Measure usefulness of generated locators for automation.

| Metric | Description |
|--------|-------------|
| **Coverage** | Elements with at least one locator |
| **Text Locator Rate** | Elements locatable by text (preferred) |
| **Uniqueness Rate** | Locators that uniquely identify elements |
| **Duplicate Rate** | Elements with ambiguous locators |

```python
@dataclass
class LocatorMetrics:
    total_elements: int = 0
    text_locatable: int = 0
    unique_locators: int = 0

    @property
    def text_locator_rate(self) -> float:
        return self.text_locatable / self.total_elements

    @property
    def uniqueness_rate(self) -> float:
        return self.unique_locators / self.total_elements
```

### Evaluator Usage

```python
from visual_dom.evaluation import VisualDOMEvaluator, EvaluationConfig

# Configure evaluation
config = EvaluationConfig(
    iou_threshold=0.5,          # 50% overlap required for match
    evaluate_hierarchy=True,
    evaluate_locators=True,
)

# Create evaluator
evaluator = VisualDOMEvaluator(config)

# Single evaluation
result = evaluator.evaluate_from_files("predicted.json", "ground_truth.json")
print(result.summary())

# Batch evaluation
batch_result = evaluator.evaluate_batch(predictions, ground_truths)
print(f"Mean F1: {batch_result.mean_f1:.2%}")
```

### Report Generation

```python
from visual_dom.evaluation import EvaluationReport

report = EvaluationReport(result)

# Multiple output formats
report.save_json("report.json")
report.save_markdown("report.md")
report.save_html("report.html")

print(report.to_text())
```

### Quality Thresholds

| Metric | Excellent | Good | Fair | Poor |
|--------|-----------|------|------|------|
| F1 Score | > 0.90 | 0.75-0.90 | 0.50-0.75 | < 0.50 |
| Mean IoU | > 0.80 | 0.60-0.80 | 0.40-0.60 | < 0.40 |
| Char Accuracy | > 0.95 | 0.85-0.95 | 0.70-0.85 | < 0.70 |
| Parent Accuracy | > 0.90 | 0.75-0.90 | 0.50-0.75 | < 0.50 |

## Consequences

### Positive

- **Quantitative quality tracking**: Objective measurement of system performance
- **Regression detection**: Catch quality degradation early
- **Configuration tuning**: Compare different settings objectively
- **Documentation**: Clear metrics for project status

### Negative

- **Ground truth required**: Need manually annotated data
- **Metric limitations**: Some quality aspects hard to quantify
- **Annotation burden**: Creating ground truth is time-consuming

### Neutral

- Metrics may not capture all aspects of "good" detection
- Different use cases may prioritize different metrics
- Thresholds are guidelines, not strict requirements

## Alternatives Considered

### 1. Manual Inspection Only (Rejected)

Rely only on visual inspection of results.

Rejected because:
- Not scalable
- Subjective
- Cannot track regression
- Not reproducible

### 2. User Acceptance Testing Only (Rejected)

Only measure end-to-end automation success.

Rejected because:
- Too coarse-grained
- Hard to diagnose failures
- Doesn't isolate detection vs. automation issues

### 3. Custom Metric Design (Deferred)

Design completely novel metrics specific to Visual DOM.

Deferred because:
- Standard metrics well understood
- Easier to compare with other systems
- Can add custom metrics later if needed

## References

- COCO evaluation metrics: https://cocodataset.org/#detection-eval
- OCR evaluation standards
- Source: `src/visual_dom/evaluation/metrics.py`
- Source: `src/visual_dom/evaluation/evaluator.py`
- Documentation: `docs/EVALUATION.md`
