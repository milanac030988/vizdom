"""Windows screen capture (mss if available, else Pillow ImageGrab)."""

import numpy as np

from visual_dom.core.ports.outbound.capture_port import CaptureStrategy


class WindowsCapture(CaptureStrategy):
    name = "windows"
    platform = "windows"
    description = "Full-screen grab on Windows (mss, or Pillow ImageGrab fallback)."

    def __init__(self, monitor: int = 1):
        self._monitor = monitor
        self._sct = None

    @classmethod
    def is_available(cls) -> bool:
        import sys
        if not sys.platform.startswith("win"):
            return False
        try:
            import mss  # noqa: F401
            return True
        except Exception:
            try:
                from PIL import ImageGrab  # noqa: F401
                return True
            except Exception:
                return False

    def capture(self) -> np.ndarray:
        import cv2
        # Prefer mss (fast, multi-monitor); fall back to Pillow ImageGrab.
        try:
            import mss
            if self._sct is None:
                self._sct = mss.mss()
            mon = self._sct.monitors[self._monitor]
            shot = self._sct.grab(mon)
            arr = np.array(shot)  # BGRA
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        except Exception:
            from PIL import ImageGrab
            img = ImageGrab.grab()  # RGB
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
