"""
Detector backend contract.

Defines the neutral detection type and the abstract backend interface that all
element detectors (UIED, YOLO, OmniParser, ...) implement.

Design notes
------------
Backends return `Detection` objects rather than the pipeline's `UIElement` so
that this package has no dependency on `pipeline.py` (which imports it). The
pipeline adapts `Detection` -> `UIElement` in one place.

`Detection` carries only what a detector can actually know: geometry, a coarse
type, a confidence, and optionally text/interactability. Semantics, hierarchy
and IDs are assigned later by the pipeline — consistent with the project rule
that CV owns geometry and downstream stages own meaning.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class Detection:
    """
    A single detected UI element, independent of which backend found it.

    Attributes:
        bounds: (x1, y1, x2, y2) in pixel coordinates of the input image
        visual_type: coarse type string ("button", "icon", "text", "unknown", ...)
        confidence: detector confidence in [0, 1]
        text: OCR/caption text if the backend provides it
        interactable: whether the element is actionable, if the backend predicts it
                      (OmniParser provides this; UIED/YOLO leave it None)
        source: name of the backend that produced this detection
        parent_id / children_ids: containment info if the backend computes it
                      (UIED does; most others do not)
        extra: backend-specific payload, kept for debugging/evaluation
    """

    bounds: Tuple[int, int, int, int]
    visual_type: str = "unknown"
    confidence: float = 1.0
    text: Optional[str] = None      # literal OCR-read text (None if not read from pixels)
    label: Optional[str] = None     # semantic name/caption (model prediction, e.g. an icon caption)
    interactable: Optional[bool] = None
    source: str = "unknown"
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def area(self) -> int:
        return self.width * self.height


class DetectorBackend(ABC):
    """
    Abstract element-detection backend.

    Subclasses declare their identity and licensing up front so that callers can
    reason about dependencies without importing heavy libraries. `is_available()`
    must be cheap and must not raise.
    """

    #: short registry name, e.g. "uied"
    name: str = "base"

    #: human-readable description shown by `list_detectors()`
    description: str = ""

    #: SPDX-ish licence of the backend's model/weights. Surfaced deliberately:
    #: some backends (YOLO/Ultralytics, OmniParser's icon_detect) are AGPL-3.0,
    #: which constrains how this project may be distributed.
    license: str = "unknown"

    #: whether the backend realistically needs a GPU
    requires_gpu: bool = False

    @abstractmethod
    def detect(self, image: np.ndarray) -> List[Detection]:
        """
        Detect UI elements in a BGR image.

        Args:
            image: BGR image as a numpy array (as produced by cv2.imread)

        Returns:
            List of Detection objects. Returns an empty list when nothing is
            found. Implementations should raise only on genuine misconfiguration
            (e.g. missing weights), not on "no detections".
        """
        raise NotImplementedError

    @classmethod
    def is_available(cls) -> bool:
        """
        Whether this backend's dependencies are importable.

        Must never raise — return False instead. Availability does not imply the
        model weights are present; that is checked at construction time.
        """
        return True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name!r} license={self.license!r}>"
