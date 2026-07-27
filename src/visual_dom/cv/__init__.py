"""
Computer Vision modules for element detection and OCR.

This module implements the UIED-inspired coarse-to-fine detection strategy:
1. Text detection via OCR (EasyOCR/PaddleOCR/Tesseract)
2. Non-text detection via traditional CV (edge detection, contours)
3. Merge and deduplicate results
4. Build containment-based hierarchy

Based on the paper:
"Object Detection for Graphical User Interface: Old Fashioned or Deep Learning or a Combination?"
https://arxiv.org/abs/2008.05132
"""

from .text_detector import TextDetector, TextElement, detect_text
from .element_detector import ElementDetector, UIElement, VisualType
from .uied_detection import UIEDDetector, DetectedElement, ElementType, detect_ui_elements
from .pipeline import VisualDOMPipeline, extract_elements
from .slm_advisor import SLMAdvisor
from .detectors import Detection, DetectorBackend, create_detector, list_detectors
from .image_processing import (
    preprocess_image,
    ProcessedImage,
    calculate_iou,
    non_max_suppression,
    is_contained,
)

__all__ = [
    # Main pipeline
    "VisualDOMPipeline",
    "extract_elements",

    # Text detection
    "TextDetector",
    "TextElement",
    "detect_text",

    # UIED detection
    "UIEDDetector",
    "DetectedElement",
    "ElementType",
    "detect_ui_elements",

    # Legacy element detector
    "ElementDetector",
    "UIElement",
    "VisualType",

    # SLM advisor
    "SLMAdvisor",

    # Pluggable detector backends
    "Detection",
    "DetectorBackend",
    "create_detector",
    "list_detectors",

    # Image processing utilities
    "preprocess_image",
    "ProcessedImage",
    "calculate_iou",
    "non_max_suppression",
    "is_contained",
]
