"""
Region-proposer contract — stage 1 of the modular detector (ADR-027).

A region proposer finds candidate *interactable* regions (buttons, icons,
fields) in a screenshot. It is deliberately dumber than a full detector: no
text, no captions, no hierarchy — geometry and a confidence, nothing else.
Text reading is stage 2 (the existing `TextDetector`, ADR-012) and semantics
are stage 3 (`Captioner`); the `modular` backend fuses the three.

Kept separate from `DetectorBackend` on purpose: a proposer is a *component of*
a detector, not a detector — it does not emit `Detection` objects and cannot be
selected as `detector.backend`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class RegionProposal:
    """One candidate interactable region."""

    bounds: Tuple[int, int, int, int]   # (x1, y1, x2, y2) pixels
    confidence: float                   # the model's own score, in [0, 1]

    @property
    def area(self) -> int:
        return max(0, self.bounds[2] - self.bounds[0]) * \
            max(0, self.bounds[3] - self.bounds[1])


class RegionProposer(ABC):
    """Abstract stage-1 model: interactable-region candidates for one image."""

    #: short registry name, e.g. "omniparser", "uied"
    name: str = "base"

    #: licence of the underlying model/weights (AGPL matters here - ADR-027)
    license: str = "unknown"

    requires_gpu: bool = False

    @abstractmethod
    def propose(self, image: np.ndarray) -> List[RegionProposal]:
        """
        Propose interactable regions in a BGR image.

        Returns an empty list when nothing is found; raises only on genuine
        misconfiguration (missing weights), never on "no regions".
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release model resources. Optional."""
