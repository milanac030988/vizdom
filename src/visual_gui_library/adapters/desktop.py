"""
Desktop platform adapter using pyautogui.
"""

from typing import Tuple, Optional
import numpy as np

from .base import BaseAdapter


class DesktopAdapter(BaseAdapter):
    """Desktop adapter using pyautogui for Windows/macOS/Linux."""

    def __init__(self, failsafe: bool = True):
        """
        Initialize desktop adapter.

        Args:
            failsafe: Enable pyautogui failsafe (move to corner to abort)
        """
        self.failsafe = failsafe
        self._pyautogui = None

    def _init_pyautogui(self):
        """Lazy initialization of pyautogui."""
        if self._pyautogui is not None:
            return

        import pyautogui
        pyautogui.FAILSAFE = self.failsafe
        self._pyautogui = pyautogui

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """Capture screen using pyautogui."""
        self._init_pyautogui()

        if region:
            screenshot = self._pyautogui.screenshot(region=region)
        else:
            screenshot = self._pyautogui.screenshot()

        # Convert PIL to numpy BGR
        import cv2
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def click(self, x: int, y: int, click_type: str = "single") -> None:
        """Click at coordinates using pyautogui."""
        self._init_pyautogui()

        if click_type == "double":
            self._pyautogui.doubleClick(x, y)
        elif click_type == "right":
            self._pyautogui.rightClick(x, y)
        else:
            self._pyautogui.click(x, y)

    def type_text(self, text: str) -> None:
        """Type text using pyautogui."""
        self._init_pyautogui()
        self._pyautogui.typewrite(text, interval=0.02)

    def press_key(self, key: str) -> None:
        """Press key using pyautogui."""
        self._init_pyautogui()

        # Handle key combinations like "ctrl+a"
        if "+" in key:
            keys = key.split("+")
            self._pyautogui.hotkey(*keys)
        else:
            self._pyautogui.press(key)

    def scroll(
        self,
        x: int,
        y: int,
        direction: str = "down",
        amount: int = 1
    ) -> None:
        """Scroll using pyautogui."""
        self._init_pyautogui()

        # Move to position first
        self._pyautogui.moveTo(x, y)

        clicks = amount * 3  # 3 scroll clicks per "page"
        if direction == "up":
            self._pyautogui.scroll(clicks)
        elif direction == "down":
            self._pyautogui.scroll(-clicks)
        elif direction == "left":
            self._pyautogui.hscroll(-clicks)
        elif direction == "right":
            self._pyautogui.hscroll(clicks)
