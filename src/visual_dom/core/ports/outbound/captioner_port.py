"""
Captioner contract — stage 3 of the modular detector (ADR-027).

A captioner names glyphs: given the regions that survived fusion *without* any
OCR-readable text (icons, symbols), it predicts a short semantic caption for
each ("settings icon", "close button"). Captions become the element's `label`
- a model prediction - never its `text`, which is reserved for literal
pixel-reads (the ADR-016 text/label separation).

The stage is OPTIONAL by design. Without a captioner, icons carry no label and
`desc=` locators fall back to tier-2 VLM grounding (ADR-022) - slower
resolution in exchange for not loading a caption model at all.

Batching note: this is a batch interface on purpose. OmniParser pushes up to
128 crops through Florence-2 per call; a per-crop interface would lock
implementations into the slow path (ADR-027, "caption batching").
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np


class Captioner(ABC):
    """Abstract stage-3 model: a semantic caption per unlabelled region."""

    #: short registry name, e.g. "florence", "none"
    name: str = "base"

    license: str = "unknown"

    requires_gpu: bool = False

    @abstractmethod
    def caption(
        self,
        image: np.ndarray,
        boxes: List[Tuple[int, int, int, int]],
    ) -> List[Optional[str]]:
        """
        Caption each region of a BGR image.

        Args:
            image: the full screenshot (BGR).
            boxes: pixel (x1, y1, x2, y2) regions to caption.

        Returns:
            One entry per input box, in order. `None` for a region the model
            could not caption - callers must not assume every box gets a name.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release model resources. Optional."""
