"""
Pluggable element-detection backends.

A detector backend turns a screenshot into a flat list of `Detection` objects
(geometry + coarse type). This lets the pipeline swap the detection stage —
UIED (default), YOLO, or Microsoft OmniParser — behind one stable interface,
supporting both empirical comparison and licence flexibility.

See docs/discussion/landscape-comparison-*.html for the rationale.
"""

from .base import Detection, DetectorBackend
from .registry import create_detector, list_detectors, register

__all__ = [
    "Detection",
    "DetectorBackend",
    "create_detector",
    "list_detectors",
    "register",
]
