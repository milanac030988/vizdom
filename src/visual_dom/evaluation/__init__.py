"""
Visual DOM Evaluation Framework

Provides metrics and tools for evaluating Visual DOM detection quality:
- Element detection metrics (precision, recall, F1, IoU)
- OCR accuracy metrics (CER, WER)
- Hierarchy structure metrics
- Locator quality metrics
"""

from .metrics import (
    ElementMetrics,
    OCRMetrics,
    HierarchyMetrics,
    LocatorMetrics,
)
from .evaluator import VisualDOMEvaluator
from .report import EvaluationReport

__all__ = [
    "ElementMetrics",
    "OCRMetrics",
    "HierarchyMetrics",
    "LocatorMetrics",
    "VisualDOMEvaluator",
    "EvaluationReport",
]
