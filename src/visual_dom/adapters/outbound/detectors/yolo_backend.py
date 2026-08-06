"""
YOLO detector backend (Ultralytics).

WARNING — LICENSING: Ultralytics YOLO (and any weights trained through it) is
AGPL-3.0. Distributing or network-serving this project while this backend is
active carries AGPL obligations. See docs/discussion/landscape-comparison-*.html
section 9. For permissive reuse, prefer a detector from an Apache-licensed
upstream (e.g. original RT-DETR) rather than the ultralytics package.
"""

from typing import List, Optional

import numpy as np

from visual_dom.core.ports.outbound.detector_port import Detection, DetectorBackend
from visual_dom.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_CLASSES = [
    "button", "text", "icon", "input_field", "checkbox",
    "radio_button", "toggle", "slider", "dropdown", "image",
    "container", "toolbar", "navbar", "card", "list_item",
]


class YOLOBackend(DetectorBackend):
    name = "yolo"
    description = "Ultralytics YOLO detector. GPU recommended. Requires a .pt weights file."
    license = "AGPL-3.0"  # inherited from ultralytics
    requires_gpu = True

    def __init__(
        self,
        model_path: str,
        use_gpu: bool = True,
        confidence_threshold: float = 0.3,
        classes: Optional[List[str]] = None,
    ):
        if not model_path:
            raise ValueError("YOLOBackend requires model_path to a .pt weights file")

        from ultralytics import YOLO  # raises ImportError if not installed

        self._model = YOLO(model_path)
        self._device = "cuda:0" if use_gpu else "cpu"
        self._conf = confidence_threshold
        self._classes = classes or self._load_classes()
        log.info("YOLO model loaded: %s", model_path)

    @staticmethod
    def _load_classes() -> List[str]:
        try:
            from models.configs.cv_model_registry import UI_ELEMENT_CLASSES
            return list(UI_ELEMENT_CLASSES)
        except Exception:
            return list(_DEFAULT_CLASSES)

    @classmethod
    def is_available(cls) -> bool:
        try:
            import ultralytics  # noqa: F401
            return True
        except Exception:
            return False

    def detect(self, image: np.ndarray) -> List[Detection]:
        results = self._model(image, conf=self._conf, verbose=False)
        detections: List[Detection] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                vtype = self._classes[cls_id] if cls_id < len(self._classes) else "unknown"
                detections.append(
                    Detection(
                        bounds=(x1, y1, x2, y2),
                        visual_type=vtype,
                        confidence=conf,
                        source="yolo",
                    )
                )
        log.info("YOLO detected %d elements", len(detections))
        return detections
