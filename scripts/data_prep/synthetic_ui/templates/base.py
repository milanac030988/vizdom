"""Base class for UI templates."""

import numpy as np
from abc import ABC, abstractmethod
from typing import List, Tuple

from ..primitives import Element
from ..themes import Theme


class UITemplate(ABC):
    """Abstract base for synthetic UI templates.

    All pixel values and font sizes are designed for 800x600 reference.
    The `s()` method scales them to the actual canvas resolution.
    """

    name: str = "base"

    # Reference resolution for all hardcoded values
    REF_WIDTH = 800
    REF_HEIGHT = 600

    def __init__(self, width: int, height: int, theme: Theme, rng: np.random.Generator):
        self.width = width
        self.height = height
        self.theme = theme
        self.rng = rng
        self.elements: List[Element] = []
        self._id_counter = 0

        # Scale factor based on canvas vs reference
        self._scale = min(width / self.REF_WIDTH, height / self.REF_HEIGHT)

    def s(self, value) -> int:
        """Scale a pixel value to current resolution."""
        return max(1, int(value * self._scale))

    def sf(self, value: float) -> float:
        """Scale a float value (e.g. font_size) to current resolution."""
        return max(1.0, value * self._scale)

    def next_id(self) -> str:
        self._id_counter += 1
        return f"E{self._id_counter}"

    @abstractmethod
    def generate(self) -> Tuple[np.ndarray, List[Element]]:
        """Generate a synthetic UI screenshot with ground truth elements.

        Returns:
            (image, elements) - BGR numpy array and list of Element
        """
        ...

    def create_canvas(self) -> np.ndarray:
        """Create a blank canvas with the background color."""
        img = np.full((self.height, self.width, 3), self.theme.background, dtype=np.uint8)
        return img

    def jitter(self, value: int, amount: int = 8) -> int:
        """Add random positional jitter."""
        return value + int(self.rng.integers(-self.s(amount), self.s(amount) + 1))

    def pick(self, items: list):
        """Pick a random item from a list."""
        return items[self.rng.integers(0, len(items))]

    def pick_n(self, items: list, n: int) -> list:
        """Pick n unique random items from a list."""
        n = min(n, len(items))
        indices = self.rng.choice(len(items), size=n, replace=False)
        return [items[i] for i in indices]

    def rand_int(self, low: int, high: int) -> int:
        """Random integer in [low, high]."""
        return int(self.rng.integers(low, high + 1))

    def rand_bool(self, prob: float = 0.5) -> bool:
        """Random boolean with given probability."""
        return self.rng.random() < prob
