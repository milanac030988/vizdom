"""
Visual DOM Evaluation Framework

Provides metrics and tools for evaluating Visual DOM detection quality:
- Element detection metrics (precision, recall, F1, IoU)
- OCR accuracy metrics (CER, WER)
- Hierarchy structure metrics
- Locator quality metrics
"""

from visual_dom.evaluation.metrics import (
    ElementMetrics,
    OCRMetrics,
    HierarchyMetrics,
    LocatorMetrics,
)
from visual_dom.evaluation.evaluator import VisualDOMEvaluator
from visual_dom.evaluation.report import EvaluationReport

__all__ = [
    "ElementMetrics",
    "OCRMetrics",
    "HierarchyMetrics",
    "LocatorMetrics",
    "VisualDOMEvaluator",
    "EvaluationReport",
]
