"""
UIED detector backend.

Thin adapter around the existing `UIEDDetector` (traditional CV, coarse-to-fine).
This is the default backend: no GPU, no external weights, permissive to ship.
"""

from typing import List

import numpy as np

from .base import Detection, DetectorBackend


class UIEDBackend(DetectorBackend):
    name = "uied"
    description = "Traditional CV coarse-to-fine detector (UIED-inspired). CPU, no weights."
    license = "project"  # our own code; depends only on OpenCV (BSD/Apache)
    requires_gpu = False

    def __init__(self, min_element_area: int = 100, nms_threshold: float = 0.5):
        # Imported lazily so this module stays importable even if a future
        # refactor moves UIEDDetector.
        from ..uied_detection import UIEDDetector

        self._detector = UIEDDetector(
            min_element_area=min_element_area,
            nms_threshold=nms_threshold,
        )

    def detect(self, image: np.ndarray) -> List[Detection]:
        results = self._detector.detect(image)
        detections: List[Detection] = []
        for de in results:
            detections.append(
                Detection(
                    bounds=tuple(de.bounds),
                    visual_type=de.element_type.value,
                    confidence=de.confidence,
                    text=de.text,
                    source="uied",
                    parent_id=de.parent_id,
                    children_ids=list(de.children_ids),
                )
            )
        return detections
