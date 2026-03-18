"""
Base adapter interface for platform-specific actions.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional
import numpy as np


class BaseAdapter(ABC):
    """Abstract base class for platform adapters."""

    @abstractmethod
    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """
        Capture screen or region.

        Args:
            region: Optional (x, y, width, height) to capture

        Returns:
            Screenshot as numpy array (BGR)
        """
        pass

    @abstractmethod
    def click(self, x: int, y: int, click_type: str = "single") -> None:
        """
        Click at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            click_type: "single", "double", or "right"
        """
        pass

    @abstractmethod
    def type_text(self, text: str) -> None:
        """
        Type text at current focus.

        Args:
            text: Text to type
        """
        pass

    @abstractmethod
    def press_key(self, key: str) -> None:
        """
        Press a keyboard key.

        Args:
            key: Key name (e.g., "enter", "tab", "backspace")
        """
        pass

    @abstractmethod
    def scroll(
        self,
        x: int,
        y: int,
        direction: str = "down",
        amount: int = 1
    ) -> None:
        """
        Scroll at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            direction: "up", "down", "left", "right"
            amount: Scroll amount
        """
        pass

    def select_all(self) -> None:
        """Select all text in focused element."""
        self.press_key("ctrl+a")

    def clear_text(self) -> None:
        """Clear text in focused element."""
        self.select_all()
        self.press_key("delete")
