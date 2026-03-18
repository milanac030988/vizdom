"""
Android platform adapter using ADB.
"""

import subprocess
from typing import Tuple, Optional
import numpy as np

from .base import BaseAdapter


class AndroidAdapter(BaseAdapter):
    """Android adapter using ADB commands."""

    def __init__(self, device_serial: Optional[str] = None):
        """
        Initialize Android adapter.

        Args:
            device_serial: ADB device serial (None for default device)
        """
        self.device_serial = device_serial
        self._adb_prefix = self._build_adb_prefix()

    def _build_adb_prefix(self) -> list:
        """Build ADB command prefix."""
        if self.device_serial:
            return ["adb", "-s", self.device_serial]
        return ["adb"]

    def _run_adb(self, *args) -> subprocess.CompletedProcess:
        """Run ADB command."""
        cmd = self._adb_prefix + list(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def _run_shell(self, *args) -> subprocess.CompletedProcess:
        """Run ADB shell command."""
        return self._run_adb("shell", *args)

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """Capture Android screen via ADB."""
        import cv2
        import tempfile
        import os

        # Capture to device temp file
        device_path = "/sdcard/screenshot.png"
        self._run_shell("screencap", "-p", device_path)

        # Pull to local temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            local_path = f.name

        self._run_adb("pull", device_path, local_path)

        # Read image
        img = cv2.imread(local_path)
        os.unlink(local_path)

        # Crop if region specified
        if region and img is not None:
            x, y, w, h = region
            img = img[y:y+h, x:x+w]

        return img

    def click(self, x: int, y: int, click_type: str = "single") -> None:
        """Tap on Android screen via ADB."""
        if click_type == "double":
            # Double tap
            self._run_shell("input", "tap", str(x), str(y))
            self._run_shell("input", "tap", str(x), str(y))
        elif click_type == "long":
            # Long press (swipe with 0 distance)
            self._run_shell("input", "swipe", str(x), str(y), str(x), str(y), "1000")
        else:
            self._run_shell("input", "tap", str(x), str(y))

    def type_text(self, text: str) -> None:
        """Type text on Android via ADB."""
        # Escape special characters for shell
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self._run_shell("input", "text", escaped)

    def press_key(self, key: str) -> None:
        """Press key on Android via ADB keyevent."""
        key_map = {
            "enter": "66",
            "back": "4",
            "home": "3",
            "tab": "61",
            "delete": "67",
            "backspace": "67",
            "ctrl+a": "29",  # KEYCODE_A with meta
        }

        keycode = key_map.get(key.lower(), key)
        self._run_shell("input", "keyevent", keycode)

    def scroll(
        self,
        x: int,
        y: int,
        direction: str = "down",
        amount: int = 1
    ) -> None:
        """Scroll on Android via ADB swipe."""
        distance = 300 * amount

        if direction == "down":
            end_y = y - distance
            self._run_shell("input", "swipe", str(x), str(y), str(x), str(end_y), "300")
        elif direction == "up":
            end_y = y + distance
            self._run_shell("input", "swipe", str(x), str(y), str(x), str(end_y), "300")
        elif direction == "left":
            end_x = x + distance
            self._run_shell("input", "swipe", str(x), str(y), str(end_x), str(y), "300")
        elif direction == "right":
            end_x = x - distance
            self._run_shell("input", "swipe", str(x), str(y), str(end_x), str(y), "300")
